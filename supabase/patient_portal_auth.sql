begin;

create extension if not exists pg_net with schema extensions;

create table if not exists public.patient_journal_entries (
    entry_id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    client_entry_id text not null,
    content text not null check (char_length(btrim(content)) between 1 and 10000),
    created_at timestamptz not null default now(),
    unique (user_id, client_entry_id)
);

alter table public.patient_journal_entries enable row level security;
revoke all on public.patient_journal_entries from public, anon, authenticated;
grant select, insert, update, delete on public.patient_journal_entries to authenticated;

drop policy if exists "Patients can read their own journal entries"
    on public.patient_journal_entries;
create policy "Patients can read their own journal entries"
    on public.patient_journal_entries
    for select to authenticated
    using (user_id = auth.uid());

drop policy if exists "Patients can add their own journal entries"
    on public.patient_journal_entries;
create policy "Patients can add their own journal entries"
    on public.patient_journal_entries
    for insert to authenticated
    with check (user_id = auth.uid());

drop policy if exists "Patients can update their own journal entries"
    on public.patient_journal_entries;
create policy "Patients can update their own journal entries"
    on public.patient_journal_entries
    for update to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

drop policy if exists "Patients can delete their own journal entries"
    on public.patient_journal_entries;
create policy "Patients can delete their own journal entries"
    on public.patient_journal_entries
    for delete to authenticated
    using (user_id = auth.uid());

create table if not exists public.patient_journal_entry_counts (
    user_id uuid primary key references auth.users (id) on delete cascade,
    entry_count bigint not null check (entry_count >= 0)
);

alter table public.patient_journal_entry_counts enable row level security;
revoke all on public.patient_journal_entry_counts from public, anon, authenticated;

delete from public.patient_journal_entry_counts as counts
where not exists (
    select 1
    from public.patient_journal_entries as entries
    where entries.user_id = counts.user_id
);

insert into public.patient_journal_entry_counts (user_id, entry_count)
select user_id, count(*)::bigint
from public.patient_journal_entries
group by user_id
on conflict (user_id) do update
set entry_count = excluded.entry_count;

create or replace function public.notify_journal_entry_milestone()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_entry_count bigint;
    v_patient_email text;
    v_wellness_email_opt_in boolean;
    v_project_url text;
    v_publishable_key text;
    v_webhook_secret text;
begin
    insert into public.patient_journal_entry_counts as counts (user_id, entry_count)
    values (new.user_id, 1)
    on conflict (user_id) do update
    set entry_count = counts.entry_count + 1
    returning entry_count into v_entry_count;

    if v_entry_count <= 0 or mod(v_entry_count, 5) <> 0 then
        return new;
    end if;

    select
        patient.email,
        coalesce(patient.raw_user_meta_data ->> 'wellness_email_opt_in', 'false') = 'true'
    into v_patient_email, v_wellness_email_opt_in
    from auth.users as patient
    where patient.id = new.user_id;

    if not coalesce(v_wellness_email_opt_in, false) then
        return new;
    end if;

    if v_patient_email is null or btrim(v_patient_email) = '' then
        raise warning 'Wellness check-in skipped: opted-in patient % has no email address.', new.user_id;
        return new;
    end if;

    select decrypted_secret into v_project_url
    from vault.decrypted_secrets
    where name = 'patient_portal_project_url';

    select decrypted_secret into v_publishable_key
    from vault.decrypted_secrets
    where name = 'patient_portal_publishable_key';

    select decrypted_secret into v_webhook_secret
    from vault.decrypted_secrets
    where name = 'patient_portal_wellness_webhook_secret';

    if v_project_url is null or v_publishable_key is null or v_webhook_secret is null then
        raise warning 'Wellness check-in skipped: configure the patient portal webhook secrets in Supabase Vault.';
        return new;
    end if;

    perform net.http_post(
        url := rtrim(v_project_url, '/') || '/functions/v1/notify-five-entries',
        body := jsonb_build_object(
            'user_id', new.user_id,
            'patient_email', v_patient_email,
            'entry_count', v_entry_count
        ),
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'apikey', v_publishable_key,
            'x-wellness-webhook-secret', v_webhook_secret
        ),
        timeout_milliseconds := 5000
    );

    return new;
end;
$$;

create or replace function public.decrement_journal_entry_count()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.patient_journal_entry_counts
    set entry_count = entry_count - 1
    where user_id = old.user_id
      and entry_count > 0;

    delete from public.patient_journal_entry_counts
    where user_id = old.user_id
      and entry_count = 0;

    return old;
end;
$$;

revoke all on function public.notify_journal_entry_milestone() from public, anon, authenticated;
revoke all on function public.decrement_journal_entry_count() from public, anon, authenticated;

drop trigger if exists patient_journal_entry_milestone
    on public.patient_journal_entries;
create trigger patient_journal_entry_milestone
after insert on public.patient_journal_entries
for each row
execute function public.notify_journal_entry_milestone();

drop trigger if exists patient_journal_entry_count_delete
    on public.patient_journal_entries;
create trigger patient_journal_entry_count_delete
after delete on public.patient_journal_entries
for each row
execute function public.decrement_journal_entry_count();

alter table public.patient_help_requests
    add column if not exists patient_user_id uuid
    references auth.users (id) on delete set null;

alter table public.patient_help_requests
    add column if not exists patient_email text;

alter table public.patient_help_requests
    add column if not exists guest_token text;

create index if not exists patient_help_requests_patient_user_id_idx
    on public.patient_help_requests (patient_user_id, created_at desc);

create unique index if not exists patient_help_requests_guest_token_uidx
    on public.patient_help_requests (guest_token)
    where guest_token is not null;

create index if not exists patient_help_requests_legacy_email_idx
    on public.patient_help_requests (lower(btrim(patient_email)), created_at desc)
    where patient_user_id is null;

alter table public.patient_help_requests enable row level security;
revoke all on public.patient_help_requests from public, anon, authenticated;
grant insert on public.patient_help_requests to anon, authenticated;
grant select, update on public.patient_help_requests to authenticated;
grant select, update on public.patient_help_requests to service_role;

drop policy if exists "Anyone can submit a consented help request"
    on public.patient_help_requests;
create policy "Anyone can submit a consented help request"
    on public.patient_help_requests
    for insert to anon
    with check (
        patient_user_id is null
        and patient_email is null
        and (guest_token is null or char_length(btrim(guest_token)) >= 24)
        and consent_given is true
        and requested_date >= (now() at time zone 'Asia/Manila')::date
        and extract(isodow from requested_date) between 1 and 5
        and requested_time_slot >= time '08:00'
        and requested_time_slot <= time '15:30'
        and (
            requested_time_slot < time '12:00'
            or requested_time_slot >= time '13:00'
        )
        and extract(minute from requested_time_slot) in (0, 30)
        and extract(second from requested_time_slot) = 0
    );

drop policy if exists "Signed-in patients can submit their own help requests"
    on public.patient_help_requests;
create policy "Signed-in patients can submit their own help requests"
    on public.patient_help_requests
    for insert to authenticated
    with check (
        patient_user_id = auth.uid()
        and consent_given is true
        and requested_date >= (now() at time zone 'Asia/Manila')::date
        and extract(isodow from requested_date) between 1 and 5
        and requested_time_slot >= time '08:00'
        and requested_time_slot <= time '15:30'
        and (
            requested_time_slot < time '12:00'
            or requested_time_slot >= time '13:00'
        )
        and extract(minute from requested_time_slot) in (0, 30)
        and extract(second from requested_time_slot) = 0
    );

drop policy if exists "Patients can read their own help requests"
    on public.patient_help_requests;
create policy "Patients can read their own help requests"
    on public.patient_help_requests
    for select to authenticated
    using (
        patient_user_id = (select auth.uid())
        or (
            patient_user_id is null
            and nullif(btrim((select auth.jwt() ->> 'email')), '') is not null
            and lower(btrim(patient_email)) =
                lower(btrim((select auth.jwt() ->> 'email')))
        )
    );

alter table public.appointments
    add column if not exists patient_user_id uuid
    references auth.users (id) on delete set null;

create index if not exists appointments_patient_user_id_idx
    on public.appointments (patient_user_id, created_at desc);

grant select on public.appointments to authenticated;
drop policy if exists "Patients can read their own appointments"
    on public.appointments;
create policy "Patients can read their own appointments"
    on public.appointments
    for select to authenticated
    using (patient_user_id = auth.uid());

commit;
