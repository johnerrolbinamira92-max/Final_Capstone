import calendar
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from database import get_local_connection, get_supabase_client


ACTIVE_STATUSES = ("Pending", "Scheduled", "Rescheduled")
CALENDAR_STATUSES = ("Scheduled", "Rescheduled")
APPOINTMENT_STATUSES = (
    "Pending",
    "Scheduled",
    "Rescheduled",
    "Completed",
    "No-show",
    "Cancelled",
)
HELP_REQUEST_STATUSES = (
    "Pending",
    "Scheduled",
    "Rescheduled",
    "Completed",
    "No-show",
    "Cancelled",
)
WEEKDAY_LABELS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
APPOINTMENT_COLUMNS = [
    "appointment_id",
    "patient_id",
    "patient_name",
    "contact_number",
    "requested_date",
    "requested_time_slot",
    "approval_status",
    "reason",
]
PAGE_SIZE = 1000


def _month_offset(value, offset):
    month_index = value.year * 12 + value.month - 1 + offset
    year, month = divmod(month_index, 12)
    return date(year, month + 1, 1)


def _format_time(value):
    if value is None or pd.isna(value) or value == "":
        return "Time not set"
    for time_format in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(str(value), time_format).strftime("%I:%M %p").lstrip("0")
        except ValueError:
            continue
    return str(value)


def _format_received_at(value):
    if value is None or pd.isna(value) or not str(value).strip():
        return "Unknown"
    try:
        received_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=ZoneInfo("Asia/Manila"))
    else:
        received_at = received_at.astimezone(ZoneInfo("Asia/Manila"))
    time_label = received_at.strftime("%I:%M%p").lstrip("0").lower()
    return f"{received_at:%m/%d/%Y} - {time_label}"


def _format_optional(value):
    if value is None or pd.isna(value) or not str(value).strip():
        return "Not provided"
    return str(value)


def _appointment_datetime(appointment, *, now=None):
    now = now or datetime.now(ZoneInfo("Asia/Manila"))
    try:
        scheduled_date = date.fromisoformat(str(appointment.get("requested_date")))
    except (TypeError, ValueError):
        return None

    raw_time = appointment.get("requested_time_slot")
    if raw_time is None or pd.isna(raw_time) or not str(raw_time).strip():
        if scheduled_date < now.date():
            return datetime.combine(
                scheduled_date,
                time.max,
                tzinfo=ZoneInfo("Asia/Manila"),
            )
        return None

    scheduled_time = None
    for time_format in ("%H:%M:%S", "%H:%M"):
        try:
            scheduled_time = datetime.strptime(str(raw_time), time_format).time()
            break
        except ValueError:
            continue
    if scheduled_time is None:
        return None
    return datetime.combine(
        scheduled_date,
        scheduled_time,
        tzinfo=ZoneInfo("Asia/Manila"),
    )


def _load_appointments(client):
    records = []
    offset = 0
    while True:
        response = (
            client.table("appointments")
            .select(", ".join(APPOINTMENT_COLUMNS))
            .order("requested_date")
            .order("requested_time_slot")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        records.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    appointments = pd.DataFrame(records, columns=APPOINTMENT_COLUMNS)
    if appointments.empty:
        return appointments

    requested_dates = pd.to_datetime(appointments["requested_date"], errors="coerce")
    today = datetime.now(ZoneInfo("Asia/Manila")).date()
    appointments["_schedule_group"] = 2
    active = appointments["approval_status"].isin(ACTIVE_STATUSES)
    appointments.loc[active & (requested_dates.dt.date >= today), "_schedule_group"] = 0
    appointments.loc[active & (requested_dates.dt.date < today), "_schedule_group"] = 1
    appointments = appointments.sort_values(
        ["_schedule_group", "requested_date", "requested_time_slot", "patient_name"],
        kind="stable",
        na_position="last",
    ).drop(columns="_schedule_group")
    return appointments.reset_index(drop=True)


def _load_calendar_appointments(client, appointments=None):
    if appointments is None:
        appointments = _load_appointments(client)
    appointments = appointments.copy()
    appointments["event_source"] = "appointment"
    appointments["patient_age"] = None
    appointments["message"] = None

    request_records = []
    offset = 0
    while True:
        response = (
            client.table("patient_help_requests")
            .select(
                "request_id, patient_name, patient_age, contact_number, message, "
                "requested_date, requested_time_slot, approval_status, created_at"
            )
            .in_("approval_status", list(HELP_REQUEST_STATUSES))
            .order("requested_date")
            .order("requested_time_slot")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        request_records.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    request_rows = [
        {
            "appointment_id": f"help_request:{request['request_id']}",
            "patient_id": None,
            "patient_name": request.get("patient_name"),
            "contact_number": request.get("contact_number"),
            "requested_date": request.get("requested_date"),
            "requested_time_slot": request.get("requested_time_slot"),
            "approval_status": request.get("approval_status"),
            "reason": request.get("message"),
            "event_source": "help_request",
            "patient_age": request.get("patient_age"),
            "message": request.get("message"),
            "created_at": request.get("created_at"),
        }
        for request in request_records
    ]
    if not request_rows:
        return appointments

    return pd.concat(
        [appointments, pd.DataFrame(request_rows)],
        ignore_index=True,
    )


def _appointment_summary_counts(appointments, today):
    if appointments.empty:
        return {
            "today": 0,
            "scheduled_today": 0,
            "pending": 0,
            "month": 0,
        }

    requested_dates = pd.to_datetime(
        appointments["requested_date"], errors="coerce"
    )
    active = appointments["approval_status"].isin(CALENDAR_STATUSES)
    completed = appointments["approval_status"].eq("Completed")
    today_count = int((completed & requested_dates.dt.date.eq(today)).sum())
    scheduled_today_count = int(
        (active & requested_dates.dt.date.eq(today)).sum()
    )
    in_month = (
        requested_dates.dt.year.eq(today.year)
        & requested_dates.dt.month.eq(today.month)
    )
    month_count = int((completed & in_month).sum())
    pending_count = int(appointments["approval_status"].eq("Pending").sum())
    return {
        "today": today_count,
        "scheduled_today": scheduled_today_count,
        "pending": pending_count,
        "month": month_count,
    }


def _load_appointment_summary_counts(client, today):
    records = []
    for table_name in ("appointments", "patient_help_requests"):
        offset = 0
        while True:
            response = (
                client.table(table_name)
                .select("requested_date, approval_status")
                .in_("approval_status", [*ACTIVE_STATUSES, "Completed"])
                .range(offset, offset + PAGE_SIZE - 1)
                .execute()
            )
            page = response.data or []
            records.extend(page)
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

    active_visits = pd.DataFrame(
        records,
        columns=["requested_date", "approval_status"],
    )
    return _appointment_summary_counts(active_visits, today)


@st.fragment(run_every="30s")
def _render_appointment_metrics(client, initial_appointments, today):
    if not st.session_state.get("appointment_metrics_initialized"):
        counts = _appointment_summary_counts(initial_appointments, today)
        st.session_state["appointment_metrics_initialized"] = True
    else:
        try:
            counts = _load_appointment_summary_counts(client, today)
        except Exception as error:
            st.error("Unable to refresh appointment counts from Supabase.")
            with st.expander("Technical details"):
                st.code(str(error))
            return

    metrics = st.columns(3)
    metrics[0].metric("Visits today", counts["today"], border=True)
    metrics[1].metric("Pending requests", counts["pending"], border=True)
    metrics[2].metric(
        "Active visits this month",
        counts["month"],
        border=True,
    )


def _render_calendar(appointments, selected_date):
    month_state_key = "appointment_calendar_month"
    if month_state_key not in st.session_state:
        st.session_state[month_state_key] = selected_date.replace(day=1)

    month_start = st.session_state[month_state_key]
    today_col, previous_col, title_col, next_col = st.columns([1.3, 1, 4, 1])
    with today_col:
        if st.button("Today", key="appointment_today"):
            today = datetime.now(ZoneInfo("Asia/Manila")).date()
            st.session_state[month_state_key] = today.replace(day=1)
            st.session_state["appointment_selected_date"] = today
            st.session_state["appointment_form_date"] = today
            st.rerun()
    with previous_col:
        if st.button(
            " ",
            icon=":material/chevron_left:",
            key="appointment_previous_month",
            help="Show the previous month",
        ):
            st.session_state[month_state_key] = _month_offset(month_start, -1)
            st.rerun()
    with title_col:
        st.markdown(f"### {month_start.strftime('%B %Y')}")
    with next_col:
        if st.button(
            " ",
            icon=":material/chevron_right:",
            key="appointment_next_month",
            help="Show the next month",
        ):
            st.session_state[month_state_key] = _month_offset(month_start, 1)
            st.rerun()

    active_by_date = {}
    if not appointments.empty:
        confirmed_appointments = appointments[
            appointments["approval_status"].isin(CALENDAR_STATUSES)
        ]
        confirmed_by_date = {
            requested_date: day_appointments
            for requested_date, day_appointments in confirmed_appointments.groupby(
                "requested_date", dropna=True
            )
        }

    weekday_columns = st.columns(7)
    for column, label in zip(weekday_columns, WEEKDAY_LABELS):
        with column:
            st.caption(f"**{label}**")

    month_rows = calendar.Calendar(firstweekday=calendar.SUNDAY).monthdayscalendar(
        month_start.year, month_start.month
    )
    for week_index, week in enumerate(month_rows):
        day_columns = st.columns(7)
        for day_index, (column, day_number) in enumerate(zip(day_columns, week)):
            with column:
                if not day_number:
                    st.markdown(
                        '<div class="appointment-calendar-empty-day"></div>',
                        unsafe_allow_html=True,
                    )
                    continue

                day_date = date(month_start.year, month_start.month, day_number)
                day_key = day_date.isoformat()
                day_appointments = confirmed_by_date.get(day_key)
                appointment_count = (
                    len(day_appointments) if day_appointments is not None else 0
                )
                label = (
                    f"{day_number}\n● {appointment_count} visit(s)"
                    if appointment_count
                    else str(day_number)
                )
                tooltip = (
                    f"{appointment_count} confirmed or rescheduled appointment(s)"
                )
                if appointment_count:
                    patient_names = day_appointments["patient_name"].fillna(
                        "Patient"
                    )
                    tooltip += ":\n" + "\n".join(
                        f"- {name}" for name in patient_names
                    )
                else:
                    tooltip = (
                        f"Select {day_date.strftime('%B')} {day_number}, "
                        f"{day_date.year}"
                    )
                if st.button(
                    label,
                    key=f"appointment_day_{day_key}",
                    type="primary" if day_date == selected_date else "secondary",
                    width="stretch",
                    help=tooltip,
                ):
                    st.session_state["appointment_selected_date"] = day_date
                    st.session_state["appointment_form_date"] = day_date
                    st.rerun()

    st.caption(
        "● indicates one or more confirmed or rescheduled visits. "
        "Select a date to schedule a visit."
    )


def _render_selected_day(appointments, selected_date):
    if appointments.empty:
        day_appointments = appointments
    else:
        day_appointments = appointments[
            appointments["requested_date"] == selected_date.isoformat()
        ]

    display_date = (
        f"{selected_date.strftime('%A, %B')} {selected_date.day}, {selected_date.year}"
    )
    st.markdown("#### Selected day")
    st.markdown(f"### {display_date}")
    if day_appointments.empty:
        st.info("No appointments are recorded for this date yet.")
    else:
        confirmed_day_appointments = day_appointments[
            day_appointments["approval_status"].isin(CALENDAR_STATUSES)
        ]
        day_appointments = confirmed_day_appointments
        st.caption(
            f"{len(confirmed_day_appointments)} confirmed or rescheduled "
            "appointment(s) on this date."
        )
        if day_appointments.empty:
            st.info("No confirmed appointments are recorded for this date.")
            return
        for index, appointment in enumerate(day_appointments.to_dict(orient="records")):
            patient_name = str(appointment.get("patient_name") or "Patient")
            with st.expander(
                patient_name,
                key=f"appointment-selected-details-{index}",
            ):
                st.caption(
                    f"{_format_time(appointment.get('requested_time_slot'))}"
                )
                st.badge(
                    str(appointment.get("approval_status") or "Pending"),
                    color="blue",
                )
                st.text(
                    f"Contact: {_format_optional(appointment.get('contact_number'))}"
                )
                if appointment.get("event_source") == "help_request":
                    st.text("Request type: Patient Help Request")
                    age = appointment.get("patient_age")
                    if age is not None and not pd.isna(age):
                        st.text(f"Age: {age}")
                    message = appointment.get("message")
                    if message and not pd.isna(message):
                        st.text(f"Message: {message}")
                    received_at = appointment.get("created_at")
                    if received_at is not None and not pd.isna(received_at):
                        st.text(
                            f"Received: {_format_received_at(received_at)}"
                        )
                else:
                    st.text(
                        f"Patient app ID: "
                        f"{_format_optional(appointment.get('patient_id'))}"
                    )
                    reason = _format_optional(appointment.get("reason"))
                    if reason != "Not provided":
                        st.text(f"Reason: {reason}")


def _render_appointment_history(appointments, client, today):
    st.markdown("#### Appointment history")
    st.caption(
        "Completed means the patient attended; No-show means they did not attend. "
        "Past appointments without an outcome remain visible until updated."
    )
    if appointments.empty:
        st.info("There is no appointment history yet.")
        return

    past_dates = appointments["requested_date"].astype(str) < today.isoformat()
    final_statuses = appointments["approval_status"].isin(
        ("Completed", "No-show", "Cancelled")
    )
    history = appointments[past_dates | final_statuses].copy()
    if history.empty:
        st.info("There is no appointment history yet.")
        return

    history["Date"] = history["requested_date"].map(
        lambda value: date.fromisoformat(str(value)).strftime("%b %d, %Y")
        if value
        else "Date not set"
    )
    history["Time"] = history["requested_time_slot"].map(_format_time)
    history["Attendance / status"] = history["approval_status"].replace(
        {"Completed": "Attended", "No-show": "Did not attend"}
    )
    history["Reason"] = history["reason"].fillna("")
    history = history.sort_values(
        ["requested_date", "requested_time_slot", "patient_name"],
        ascending=[False, False, True],
        kind="stable",
        na_position="last",
    )
    st.dataframe(
        history[
            [
                "Date",
                "Time",
                "patient_name",
                "contact_number",
                "Reason",
                "Attendance / status",
            ]
        ].rename(
            columns={
                "patient_name": "Patient",
                "contact_number": "Contact",
            }
        ),
        hide_index=True,
        width="stretch",
        alt="Past appointments and attendance outcomes",
    )

    for appointment in history.to_dict(orient="records"):
        appointment_id = appointment["appointment_id"]
        status = appointment.get("approval_status") or "Pending"
        with st.expander(
            f"{appointment['patient_name']} · {appointment['requested_date']} "
            f"· {status}"
        ):
            st.write(f"**Contact:** {appointment.get('contact_number') or 'Not provided'}")
            st.write(f"**Reason:** {_format_optional(appointment.get('reason'))}")
            statuses = list(APPOINTMENT_STATUSES)
            if status not in statuses:
                statuses.insert(0, status)
            selected_status = st.selectbox(
                "Attendance / appointment status",
                statuses,
                index=statuses.index(status),
                key=f"appointment_history_status_{appointment_id}",
            )
            if st.button(
                "Save attendance",
                key=f"appointment_history_save_{appointment_id}",
                disabled=selected_status == status,
            ):
                try:
                    is_help_request = (
                        appointment.get("event_source") == "help_request"
                    )
                    table_name = (
                        "patient_help_requests"
                        if is_help_request
                        else "appointments"
                    )
                    id_column = (
                        "request_id" if is_help_request else "appointment_id"
                    )
                    record_id = (
                        str(appointment_id).removeprefix("help_request:")
                        if is_help_request
                        else appointment_id
                    )
                    updated = (
                        client.table(table_name)
                        .update({"approval_status": selected_status})
                        .eq(id_column, record_id)
                        .select(id_column)
                        .execute()
                    )
                    if not updated.data:
                        raise RuntimeError("No matching appointment was updated.")
                except Exception as error:
                    st.error(f"Unable to save the attendance outcome: {error}")
                else:
                    try:
                        _log_appointment_action(
                            "APPOINTMENT OUTCOME",
                            f"{appointment.get('patient_name') or 'Patient'}: "
                            f"{selected_status} on "
                            f"{appointment.get('requested_date') or 'date not set'} "
                            f"at {_format_time(appointment.get('requested_time_slot'))}.",
                        )
                    except Exception as error:
                        st.warning(
                            "The appointment was updated, but its local audit entry "
                            f"could not be written: {error}"
                        )
                    st.session_state["appointment_flash"] = (
                        f"Appointment outcome updated to {selected_status}."
                    )
                    st.rerun()


def _update_appointment_outcome(client, appointment, status):
    help_request = appointment.get("event_source") == "help_request"
    table_name = "patient_help_requests" if help_request else "appointments"
    id_column = "request_id" if help_request else "appointment_id"
    record_id = (
        str(appointment["appointment_id"]).removeprefix("help_request:")
        if help_request
        else appointment["appointment_id"]
    )
    try:
        response = (
            client.table(table_name)
            .update({"approval_status": status})
            .eq(id_column, record_id)
            .select(id_column)
            .execute()
        )
        if not response.data:
            raise RuntimeError("No matching appointment was updated.")
    except Exception as error:
        st.error("Unable to save this appointment outcome in Supabase.")
        with st.expander("Technical details"):
            st.code(str(error))
        return False

    try:
        _log_appointment_action(
            "APPOINTMENT OUTCOME",
            f"{appointment.get('patient_name') or 'Patient'}: {status} on "
            f"{appointment.get('requested_date') or 'date not set'} at "
            f"{_format_time(appointment.get('requested_time_slot'))}.",
        )
    except Exception as error:
        st.warning(
            "The appointment outcome was saved, but its local activity entry "
            f"could not be written: {error}"
        )
    st.session_state["appointment_flash"] = (
        f"Appointment outcome recorded as "
        f"{'Did not come' if status == 'No-show' else status}."
    )
    st.rerun()
    return True


def _render_awaiting_outcomes(appointments, client, *, now=None):
    now = now or datetime.now(ZoneInfo("Asia/Manila"))
    st.markdown("### Visits awaiting outcome")
    st.caption(
        "Appointments remain here after their scheduled time until you mark "
        "them done, cancelled, or as a no-show."
    )
    if appointments.empty:
        st.info("There are no visits awaiting an outcome.")
        return

    waiting = []
    for appointment in appointments.to_dict(orient="records"):
        if appointment.get("approval_status") not in CALENDAR_STATUSES:
            continue
        scheduled_at = _appointment_datetime(appointment, now=now)
        if scheduled_at is not None and scheduled_at <= now:
            waiting.append((scheduled_at, appointment))

    waiting.sort(
        key=lambda item: (
            item[0],
            str(item[1].get("patient_name") or "").casefold(),
        ),
        reverse=True,
    )
    if not waiting:
        st.info("There are no past scheduled visits awaiting an outcome.")
        return

    for scheduled_at, appointment in waiting:
        patient_name = appointment.get("patient_name") or "Patient"
        identity = appointment.get("appointment_id")
        if pd.isna(identity):
            identity = patient_name
        row_key = str(identity).replace(":", "-")
        with st.container(border=True, key=f"appointment-outcome-{row_key}"):
            st.markdown(f"**{patient_name}**")
            st.caption(
                f"{scheduled_at:%b %d, %Y} · "
                f"{_format_time(appointment.get('requested_time_slot'))}"
            )
            done_column, cancel_column, no_show_column = st.columns(3)
            if done_column.button(
                "Done",
                key=f"appointment-outcome-done-{row_key}",
                icon=":material/check_circle:",
                width="stretch",
            ):
                _update_appointment_outcome(client, appointment, "Completed")
            if cancel_column.button(
                "Cancel",
                key=f"appointment-outcome-cancel-{row_key}",
                icon=":material/event_busy:",
                width="stretch",
            ):
                _update_appointment_outcome(client, appointment, "Cancelled")
            if no_show_column.button(
                "Did not come",
                key=f"appointment-outcome-no-show-{row_key}",
                icon=":material/person_off:",
                width="stretch",
            ):
                _update_appointment_outcome(client, appointment, "No-show")


def _log_appointment_action(action_type, details):
    conn = get_local_connection()
    try:
        with conn:
            conn.execute(
                "INSERT INTO admin_logs (action_type, details) VALUES (?, ?)",
                (action_type, details),
            )
    finally:
        conn.close()


def _render_schedule_form(client):
    st.markdown("### Set an appointment")
    st.caption(
        "Patient-app requests appear here with Pending status. "
        "Appointments entered by an admin are saved as Scheduled."
    )
    with st.form("schedule_appointment_form"):
        patient_column, schedule_column = st.columns(2)
        with patient_column:
            patient_name = st.text_input(
                "Patient name",
                key="appointment_form_patient_name",
            ).strip()
            patient_id = st.text_input(
                "Patient app ID (optional)",
                key="appointment_form_patient_id",
                help="Use the patient ID from the connected patient app when available.",
            ).strip()
            contact_number = st.text_input(
                "Contact number",
                key="appointment_form_contact",
            ).strip()
        with schedule_column:
            visit_date = st.date_input(
                "Visit date",
                key="appointment_form_date",
                format="MM/DD/YYYY",
            )
            visit_time = st.time_input(
                "Visit time (Philippine time)",
                key="appointment_form_time",
                format="12h",
            )
        reason = st.text_area(
            "Notes / reason for visit (optional)",
            key="appointment_form_reason",
            max_chars=500,
            help="Keep this brief. Do not include sensitive clinical details.",
        ).strip()
        submitted = st.form_submit_button(
            "Schedule appointment",
            type="primary",
            icon=":material/event_available:",
        )

    if not submitted:
        return
    if not patient_name:
        st.error("Enter the patient's name before scheduling.")
        return
    if visit_date is None or visit_time is None:
        st.error("Choose both a visit date and time.")
        return

    appointment_time = visit_time.strftime("%H:%M:%S")
    try:
        response = (
            client.table("appointments")
            .insert(
                {
                    "patient_id": patient_id or None,
                    "patient_name": patient_name,
                    "contact_number": contact_number or None,
                    "requested_date": visit_date.isoformat(),
                    "requested_time_slot": appointment_time,
                    "approval_status": "Scheduled",
                    "reason": reason or None,
                }
            )
            .select("appointment_id")
            .execute()
        )
        if not response.data:
            raise RuntimeError(
                "Supabase did not return the created appointment. "
                "Check the table permissions and INSERT policy."
            )
        appointment_id = response.data[0]["appointment_id"]
    except Exception as error:
        st.error(
            "Unable to save the appointment to Supabase. Verify the project URL, "
            "appointments table, and INSERT permissions."
        )
        with st.expander("Technical details"):
            st.code(str(error))
        return

    try:
        _log_appointment_action(
            "APPOINTMENT SCHEDULED",
            f"Scheduled {patient_name} for {visit_date.isoformat()} at "
            f"{_format_time(appointment_time)}.",
        )
    except Exception as error:
        st.warning(
            "The appointment was saved to Supabase, but its local audit entry "
            f"could not be written: {error}"
        )

    st.session_state["appointment_flash"] = (
        f"Appointment for {patient_name} scheduled successfully."
    )
    st.session_state["appointment_selected_date"] = visit_date
    st.session_state["appointment_calendar_month"] = visit_date.replace(day=1)
    st.session_state["appointment_reset_form"] = True
    st.rerun()


def _render_schedule_list(appointments, client):
    if appointments.empty:
        st.info("No appointments have been scheduled yet.")
        return

    st.caption("Patient-app requests and admin-scheduled visits are shown together.")
    status_filter = st.selectbox(
        "Show appointments",
        ["All statuses", *APPOINTMENT_STATUSES],
        key="appointment_status_filter",
    )
    visible = appointments.copy()
    if status_filter != "All statuses":
        visible = visible[visible["approval_status"] == status_filter]

    search_text = st.text_input(
        "Filter by patient name",
        key="appointment_name_filter",
    ).strip()
    if search_text:
        visible = visible[
            visible["patient_name"].str.contains(search_text, case=False, na=False)
        ]

    if visible.empty:
        st.info("No appointments match those filters.")
        return

    for appointment in visible.to_dict(orient="records"):
        try:
            appointment_date = date.fromisoformat(appointment["requested_date"])
            display_date = (
                f"{appointment_date.strftime('%b')} "
                f"{appointment_date.day}, {appointment_date.year}"
            )
        except (TypeError, ValueError):
            display_date = appointment["requested_date"] or "Date not set"
        display_time = _format_time(appointment["requested_time_slot"])
        status = appointment["approval_status"] or "Pending"
        with st.expander(
            f"{display_date} · {display_time}  |  "
            f"{appointment['patient_name']}  |  {status}"
        ):
            col_patient, col_contact = st.columns(2)
            with col_patient:
                st.write(f"**Patient:** {appointment['patient_name']}")
                st.write(f"**Patient app ID:** {appointment['patient_id'] or 'Not linked'}")
                st.write(f"**Status:** {status}")
                reason = _format_optional(appointment.get("reason"))
                if reason != "Not provided":
                    st.write(f"**Reason:** {reason}")
            with col_contact:
                st.write(f"**Contact:** {appointment['contact_number'] or 'Not provided'}")

            appointment_id = appointment["appointment_id"]
            statuses = list(APPOINTMENT_STATUSES)
            if status not in statuses:
                statuses.insert(0, status)
            selected_status = st.selectbox(
                "Update status",
                statuses,
                index=statuses.index(status),
                key=f"appointment_status_{appointment_id}",
            )
            if st.button(
                "Save status",
                key=f"appointment_save_status_{appointment_id}",
                disabled=selected_status == status,
            ):
                try:
                    response = (
                        client.table("appointments")
                        .update({"approval_status": selected_status})
                        .eq("appointment_id", appointment_id)
                        .select("appointment_id")
                        .execute()
                    )
                    if not response.data:
                        raise RuntimeError(
                            "No appointment was updated. Check the appointment ID "
                            "and UPDATE permissions."
                        )
                except Exception as error:
                    st.error(
                        "Unable to update the appointment in Supabase. Verify "
                        "the project URL, appointment, and UPDATE permissions."
                    )
                    with st.expander("Technical details"):
                        st.code(str(error))
                else:
                    action_type = {
                        "Scheduled": "APPOINTMENT SCHEDULED",
                        "Cancelled": "APPOINTMENT CANCELLED",
                        "Completed": "APPOINTMENT OUTCOME",
                        "No-show": "APPOINTMENT OUTCOME",
                    }.get(selected_status, "APPOINTMENT STATUS")
                    try:
                        _log_appointment_action(
                            action_type,
                            f"{appointment.get('patient_name') or 'Patient'}: "
                            f"status changed from {status} to {selected_status} "
                            f"for {appointment.get('requested_date') or 'date not set'} "
                            f"at {_format_time(appointment.get('requested_time_slot'))}.",
                        )
                    except Exception as error:
                        st.warning(
                            "The online status was updated, but its local audit "
                            f"entry could not be written: {error}"
                        )
                    st.session_state["appointment_flash"] = (
                        f"Appointment status updated to {selected_status}."
                    )
                    st.rerun()


def _render_help_requests(client):
    st.caption(
        "Messages in this queue were explicitly sent by patients asking for help. "
        "Keep them confidential and contact the patient using their selected schedule."
    )
    try:
        response = (
            client.table("patient_help_requests")
            .select(
                "request_id, patient_name, patient_age, contact_number, message, "
                "requested_date, requested_time_slot, approval_status, created_at"
            )
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
    except Exception as error:
        st.error(
            "Unable to load confidential help requests. Run "
            "supabase/patient_help_requests.sql and verify that the admin app uses "
            "a server-side Supabase service-role/secret key."
        )
        with st.expander("Technical details"):
            st.code(str(error))
        return

    requests = response.data or []
    if not requests:
        st.info("There are no confidential help requests yet.")
        return

    st.caption(f"{len(requests)} most recent request(s), newest first.")
    for request in requests:
        request_id = request["request_id"]
        status = request["approval_status"] or "Pending"
        requested_date = request.get("requested_date") or "Date not set"
        requested_time = _format_time(request.get("requested_time_slot"))
        with st.expander(
            f"Callback requested: {requested_date} · {requested_time}  |  {status}"
        ):
            patient_col, schedule_col = st.columns(2)
            with patient_col:
                st.text(f"Patient: {request['patient_name']}")
                st.text(f"Age: {request['patient_age']}")
                st.text(f"Contact: {request['contact_number']}")
            with schedule_col:
                st.text(f"Requested callback: {requested_date} · {requested_time}")
                st.text(
                    f"Received: {_format_received_at(request.get('created_at'))}"
                )
                st.text(f"Status: {status}")

            st.markdown("**Message from the patient**")
            st.text(request["message"])

            statuses = list(HELP_REQUEST_STATUSES)
            if status not in statuses:
                statuses.insert(0, status)
            selected_status = st.selectbox(
                "Update request status",
                statuses,
                index=statuses.index(status),
                key=f"help_request_status_{request_id}",
            )
            if st.button(
                "Save request status",
                key=f"help_request_save_status_{request_id}",
                disabled=selected_status == status,
            ):
                try:
                    updated = (
                        client.table("patient_help_requests")
                        .update({"approval_status": selected_status})
                        .eq("request_id", request_id)
                        .select("request_id")
                        .execute()
                    )
                    if not updated.data:
                        raise RuntimeError(
                            "No help request was updated. Check the request ID "
                            "and UPDATE permissions."
                        )
                except Exception as error:
                    st.error("Unable to update the confidential request status.")
                    with st.expander("Technical details"):
                        st.code(str(error))
                else:
                    action_type = {
                        "Scheduled": "APPOINTMENT SCHEDULED",
                        "Cancelled": "APPOINTMENT CANCELLED",
                        "Completed": "APPOINTMENT OUTCOME",
                        "No-show": "APPOINTMENT OUTCOME",
                    }.get(selected_status, "HELP REQUEST STATUS")
                    try:
                        _log_appointment_action(
                            action_type,
                            f"{request.get('patient_name') or 'Patient'}: "
                            f"help request status changed from {status} to "
                            f"{selected_status} for {requested_date} at "
                            f"{requested_time}.",
                        )
                    except Exception as error:
                        st.warning(
                            "The request status was updated, but its local audit "
                            f"entry could not be written: {error}"
                        )
                    st.session_state["appointment_flash"] = (
                        f"Help request status updated to {selected_status}."
                    )
                    st.rerun()


def show_appointments_page():
    with st.container(key="admin-calendar-page"):
        st.markdown(
            '<div class="calendar-eyebrow">Appointment management</div>',
            unsafe_allow_html=True,
        )
        title_column, action_column = st.columns(
            [3, 1], vertical_alignment="center"
        )
        with title_column:
            st.markdown("# Calendar")
            st.write(
                "Plan and manage patient appointments. Dates and times use "
                "Philippine local time."
            )
        with action_column:
            if st.button(
                "Refresh data",
                icon=":material/refresh:",
                width="stretch",
                key="appointment_refresh_data",
            ):
                st.rerun()

            if st.button(
                "Set an appointment",
                type="primary",
                icon=":material/add:",
                width="stretch",
                key="appointment_jump_to_form",
            ):
                st.query_params["focus"] = "schedule"
                st.rerun()

        client = get_supabase_client()
        if client is None:
            return

        try:
            appointments = _load_appointments(client)
            calendar_appointments = _load_calendar_appointments(
                client, appointments
            )
        except Exception as error:
            st.error(
                "Unable to load the appointment calendar from Supabase. Check the "
                "project API URL, run the appointment and patient-help-request SQL "
                "setup scripts, and verify SELECT permissions."
            )
            with st.expander("Technical details"):
                st.code(str(error))
            return

        today = datetime.now(ZoneInfo("Asia/Manila")).date()
        if "appointment_selected_date" not in st.session_state:
            st.session_state["appointment_selected_date"] = today
        if "appointment_form_date" not in st.session_state:
            st.session_state["appointment_form_date"] = st.session_state[
                "appointment_selected_date"
            ]
        if "appointment_form_time" not in st.session_state:
            st.session_state["appointment_form_time"] = time(9, 0)
        if st.session_state.pop("appointment_reset_form", False):
            st.session_state["appointment_form_patient_id"] = ""
            st.session_state["appointment_form_patient_name"] = ""
            st.session_state["appointment_form_contact"] = ""
            st.session_state["appointment_form_reason"] = ""
            st.session_state["appointment_form_time"] = time(9, 0)

        if "appointment_form_patient_id" not in st.session_state:
            st.session_state["appointment_form_patient_id"] = ""
        if "appointment_form_patient_name" not in st.session_state:
            st.session_state["appointment_form_patient_name"] = ""
        if "appointment_form_contact" not in st.session_state:
            st.session_state["appointment_form_contact"] = ""
        if "appointment_form_reason" not in st.session_state:
            st.session_state["appointment_form_reason"] = ""

        if "appointment_flash" in st.session_state:
            st.success(st.session_state.pop("appointment_flash"))

        _render_appointment_metrics(client, calendar_appointments, today)

        with st.container(key="appointment-calendar-content"):
            selected_date = st.session_state["appointment_selected_date"]
            with st.container(key="appointment-calendar-layout"):
                calendar_column, selected_day_column = st.columns(
                    [1.8, 0.9], gap="medium"
                )
                with calendar_column:
                    with st.container(
                        border=True, key="appointment-calendar-panel"
                    ):
                        _render_calendar(calendar_appointments, selected_date)
                with selected_day_column:
                    with st.container(
                        border=True, key="appointment-selected-day-panel"
                    ):
                        _render_selected_day(calendar_appointments, selected_date)

            with st.container(border=True, key="appointment-outcome-queue"):
                _render_awaiting_outcomes(calendar_appointments, client)

            with st.container(border=True, key="appointment-setting"):
                _render_schedule_form(client)
            with st.container(border=True):
                _render_appointment_history(calendar_appointments, client, today)

        if st.query_params.get("focus") == "schedule":
            st.html(
                """
                <script>
                requestAnimationFrame(() => requestAnimationFrame(() => {
                  document.querySelector(".st-key-appointment-setting")
                    ?.scrollIntoView({ behavior: "smooth", block: "center" });
                }));
                </script>
                """,
                unsafe_allow_javascript=True,
            )
            st.query_params.pop("focus", None)


if __name__ == "__main__":
    show_appointments_page()
