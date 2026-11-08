-- Holy Face Center helpline schema
-- Run this entire file in Supabase Dashboard → SQL Editor.

create extension if not exists pgcrypto;

do $$
begin
  create type public.vent_kind as enum ('support', 'self-release');
exception
  when duplicate_object then null;
end $$;

do $$
begin
  create type public.vent_status as enum (
    'new',
    'contact-attempted',
    'scheduled',
    'closed',
    'stored'
  );
exception
  when duplicate_object then null;
end $$;

create table if not exists public.admin_users (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null,
  created_at timestamptz not null default now()
);

create or replace function public.is_helpline_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.admin_users
    where user_id = auth.uid()
  );
$$;

revoke all on function public.is_helpline_admin() from public;
grant execute on function public.is_helpline_admin() to authenticated;

create table if not exists public.vent_entries (
  id uuid primary key default gen_random_uuid(),
  reference_code text not null unique
    default ('HF-' || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 8))),
  owner_id uuid not null references auth.users(id) on delete cascade,
  kind public.vent_kind not null,
  message text not null check (char_length(btrim(message)) >= 10),
  name text,
  age integer,
  contact_number text,
  scheduled_for timestamptz,
  consent_to_contact boolean not null default false,
  status public.vent_status not null default 'new',
  staff_notes text,
  expires_at timestamptz not null default (now() + interval '30 days'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint valid_help_request check (
    (
      kind = 'self-release'
      and name is null
      and age is null
      and contact_number is null
      and scheduled_for is null
      and consent_to_contact = false
      and status in ('stored', 'closed')
    )
    or
    (
      kind = 'support'
      and char_length(btrim(name)) >= 2
      and age between 7 and 120
      and regexp_replace(contact_number, '[[:space:]-]', '', 'g')
        ~ '^(\\+63|0)9[0-9]{9}$'
      and scheduled_for is not null
      and consent_to_contact = true
    )
  )
);

create or replace function public.prepare_vent_entry()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  local_schedule timestamp;
begin
  new.reference_code :=
    'HF-' || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 8));
  new.status := case
    when new.kind = 'support' then 'new'::public.vent_status
    else 'stored'::public.vent_status
  end;
  new.staff_notes := null;
  new.expires_at := now() + interval '30 days';
  new.created_at := now();
  new.updated_at := now();

  if new.kind = 'self-release' then
    new.name := null;
    new.age := null;
    new.contact_number := null;
    new.scheduled_for := null;
    new.consent_to_contact := false;
  else
    local_schedule := new.scheduled_for at time zone 'Asia/Manila';
    if new.scheduled_for <= now()
      or new.scheduled_for > now() + interval '31 days'
      or extract(isodow from local_schedule) not between 1 and 5
      or local_schedule::time not between time '09:00' and time '16:30'
      or extract(minute from local_schedule)::integer not in (0, 30)
      or extract(second from local_schedule) <> 0
    then
      raise exception 'Invalid callback schedule';
    end if;
  end if;

  return new;
end;
$$;

drop trigger if exists prepare_vent_entry_before_insert on public.vent_entries;
create trigger prepare_vent_entry_before_insert
before insert on public.vent_entries
for each row execute function public.prepare_vent_entry();

create unique index if not exists vent_entries_unique_schedule
  on public.vent_entries (scheduled_for)
  where scheduled_for is not null;

create index if not exists vent_entries_owner_created
  on public.vent_entries (owner_id, created_at desc);

create index if not exists vent_entries_status_created
  on public.vent_entries (status, created_at desc);

create index if not exists vent_entries_expiry
  on public.vent_entries (expires_at);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_vent_entries_updated_at on public.vent_entries;
create trigger set_vent_entries_updated_at
before update on public.vent_entries
for each row execute function public.set_updated_at();

alter table public.admin_users enable row level security;
alter table public.vent_entries enable row level security;

revoke all on table public.admin_users from anon, authenticated;
grant select on table public.admin_users to authenticated;

revoke all on table public.vent_entries from anon, authenticated;
grant select, delete on table public.vent_entries to authenticated;
grant update (status, staff_notes) on table public.vent_entries to authenticated;

drop policy if exists "Admins can read their profile" on public.admin_users;
create policy "Admins can read their profile"
on public.admin_users
for select
to authenticated
using (user_id = auth.uid());

drop policy if exists "Visitors can create their own entries" on public.vent_entries;
create policy "Visitors can create their own entries"
on public.vent_entries
for insert
to authenticated
with check (
  owner_id = auth.uid()
  and expires_at <= now() + interval '30 days 5 minutes'
  and expires_at >= now() + interval '29 days 23 hours'
);

drop policy if exists "Visitors can read their active entries" on public.vent_entries;
create policy "Visitors can read their active entries"
on public.vent_entries
for select
to authenticated
using (
  (owner_id = auth.uid() and expires_at > now())
  or public.is_helpline_admin()
);

drop policy if exists "Visitors can delete their own entries" on public.vent_entries;
create policy "Visitors can delete their own entries"
on public.vent_entries
for delete
to authenticated
using (owner_id = auth.uid() or public.is_helpline_admin());

drop policy if exists "Admins can update entries" on public.vent_entries;
create policy "Admins can update entries"
on public.vent_entries
for update
to authenticated
using (public.is_helpline_admin())
with check (public.is_helpline_admin());

create or replace function public.submit_vent_entry(
  p_kind public.vent_kind,
  p_message text,
  p_name text default null,
  p_age integer default null,
  p_contact_number text default null,
  p_scheduled_for timestamptz default null,
  p_consent_to_contact boolean default false
)
returns table (reference_code text, expires_at timestamptz)
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.uid() is null then
    raise exception 'Authentication is required' using errcode = '42501';
  end if;

  return query
  insert into public.vent_entries (
    owner_id,
    kind,
    message,
    name,
    age,
    contact_number,
    scheduled_for,
    consent_to_contact
  ) values (
    auth.uid(),
    p_kind,
    btrim(p_message),
    p_name,
    p_age,
    p_contact_number,
    p_scheduled_for,
    p_consent_to_contact
  )
  returning vent_entries.reference_code, vent_entries.expires_at;
end;
$$;

revoke all on function public.submit_vent_entry(
  public.vent_kind, text, text, integer, text, timestamptz, boolean
) from public, anon;
grant execute on function public.submit_vent_entry(
  public.vent_kind, text, text, integer, text, timestamptz, boolean
) to authenticated;

revoke insert on table public.vent_entries from authenticated;
notify pgrst, 'reload schema';

create or replace function public.get_booked_slots(requested_date date)
returns table (scheduled_for timestamptz)
language sql
stable
security definer
set search_path = public
as $$
  select e.scheduled_for
  from public.vent_entries e
  where e.scheduled_for is not null
    and e.expires_at > now()
    and (e.scheduled_for at time zone 'Asia/Manila')::date = requested_date;
$$;

revoke all on function public.get_booked_slots(date) from public;
grant execute on function public.get_booked_slots(date) to authenticated;

create or replace function public.purge_expired_vent_entries()
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
  deleted_count bigint;
begin
  delete from public.vent_entries where expires_at <= now();
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

revoke all on function public.purge_expired_vent_entries() from public;
grant execute on function public.purge_expired_vent_entries() to service_role;

-- In Supabase Dashboard → Integrations → Cron, create a daily job with:
--   Name: purge-expired-vent-entries
--   Schedule: 15 0 * * *
--   SQL command: select public.purge_expired_vent_entries();

-- Make newly created tables and functions available to the REST API immediately.
notify pgrst, 'reload schema';
