begin;

create or replace function public.get_callback_slot_availability(target_date date)
returns table (
    requested_date date,
    requested_time_slot time,
    approval_status text
)
language sql
stable
security definer
set search_path = ''
as $$
    select request.requested_date, request.requested_time_slot, request.approval_status
    from public.patient_help_requests as request
    where request.requested_date = target_date
      and lower(btrim(coalesce(request.approval_status, ''))) not in (
          'done',
          'completed',
          'cancelled',
          'declined'
      )

    union all

    select appointment.requested_date, appointment.requested_time_slot, appointment.approval_status
    from public.appointments as appointment
    where appointment.requested_date = target_date
      and lower(btrim(coalesce(appointment.approval_status, ''))) not in (
          'done',
          'completed',
          'cancelled',
          'declined'
      );
$$;

revoke all on function public.get_callback_slot_availability(date)
    from public, anon, authenticated;
grant execute on function public.get_callback_slot_availability(date)
    to anon, authenticated;

create or replace function public.prevent_callback_slot_conflicts()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    conflicting_slots bigint;
    slot_keys text[] := array[]::text[];
    slot_key text;
begin
    if lower(btrim(coalesce(new.approval_status, ''))) in (
        'done',
        'completed',
        'cancelled',
        'declined'
    ) or new.requested_date is null or new.requested_time_slot is null then
        return new;
    end if;

    if tg_op = 'UPDATE' then
        if old.requested_date is not null and old.requested_time_slot is not null then
            slot_keys := array_append(
                slot_keys,
                old.requested_date::text || ' ' || old.requested_time_slot::text
            );
        end if;
    end if;

    slot_keys := array_append(
        slot_keys,
        new.requested_date::text || ' ' || new.requested_time_slot::text
    );

    for slot_key in
        select distinct keys.slot_key
        from unnest(slot_keys) as keys(slot_key)
        order by keys.slot_key
    loop
        perform pg_catalog.pg_advisory_xact_lock(
            pg_catalog.hashtextextended(slot_key, 0)
        );
    end loop;

    select count(*)
    into conflicting_slots
    from public.patient_help_requests as request
    where request.requested_date = new.requested_date
      and request.requested_time_slot = new.requested_time_slot
      and lower(btrim(coalesce(request.approval_status, ''))) not in (
          'done',
          'completed',
          'cancelled',
          'declined'
      );
    if tg_table_name = 'patient_help_requests'
       and tg_op = 'UPDATE'
       and old.requested_date = new.requested_date
       and old.requested_time_slot = new.requested_time_slot
       and lower(btrim(coalesce(old.approval_status, ''))) not in (
           'done',
           'completed',
           'cancelled',
           'declined'
       ) then
        conflicting_slots := conflicting_slots - 1;
    end if;
    if conflicting_slots > 0 then
        raise exception using
            errcode = '23505',
            message = 'The selected callback slot is already taken.';
    end if;

    select count(*)
    into conflicting_slots
    from public.appointments as appointment
    where appointment.requested_date = new.requested_date
      and appointment.requested_time_slot = new.requested_time_slot
      and lower(btrim(coalesce(appointment.approval_status, ''))) not in (
          'done',
          'completed',
          'cancelled',
          'declined'
      );
    if tg_table_name = 'appointments'
       and tg_op = 'UPDATE'
       and old.requested_date = new.requested_date
       and old.requested_time_slot = new.requested_time_slot
       and lower(btrim(coalesce(old.approval_status, ''))) not in (
           'done',
           'completed',
           'cancelled',
           'declined'
       ) then
        conflicting_slots := conflicting_slots - 1;
    end if;
    if conflicting_slots > 0 then
        raise exception using
            errcode = '23505',
            message = 'The selected callback slot is already taken.';
    end if;

    return new;
end;
$$;

revoke all on function public.prevent_callback_slot_conflicts()
    from public, anon, authenticated;

drop trigger if exists patient_help_requests_prevent_slot_conflicts
    on public.patient_help_requests;
create trigger patient_help_requests_prevent_slot_conflicts
before insert or update of requested_date, requested_time_slot, approval_status
on public.patient_help_requests
for each row
execute function public.prevent_callback_slot_conflicts();

drop trigger if exists appointments_prevent_slot_conflicts
    on public.appointments;
create trigger appointments_prevent_slot_conflicts
before insert or update of requested_date, requested_time_slot, approval_status
on public.appointments
for each row
execute function public.prevent_callback_slot_conflicts();

commit;
