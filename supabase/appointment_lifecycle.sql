begin;

alter table public.appointments
    add column if not exists updated_at timestamptz;

update public.appointments
set updated_at = coalesce(updated_at, created_at, now())
where updated_at is null;

alter table public.appointments
    alter column updated_at set default now(),
    alter column updated_at set not null;

alter table public.patient_help_requests
    add column if not exists updated_at timestamptz;

update public.patient_help_requests
set updated_at = coalesce(updated_at, created_at, now())
where updated_at is null;

alter table public.appointments
    drop constraint if exists appointments_approval_status_check;

alter table public.appointments
    add constraint appointments_approval_status_check
    check (
        approval_status in (
            'Pending',
            'Scheduled',
            'Rescheduled',
            'Completed',
            'No-show',
            'Cancelled'
        )
    );

alter table public.patient_help_requests
    alter column updated_at set default now(),
    alter column updated_at set not null;

alter table public.patient_help_requests
    drop constraint if exists patient_help_requests_approval_status_check;

alter table public.patient_help_requests
    add constraint patient_help_requests_approval_status_check
    check (
        approval_status in (
            'Pending',
            'Scheduled',
            'Rescheduled',
            'Completed',
            'No-show',
            'Cancelled'
        )
    );

create or replace function public.set_appointment_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists appointments_set_updated_at on public.appointments;
create trigger appointments_set_updated_at
before update on public.appointments
for each row
execute function public.set_appointment_updated_at();

drop trigger if exists patient_help_requests_set_updated_at
    on public.patient_help_requests;
create trigger patient_help_requests_set_updated_at
before update on public.patient_help_requests
for each row
execute function public.set_appointment_updated_at();

commit;
