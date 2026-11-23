begin;

alter table public.appointments
    add column if not exists patient_email text;

alter table public.patient_help_requests
    add column if not exists patient_email text;

update public.appointments as appointment
set patient_email = nullif(btrim(patient.email), '')
from auth.users as patient
where appointment.patient_user_id = patient.id;

update public.patient_help_requests as request
set patient_email = nullif(btrim(patient.email), '')
from auth.users as patient
where request.patient_user_id = patient.id;

create or replace function public.set_patient_request_email()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if new.patient_user_id is null then
        if tg_op = 'UPDATE' then
            if old.patient_user_id is null then
                new.patient_email := old.patient_email;
            else
                new.patient_email := null;
            end if;
        else
            new.patient_email := null;
        end if;
    else
        select nullif(btrim(patient.email), '')
        into new.patient_email
        from auth.users as patient
        where patient.id = new.patient_user_id;

        if not found then
            new.patient_email := null;
        end if;
    end if;

    return new;
end;
$$;

revoke all on function public.set_patient_request_email()
    from public, anon, authenticated;

drop trigger if exists appointments_set_patient_email
    on public.appointments;
create trigger appointments_set_patient_email
before insert or update on public.appointments
for each row
execute function public.set_patient_request_email();

drop trigger if exists patient_help_requests_set_patient_email
    on public.patient_help_requests;
create trigger patient_help_requests_set_patient_email
before insert or update on public.patient_help_requests
for each row
execute function public.set_patient_request_email();

commit;
