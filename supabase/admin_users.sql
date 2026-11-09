begin;

create table if not exists public.admin_users (
    user_id uuid primary key references auth.users (id) on delete cascade,
    display_name text not null,
    created_at timestamptz not null default now()
);

alter table public.admin_users enable row level security;

revoke all on public.admin_users from public, anon, authenticated;
grant select on public.admin_users to authenticated;

drop policy if exists "Admins can read their own profile"
    on public.admin_users;
create policy "Admins can read their own profile"
    on public.admin_users
    for select
    to authenticated
    using (auth.uid() = user_id);

commit;
