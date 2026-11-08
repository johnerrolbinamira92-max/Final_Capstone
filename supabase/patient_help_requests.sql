create table if not exists public.patient_help_requests (
    request_id uuid primary key default gen_random_uuid(),
    patient_name text not null check (char_length(btrim(patient_name)) between 1 and 160),
    patient_age smallint not null check (patient_age between 1 and 120),
    contact_number text not null check (char_length(btrim(contact_number)) between 7 and 24),
    message text not null check (char_length(btrim(message)) between 1 and 10000),
    requested_date date not null,
    requested_time_slot time not null,
    consent_given boolean not null check (consent_given),
    approval_status text not null default 'Pending'
        check (approval_status in ('Pending', 'Scheduled', 'Completed', 'Cancelled')),
    created_at timestamptz not null default now()
);

create index if not exists patient_help_requests_created_at_idx
    on public.patient_help_requests (created_at desc);

create index if not exists patient_help_requests_status_date_idx
    on public.patient_help_requests (approval_status, requested_date);

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
        consent_given is true
        and requested_date >= (now() at time zone 'Asia/Manila')::date
        and extract(isodow from requested_date) between 1 and 5
        and requested_time_slot >= time '09:00'
        and requested_time_slot <= time '16:30'
        and extract(minute from requested_time_slot) in (0, 30)
        and extract(second from requested_time_slot) = 0
    );
