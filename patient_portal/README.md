# Holy Face Center patient portal and helpline

This responsive site is the public patient portal and helpline. It is separate
from the private Streamlit admin app.

## Portal code structure

- `index.html` contains the page structure and loads the browser modules.
- `styles.css` contains the shared responsive and theme styling.
- `js/app.js` initializes the portal and connects the feature modules.
- `js/features/callback-schedule.js` manages the callback calendar and time slots.
- `js/features/callback-request.js` validates and submits callback requests.
- `js/features/private-entries.js` manages device entries and account backups.
- `js/ui/feedback.js` displays shared form feedback.
- The portal uses a fixed dark-teal theme.

The portal uses native JavaScript modules; continue serving it over HTTP as
described below rather than opening `index.html` directly.

## Set up Supabase

1. In the Supabase SQL Editor for the same project as the admin app, run [`../supabase/patient_help_requests.sql`](../supabase/patient_help_requests.sql), [`../supabase/patient_portal_auth.sql`](../supabase/patient_portal_auth.sql), [`../supabase/portal_engagement.sql`](../supabase/portal_engagement.sql), and [`../supabase/patient_request_emails.sql`](../supabase/patient_request_emails.sql). If the project is already configured, rerun the first two scripts to refresh their callback-time policies.
2. In Supabase **Authentication → Providers**, enable Email/password sign-in. Configure the allowed redirect URLs for the deployed portal if email confirmation is enabled.
3. In Supabase **Project Settings → API**, copy the project URL and the **publishable** key (or legacy anon key).
4. Put those two public values in [`config.js`](./config.js). Never put a `service_role` or secret key in this folder.
5. The Streamlit admin app must keep using its server-side key in its private `.env` file. Open **Appointment Schedule → Confidential help requests** to review and update requests.

The journal table uses row-level security so authenticated patients can access only their own entries. Authenticated callback requests are linked to the account that submitted them; an older unlinked request is visible to an authenticated patient only when its saved email matches that account. Guest requests stay unlinked unless the visitor later chooses **Import to my account**; guest notification lookups return only responded requests matched by the device-held reference tokens. For manually created appointments, set `patient_user_id` to the patient's Supabase Auth user UUID to show its status to that patient; this separate field avoids changing the admin app's existing internal `patient_id`. The admin app uses its private server-side key to manage requests and appointments. Do not expose a `service_role` or secret key in this folder.

The `portal_engagement.sql` migration adds anonymous completed-submission counters
and a staff-only RPC that returns sequential code names and saved-entry counts
for signed-in journal accounts. The Patient Statistics page caches only these
aggregate and anonymized values in the admin app's local SQLite archive for
offline viewing.

## Optional wellness check-in emails

Wellness emails are **off by default**. Patients can opt in when creating an account or change the preference in Recent Entries. If opted in, the portal sends a short, non-clinical check-in after each fifth saved account entry. The database sends only the account UUID, email address, and entry count to the function; journal text is never included. Patients can turn the emails off at any time from Recent Entries.

To enable the feature:

1. In Supabase **Database → Extensions**, enable `pg_net` if it is not already enabled. The portal SQL migration creates the journal counter and trigger.
2. Create a unique random webhook secret. In Supabase **Integrations → Vault**, add these secrets:
   - `patient_portal_project_url`: the Supabase project URL.
   - `patient_portal_publishable_key`: the project's publishable key (or legacy anon key).
   - `patient_portal_wellness_webhook_secret`: the random webhook secret.
3. Verify a sender address or domain in Resend.
4. In Supabase **Edge Functions → Secrets**, set `GEMINI_API_KEY`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL` (the verified Resend sender), and `WELLNESS_WEBHOOK_SECRET`. Set `WELLNESS_WEBHOOK_SECRET` to the same value as `patient_portal_wellness_webhook_secret` in Vault.
5. From the repository root, deploy the function with JWT verification disabled because the database webhook authenticates using the shared secret:

   ```powershell
   supabase functions deploy notify-five-entries --project-ref <project-ref> --no-verify-jwt
   ```

Keep the webhook secret and provider API keys private. The function validates the webhook secret itself; do not put any of these values in `patient_portal/config.js` or other browser code. Check Supabase Edge Function logs and Resend delivery status when validating the setup.

## Appointment status emails

The portal can send non-AI email updates when staff confirm, reschedule, decline,
or cancel a callback request. Requests without a patient email address are
skipped. The current request date and time fields are used as the confirmed
schedule.

1. Run [`../supabase/notify_appointment_status.sql`](../supabase/notify_appointment_status.sql) after `patient_request_emails.sql`.
2. Reuse the `patient_portal_project_url`, `patient_portal_publishable_key`, and `patient_portal_wellness_webhook_secret` Vault secrets described above. The Vault webhook secret must match the Edge Function `WELLNESS_WEBHOOK_SECRET`.
3. Keep the existing `RESEND_API_KEY` and `RESEND_FROM_EMAIL` Edge Function secrets configured; this function does not require Gemini.
4. Deploy the function from the repository root:

   ```powershell
   supabase functions deploy notify-appointment-status --project-ref <project-ref> --no-verify-jwt
   ```

The database trigger sends only status transitions to `Scheduled`, `Rescheduled`,
`Declined`, or `Cancelled`. Check Supabase Edge Function logs and Resend delivery
status when validating delivery.

Because the callback form accepts public submissions, add rate limiting or another anti-abuse control at the hosting/API layer before opening it to the public. The publishable key is expected to be visible in the browser; it is not a substitute for RLS or abuse protection.

## Run locally

From the repository root, start a static web server:

```powershell
py -m http.server 8000 --directory patient_portal
```

Open `http://localhost:8000`. Serving the folder over HTTP is needed for browser storage and API requests; do not open `index.html` directly as a file.

## Privacy behavior

- **“I don’t need help”** always saves the note in this browser first. Guests keep device-only entries for 30 days under `hfrc_guest_journal_entries`. Signed-in patients use a separate `hfrc_user_journal_<user-id>` cache and back up entries to their account; returning to an account reloads only that account's saved entries. Guest entries are never merged automatically; after signing in, use **Import to my account** to choose whether to back them up. Signing out immediately switches back to the guest list and clears account-specific portal and chatbot state. The former shared journal cache is partitioned by recorded owner and removed during migration.
- **“I need help”** sends the message, name, age, phone number, and selected callback schedule to the center’s Supabase project after consent. The request is visible to authorized staff in the admin app. Do not submit an emergency through this form.
- Guest callback requests receive a random, device-stored reference token so the guest can see response updates in the Notification Bell without creating an account. The token stays in this browser until explicitly imported to an account or browser data is cleared; do not share it.
- Every fifth locally saved guest Vent-Out entry can show an in-app wellness check-in. The check-in counts entries on this device only; journal text is not sent for it.
- **Import to my account** is voluntary: it imports guest journal entries and claims guest callback notifications for the currently signed-in account. Dismissing the banner leaves the guest data on this device.
- Sign-in is optional. Guest visitors can use the venting space and request a callback without creating an account.
- The selected callback time is a preference, not a confirmed booking. Staff confirm the time by phone.
- Callback times are offered Monday–Friday from 8:00 AM–11:30 AM and 1:00 PM–3:30 PM, Philippine time.
- Callback requests are stored in Supabase until staff handle them. Apply the center’s approved retention and privacy policy to those requests before deploying the portal publicly.
- Avoid leaving private entries on a shared device; remove them from the page or clear that browser’s site data when finished.

The former standalone Streamlit helpline has been retired; this portal is the
single public entry point.

Before public launch, configure the Supabase project and hosting origins, test with a non-production request, and have the center verify consent, access, retention, and emergency-contact wording.
