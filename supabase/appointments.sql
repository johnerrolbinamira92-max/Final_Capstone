create table if not exists public.appointments (
    appointment_id uuid primary key default gen_random_uuid(),
    patient_id text,
    patient_name text not null,
    contact_number text,
    requested_date date not null,
    requested_time_slot time,
    approval_status text not null default 'Pending'
        check (approval_status in ('Pending', 'Scheduled', 'Completed', 'Cancelled')),
    created_at timestamptz not null default now()
);

create index if not exists appointments_requested_date_idx
    on public.appointments (requested_date);

create index if not exists appointments_status_date_idx
    on public.appointments (approval_status, requested_date);

alter table public.appointments enable row level security;

-- The desktop admin uses a server-side secret key. Add patient-scoped policies
-- for the patient app after its authentication and patient-ID mapping are set.
grant select, insert, update on public.appointments to service_role;
