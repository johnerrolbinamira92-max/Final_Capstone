create table if not exists public.patient_help_requests (
    request_id uuid primary key default gen_random_uuid(),
    patient_name text check (char_length(btrim(patient_name)) between 1 and 160),
    patient_age smallint check (patient_age between 1 and 120),
    contact_number text not null check (char_length(btrim(contact_number)) between 7 and 24),
    message text not null check (char_length(btrim(message)) between 1 and 10000),
    requested_date date not null,
    requested_time_slot time not null,
    consent_given boolean not null check (consent_given),
    approval_status text not null default 'Pending'
        check (approval_status in ('Pending', 'Scheduled', 'Rescheduled', 'Completed', 'No-show', 'Cancelled')),
    created_at timestamptz not null default now()
);

alter table public.patient_help_requests
    alter column patient_name drop not null,
    alter column patient_age drop not null;

alter table public.patient_help_requests
    add column if not exists patient_user_id uuid
    references auth.users (id) on delete set null;

alter table public.patient_help_requests
    add column if not exists patient_email text;

alter table public.patient_help_requests
    add column if not exists guest_token text;

create index if not exists patient_help_requests_created_at_idx
    on public.patient_help_requests (created_at desc);

create index if not exists patient_help_requests_status_date_idx
    on public.patient_help_requests (approval_status, requested_date);

create unique index if not exists patient_help_requests_guest_token_uidx
    on public.patient_help_requests (guest_token)
    where guest_token is not null;

alter table public.patient_help_requests enable row level security;

revoke all on public.patient_help_requests from public, anon, authenticated;
grant insert on public.patient_help_requests to anon;
grant select, update on public.patient_help_requests to service_role;

drop policy if exists "Anyone can submit a consented help request"
    on public.patient_help_requests;
create policy "Anyone can submit a consented help request"
    on public.patient_help_requests
    for insert
    to anon
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

alter table public.patient_help_requests enable row level security;

grant select on table public.patient_help_requests to authenticated;

drop policy if exists "Patients can read their own help requests"
    on public.patient_help_requests;

create policy "Patients can read their own help requests"
    on public.patient_help_requests
    for select
    to authenticated
    using (
        patient_user_id = (select auth.uid())
        or (
            patient_user_id is null
            and nullif(btrim((select auth.jwt() ->> 'email')), '') is not null
            and lower(btrim(patient_email)) =
                lower(btrim((select auth.jwt() ->> 'email')))
        )
    );

create or replace function public.get_guest_request_updates(tokens text[])
returns table (
    id uuid,
    guest_token text,
    preferred_date date,
    preferred_time time,
    confirmed_date date,
    confirmed_time time,
    status text,
    created_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
begin
    if tokens is null or cardinality(tokens) = 0 then
        return;
    end if;

    if exists (
        select 1
        from unnest(tokens) as supplied(token)
        where supplied.token is null
           or char_length(btrim(supplied.token)) < 24
    ) then
        raise exception 'Every guest request token must contain at least 24 characters.';
    end if;

    return query
    select
        request.request_id,
        request.guest_token,
        request.requested_date,
        request.requested_time_slot,
        case
            when request.approval_status in ('Scheduled', 'Confirmed', 'Rescheduled')
                then request.requested_date
            else null
        end,
        case
            when request.approval_status in ('Scheduled', 'Confirmed', 'Rescheduled')
                then request.requested_time_slot
            else null
        end,
        case
            when request.approval_status in ('Scheduled', 'Confirmed') then 'Confirmed'
            when request.approval_status = 'Rescheduled' then 'Rescheduled'
            else 'Declined'
        end,
        request.created_at
    from public.patient_help_requests as request
    where request.patient_user_id is null
      and request.guest_token = any(tokens)
      and request.approval_status in (
          'Scheduled',
          'Confirmed',
          'Rescheduled',
          'Declined',
          'Cancelled'
      )
    order by request.created_at desc;
end;
$$;

create or replace function public.claim_guest_requests(tokens text[])
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
    claimed_count integer;
begin
    if auth.uid() is null then
        raise exception 'An authenticated account is required to claim guest requests.';
    end if;

    if tokens is null or cardinality(tokens) = 0 then
        return 0;
    end if;

    if exists (
        select 1
        from unnest(tokens) as supplied(token)
        where supplied.token is null
           or char_length(btrim(supplied.token)) < 24
    ) then
        raise exception 'Every guest request token must contain at least 24 characters.';
    end if;

    update public.patient_help_requests as request
    set patient_user_id = auth.uid(),
        patient_email = coalesce(
            nullif(request.patient_email, ''),
            auth.jwt() ->> 'email'
        )
    where request.patient_user_id is null
      and request.guest_token = any(tokens);

    get diagnostics claimed_count = row_count;
    return claimed_count;
end;
$$;

revoke all on function public.get_guest_request_updates(text[])
    from public, anon, authenticated;
grant execute on function public.get_guest_request_updates(text[])
    to anon, authenticated;

revoke all on function public.claim_guest_requests(text[])
    from public, anon, authenticated;
grant execute on function public.claim_guest_requests(text[])
    to authenticated;