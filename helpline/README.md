# Holy Face Center Helpline — Streamlit + Supabase

This directory is a standalone Python implementation of the helpline. It does
not replace or depend on the Next.js/Payload app in the repository root.

## Features

- Unlimited-length private vent-out messages
- “I need help” and “I don’t need help” paths
- Consent-gated contact collection
- Live 30-day weekday callback calendar with collision protection
- Visitor-owned history using anonymous Supabase Auth
- Visitor-only public interface; administration remains in the private root app
- Status tracking and staff notes
- Light and dark presentation
- 30-day database retention with an optional Supabase Cron cleanup
- Row Level Security; no service-role key is used by the app

## 1. Create the database

1. Open **Supabase Dashboard → SQL Editor**.
2. Paste and run [`supabase/schema.sql`](supabase/schema.sql).
3. Open **Authentication → Providers → Anonymous Sign-Ins** and enable it.

## 2. Configure an administrator

Create the staff user under **Authentication → Users**, then insert its UUID
into `public.admin_users`. Staff sign in through the repository root `app.py`;
the public `helpline/app.py` intentionally contains no administrator area.

## 3. Configure 30-day deletion

Row Level Security hides expired entries immediately. For physical deletion,
open **Supabase Dashboard → Integrations → Cron** and create:

- Name: `purge-expired-vent-entries`
- Schedule: `15 0 * * *`
- SQL: `select public.purge_expired_vent_entries();`

## 4. Configure the app

Copy the example secrets file:

```bash
cd streamlit_supabase
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Get the values from **Supabase Dashboard → Project Settings → API**:

```toml
SUPABASE_URL = "https://YOUR_PROJECT_ID.supabase.co"
SUPABASE_ANON_KEY = "YOUR_PUBLIC_ANON_KEY"
```

The anon key is intended for client applications and is protected by RLS.
Never add the service-role key or database password to this app.

Environment variables with the same names can be used instead.

## 5. Run locally

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Push this directory to GitHub.
2. Create a Streamlit Community Cloud app.
3. Set the main file path to `streamlit_supabase/app.py`.
4. Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` under **App settings → Secrets**.
5. Deploy.

## Security notes

- Treat narratives, names, ages, phone numbers, and staff notes as sensitive.
- Keep Supabase RLS enabled.
- Do not expose or commit the service-role key.
- Limit Supabase Dashboard and Streamlit Cloud access to authorized staff.
- Review local privacy, consent, records-retention, and breach-response
  requirements before production use.
- The form is not an emergency response service; retain the visible 911 notice.
