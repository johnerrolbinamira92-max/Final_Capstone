-- Run once in Supabase SQL Editor for an existing helpline database.

begin;

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

commit;
