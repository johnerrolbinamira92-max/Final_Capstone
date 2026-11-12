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

For a new Supabase project, run [`../supabase/appointments.sql`](../supabase/appointments.sql)
and [`../supabase/patient_help_requests.sql`](../supabase/patient_help_requests.sql),
then run [`../supabase/appointment_lifecycle.sql`](../supabase/appointment_lifecycle.sql).
For an existing project, run [`../supabase/appointments_admin_fields.sql`](../supabase/appointments_admin_fields.sql)
once to add the optional appointment reason and permit the `Rescheduled` and
`No-show` statuses, run the patient help request script once if it has not
already been applied, and run [`../supabase/appointment_lifecycle.sql`](../supabase/appointment_lifecycle.sql).
The lifecycle script adds update timestamps and enables recent status updates,
including reschedules and no-show outcomes for patient help requests.

In the appointment calendar, **Completed** means the patient attended and
**No-show** means they did not. Past appointments appear in the history section,
where their attendance status can be updated.
Confirmation, reschedule, and cancellation notifications remain visible for 24
hours. Only confirmed and rescheduled visits appear as calendar events;
unconfirmed requests stay in the request list. Past visits appear below the
calendar until marked Done, Cancelled, or Did not come, and completed patient
help requests are included in appointment history.

## Offline regional dashboard and statistics

The **Overview** home page shows local patient totals and a regional breakdown
for all six Bicol provinces: Albay, Camarines Norte, Camarines Sur,
Catanduanes, Masbate, and Sorsogon. Its province-mix chart and optional map use
the bundled boundaries in `data/bicol_provinces.geojson`, so the regional
statistics work offline. Records without a recognized Bicol province are
excluded from the regional totals. The upcoming appointment card requires a
connection to Supabase.
The admin portal uses a fixed dark appearance across the login screen,
dashboard, forms, cards, and offline maps.
The Brothers of Charity mark used in the login panel and sidebar can be
replaced by placing an image at `admin_portal/assets/boc_logo.png`. To use
another path, set `BOC_LOGO_PATH` in the root `.env` file; relative paths are
resolved from the project root.
The Overview search field opens Search Records when a query is submitted with
Enter or when the **Search** button is clicked. Its notification bell opens the
Notifications page, and its **Add appointment** action opens the Calendar at
the scheduling form.

The **Patient statistics** page keeps the location filters for exploring records by
province, city / municipality, barangay, and purok, with patient counts and
distribution charts.

**Search Records** combines searching and record management. Search by patient
name, ID, or location, or filter by province, municipality / city, barangay,
gender, and age range. Select a result to view its complete local record, then
use the **Edit** or **Delete** actions. Deletion requires confirmation. The
Overview page's quick search opens this page with the query filled in.

**Appointments** and the **Notifications** feed use the same Supabase project.
Pending appointments created by the patient portal in the `appointments` table
will appear in the admin calendar and notification feed. **Notifications**
also reads pending patient help requests from Supabase. Admins can accept,
reschedule, or cancel pending requests from their details. Pending and
scheduled help requests appear on the calendar. The calendar metrics include
both tables and refresh automatically every 30 seconds; only requests marked
**Completed** count as visits. **Refresh data** reloads the metrics immediately
after a patient submits a request. Hovering over a calendar date shows visit
names; selecting a date shows each patient name with expandable details.

The **Schedules** tab shows appointment requests, and **Vent-out notes** uses
the message field from patient help requests; the database has no separate
vent-out-note table. Unread indicators are shown on the overview bell and
sidebar for new requests. Opening **Notifications** marks the current requests
as read, and read state persists in the local database per admin account.

**Activity History** records completed changes to patient records and
appointments: records added, edited, or deleted; appointments scheduled,
rescheduled, or cancelled; and appointment statuses or attendance outcomes
updated. Searches and navigation are not logged. The history is stored in the
local archive and displayed in Philippine Standard Time.

The Encode form's patient and guardian addresses use searchable, cascading
province, city / municipality, and barangay selectors. Their Bicol location
list is bundled in `data/bicol_address_hierarchy.json` for offline use. Admins
can type a location and press Enter when it is not in the list. The remaining
street, zone, and purok details can be entered after selecting or entering a
province.

Date of birth is entered with blank year, month, and day dropdowns. The year list
is searchable and covers 1900 through the current year; month and day options
adjust to the selected date, including leap years. Calculated age updates from
the selected birth date and is read-only. The interview date calendar allows
dates from 1900 through today, without future dates.

Boundary data: geoBoundaries Philippines administrative areas (2020), sourced
from NAMRIA, the Philippines Statistics Authority, and OCHA Philippines;
licensed under [CC BY 3.0 IGO](https://www.geoboundaries.org/). The bundled
GeoJSON data contains the Bicol province features used by the Overview map,
extracted from geoBoundaries simplified boundaries.

Address dropdown data: the bundled Bicol Region administrative hierarchy was
retrieved from the [PSGC API](https://psgc.gitlab.io/api/). It includes province,
city / municipality, and barangay names and codes.
