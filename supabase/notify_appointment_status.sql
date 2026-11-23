begin;

create extension if not exists pg_net with schema extensions;

create or replace function public.notify_patient_help_request_status()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_project_url text;
    v_publishable_key text;
    v_webhook_secret text;
begin
    if new.approval_status is not distinct from old.approval_status then
        return new;
    end if;

    if lower(btrim(coalesce(new.approval_status, ''))) not in (
        'scheduled',
        'confirmed',
        'rescheduled',
        'declined',
        'cancelled'
    ) then
        return new;
    end if;

    if new.patient_email is null or btrim(new.patient_email) = '' then
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
        raise warning 'Appointment status email skipped: configure the patient portal webhook secrets in Supabase Vault.';
        return new;
    end if;

    perform net.http_post(
        url := rtrim(v_project_url, '/') || '/functions/v1/notify-appointment-status',
        body := jsonb_build_object(
            'request_id', new.request_id,
            'patient_email', new.patient_email,
            'approval_status', new.approval_status,
            'requested_date', new.requested_date,
            'requested_time_slot', new.requested_time_slot
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

revoke all on function public.notify_patient_help_request_status()
    from public, anon, authenticated;

drop trigger if exists patient_help_request_status_email
    on public.patient_help_requests;
create trigger patient_help_request_status_email
after update of approval_status on public.patient_help_requests
for each row
execute function public.notify_patient_help_request_status();

commit;
