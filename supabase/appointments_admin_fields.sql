begin;

alter table public.appointments
    add column if not exists reason text;

alter table public.appointments
    drop constraint if exists appointments_approval_status_check;

alter table public.appointments
    add constraint appointments_approval_status_check
    check (
        approval_status in (
            'Pending',
            'Scheduled',
            'Completed',
            'No-show',
            'Cancelled'
        )
    );

commit;
