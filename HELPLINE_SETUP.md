# Helpline integration

This repository now contains two Streamlit applications connected to the same
Supabase project:

- `app.py`: the existing private records/admin system, now with a **Helpline
  Requests** page.
- `helpline/app.py`: the public-facing, visitor-only mental-health helpline.

## Database

Run `helpline/supabase/schema.sql` once in the target Supabase project's SQL
Editor. Enable anonymous sign-ins under Authentication providers. The schema
contains Row Level Security, administrator authorization, scheduling validation,
and the 30-day retention function.

## Public helpline configuration

Set these in `helpline/.streamlit/secrets.toml` locally or in the public
Streamlit app's deployment secrets:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_ANON_KEY = "YOUR_PUBLIC_OR_PUBLISHABLE_KEY"
```

Run it separately:

```bash
pip install -r helpline/requirements.txt
streamlit run helpline/app.py
```

Never give the public app a service-role key.

## Private admin configuration

The root admin app uses Supabase Auth for staff login and a server-side key for
private operational reads:

```text
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_ANON_KEY=YOUR_PUBLIC_OR_PUBLISHABLE_KEY
SUPABASE_KEY=YOUR_SERVER_SIDE_SERVICE_ROLE_KEY
```

The service-role key belongs only in the trusted private admin deployment. Do
not commit it, place it in the public helpline, or expose it in browser code.

Run the private admin system:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Administrator identity

Create each staff account in Supabase Auth and add its UUID to
`public.admin_users`. The root admin system verifies both the email/password and
that administrator relationship before opening any private page. The public
helpline contains no administrator login or staff navigation.

## Retention

Create a daily Supabase Cron job:

```sql
select public.purge_expired_vent_entries();
```

Recommended schedule: `15 0 * * *`.

## Important security cleanup

This repository previously committed a `.env` file. Treat any credentials in
that file as compromised: rotate them in their provider dashboards, remove the
file from Git tracking, and keep only a placeholder `.env.example` in source
control. Rewriting Git history is a separate, potentially disruptive operation
and should be coordinated with every collaborator.
