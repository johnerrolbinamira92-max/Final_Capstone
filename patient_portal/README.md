# Holy Face Center patient portal

This is a standalone, responsive patient portal. It is separate from the Streamlit admin app.

## Set up the callback form

1. In the Supabase SQL Editor for the same project as the admin app, run [`../supabase/patient_help_requests.sql`](../supabase/patient_help_requests.sql).
2. In Supabase **Project Settings → API**, copy the project URL and the **publishable** key (or legacy anon key).
3. Put those two public values in [`config.js`](./config.js). Never put a `service_role` or secret key in this folder.
4. The Streamlit admin app must keep using its server-side key in its private `.env` file. Open **Appointment Schedule → Confidential help requests** to review and update requests.

The database permits unauthenticated patients to insert consented requests only. The public key cannot read, change, or delete submitted requests. The admin app uses its private server-side key to read the queue. Do not grant public `SELECT` access to this table.

Because the callback form accepts public submissions, add rate limiting or another anti-abuse control at the hosting/API layer before opening it to the public. The publishable key is expected to be visible in the browser; it is not a substitute for RLS or abuse protection.

## Run locally

From the repository root, start a static web server:

```powershell
py -m http.server 8000 --directory patient_portal
```

Open `http://localhost:8000`. Serving the folder over HTTP is needed for browser storage and API requests; do not open `index.html` directly as a file.

## Privacy behavior

- **“I don’t need help”** saves the note in this browser’s local storage only. It is not sent to Supabase or the center. The portal removes it from the local list after 30 days; clearing browser data removes it sooner.
- **“I need help”** sends the message, name, age, phone number, and selected callback schedule to the center’s Supabase project after consent. The request is visible to authorized staff in the admin app. Do not submit an emergency through this form.
- The selected callback time is a preference, not a confirmed booking. Staff confirm the time by phone.
- Callback requests are stored in Supabase until staff handle them. Apply the center’s approved retention and privacy policy to those requests before deploying the portal publicly.
- Avoid leaving private entries on a shared device; remove them from the page or clear that browser’s site data when finished.

Before public launch, configure the Supabase project and hosting origins, test with a non-production request, and have the center verify consent, access, retention, and emergency-contact wording.
