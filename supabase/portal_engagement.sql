begin;

do $$
begin
    if to_regclass('public.portal_engagement_counts') is not null
        and exists (
            select 1
            from information_schema.columns
            where table_schema = 'public'
              and table_name = 'portal_engagement_counts'
              and column_name = 'action_type'
        )
    then
        if to_regclass('public.portal_engagement_counts_action_rows') is not null then
            raise exception 'Portal engagement legacy table already exists.';
        end if;

        alter table public.portal_engagement_counts
            rename to portal_engagement_counts_action_rows;
    end if;
end;
$$;

create table if not exists public.portal_engagement_counts (
    id integer not null,
    need_help_submitted bigint not null default 0
        check (need_help_submitted >= 0),
    no_help_submitted bigint not null default 0
        check (no_help_submitted >= 0),
    updated_at timestamptz not null default now(),
    constraint portal_engagement_counts_singleton_pkey primary key (id),
    constraint portal_engagement_counts_singleton_id_check check (id = 1)
);

alter table public.portal_engagement_counts enable row level security;
revoke all on public.portal_engagement_counts from public, anon, authenticated;
grant select on public.portal_engagement_counts to service_role;

insert into public.portal_engagement_counts (
    id,
    need_help_submitted,
    no_help_submitted
)
values (1, 0, 0)
on conflict (id) do nothing;

create table if not exists public.portal_engagement_events (
    event_id bigint generated always as identity primary key,
    choice_type text not null
        check (choice_type in ('need_help', 'no_help')),
    user_type text not null
        check (user_type in ('guest', 'signed_in')),
    created_at timestamptz not null default now()
);

create index if not exists portal_engagement_events_time_choice_idx
    on public.portal_engagement_events (created_at, choice_type);

alter table public.portal_engagement_events enable row level security;
revoke all on public.portal_engagement_events from public, anon, authenticated;
grant insert on public.portal_engagement_events to anon, authenticated;
grant select on public.portal_engagement_events to service_role;
revoke all on sequence public.portal_engagement_events_event_id_seq
    from public, anon, authenticated;
grant usage on sequence public.portal_engagement_events_event_id_seq
    to anon, authenticated;

drop policy if exists portal_engagement_events_public_insert
    on public.portal_engagement_events;
create policy portal_engagement_events_public_insert
    on public.portal_engagement_events
    for insert
    to anon, authenticated
    with check (true);

do $$
begin
    if to_regclass('public.portal_engagement_counts_action_rows') is not null then
        execute $migration$
            insert into public.portal_engagement_counts as current_counts (
                id,
                need_help_submitted,
                no_help_submitted,
                updated_at
            )
            select
                1,
                coalesce(
                    max(submission_count)
                        filter (where action_type = 'need_help_submitted'),
                    0
                ),
                coalesce(
                    max(submission_count)
                        filter (where action_type = 'no_help_submitted'),
                    0
                ),
                coalesce(max(updated_at), now())
            from public.portal_engagement_counts_action_rows
            on conflict (id) do update
            set need_help_submitted = greatest(
                    current_counts.need_help_submitted,
                    excluded.need_help_submitted
                ),
                no_help_submitted = greatest(
                    current_counts.no_help_submitted,
                    excluded.no_help_submitted
                ),
                updated_at = greatest(
                    current_counts.updated_at,
                    excluded.updated_at
                )
        $migration$;

        drop table public.portal_engagement_counts_action_rows;
    end if;
end;
$$;

create or replace function public.increment_portal_engagement(action_type text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    if $1 is null or $1 not in ('need_help_submitted', 'no_help_submitted') then
        raise exception 'Unsupported portal engagement action.'
            using errcode = '22023';
    end if;

    insert into public.portal_engagement_counts as counts (
        id,
        need_help_submitted,
        no_help_submitted
    )
    values (
        1,
        case when $1 = 'need_help_submitted' then 1 else 0 end,
        case when $1 = 'no_help_submitted' then 1 else 0 end
    )
    on conflict (id) do update
    set need_help_submitted =
            counts.need_help_submitted + excluded.need_help_submitted,
        no_help_submitted =
            counts.no_help_submitted + excluded.no_help_submitted,
        updated_at = now();
end;
$$;

revoke all on function public.increment_portal_engagement(text)
    from public, anon, authenticated;
grant execute on function public.increment_portal_engagement(text)
    to anon, authenticated;

create or replace function public.track_patient_help_request_engagement()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    begin
        perform public.increment_portal_engagement('need_help_submitted');
    exception
        when others then
            raise warning 'Could not record portal engagement for patient help request: %',
                SQLERRM;
    end;
    return new;
end;
$$;

revoke all on function public.track_patient_help_request_engagement()
    from public, anon, authenticated;

drop trigger if exists patient_help_requests_portal_engagement_insert
    on public.patient_help_requests;
create trigger patient_help_requests_portal_engagement_insert
    after insert on public.patient_help_requests
    for each row
    execute function public.track_patient_help_request_engagement();

create or replace function public.get_anonymized_journal_stats()
returns table (code_name text, saved_entries bigint)
language sql
security definer
set search_path = ''
as $$
    with account_totals as (
        select entries.user_id, count(*)::bigint as saved_entries
        from public.patient_journal_entries as entries
        group by entries.user_id
    ),
    numbered_accounts as (
        select
            row_number() over (order by account_totals.user_id) as account_number,
            account_totals.saved_entries
        from account_totals
    )
    select
        'User #' || case
            when numbered_accounts.account_number < 10
                then '0' || numbered_accounts.account_number::text
            else numbered_accounts.account_number::text
        end,
        numbered_accounts.saved_entries
    from numbered_accounts
    order by numbered_accounts.account_number;
$$;

revoke all on function public.get_anonymized_journal_stats()
    from public, anon, authenticated;
grant execute on function public.get_anonymized_journal_stats()
    to service_role;

commit;
