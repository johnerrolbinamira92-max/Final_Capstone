# Admin portal

Run the Streamlit admin app from the repository root:

```powershell
streamlit run admin_portal/app.py
```

## Supabase credentials

The admin app reads its configuration from `.env` in the repository root,
regardless of the current working directory. If it does not exist, create it
from the template:

```powershell
Copy-Item .env.example .env
```

Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_KEY` in `.env` to the
values for your Supabase project. Keep the service-role/secret key private; do
not put it in `patient_portal/config.js` or commit `.env`.

## Create the single admin account

1. In Supabase, open **Authentication → Users** and create the admin user with
   an email address you control and a strong password. The app login expects
   that full email address.
2. Run [`../supabase/admin_users.sql`](../supabase/admin_users.sql) in the
   Supabase SQL Editor.
3. In **Authentication → Users**, copy the user's **UID**. If it is not shown
   in the table, open the user's details to view or copy the UID.
4. In the SQL Editor, authorize that account by running this query with its UID:

   ```sql
   insert into public.admin_users (user_id, display_name)
   values ('PASTE-THE-USER-UID-HERE', 'Administrator')
   on conflict (user_id) do update
   set display_name = excluded.display_name;
   ```

The UID belongs in Supabase's `admin_users` table, not in application source
code or `.env`. Never share the account password or service-role key.

## Appointment calendar setup

For a new Supabase project, run [`../supabase/appointments.sql`](../supabase/appointments.sql).
For an existing project, run [`../supabase/appointments_admin_fields.sql`](../supabase/appointments_admin_fields.sql)
once to add the optional appointment reason and permit the `No-show` attendance
status.

In the appointment calendar, **Completed** means the patient attended and
**No-show** means they did not. Past appointments appear in the history section,
where their attendance status can be updated.
