import calendar
from datetime import date, datetime, time
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from database import get_local_connection, get_supabase_client


ACTIVE_STATUSES = ("Pending", "Scheduled")
APPOINTMENT_STATUSES = ("Pending", "Scheduled", "Completed", "No-show", "Cancelled")
HELP_REQUEST_STATUSES = ("Pending", "Scheduled", "Completed", "Cancelled")
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


def _format_optional(value):
    if value is None or pd.isna(value) or not str(value).strip():
        return "Not provided"
    return str(value)


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

    active_counts = {}
    if not appointments.empty:
        active_appointments = appointments[
            appointments["approval_status"].isin(ACTIVE_STATUSES)
        ]
        active_counts = active_appointments["requested_date"].value_counts().to_dict()

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
                appointment_count = int(active_counts.get(day_key, 0))
                label = (
                    f"{day_number}\n● {appointment_count} visit(s)"
                    if appointment_count
                    else str(day_number)
                )
                if st.button(
                    label,
                    key=f"appointment_day_{day_key}",
                    type="primary" if day_date == selected_date else "secondary",
                    width="stretch",
                    help=(
                        f"{appointment_count} pending or scheduled appointment(s)"
                        if appointment_count
                        else f"Select {day_date.strftime('%B')} {day_number}, {day_date.year}"
                    ),
                ):
                    st.session_state["appointment_selected_date"] = day_date
                    st.session_state["appointment_form_date"] = day_date
                    st.rerun()

    st.caption(
        "● indicates one or more pending or scheduled visits. "
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
        active_day_appointments = day_appointments[
            day_appointments["approval_status"].isin(ACTIVE_STATUSES)
        ]
        st.caption(
            f"{len(active_day_appointments)} active appointment(s) on this date."
        )
        for index, appointment in enumerate(day_appointments.to_dict(orient="records")):
            with st.container(key=f"appointment-selected-row-{index}"):
                st.markdown(
                    f'<div class="appointment-selected-time">'
                    f'{escape(_format_time(appointment.get("requested_time_slot")))}</div>'
                    f'<div class="appointment-selected-name">'
                    f'{escape(str(appointment.get("patient_name") or "Patient"))}</div>'
                    f'<div class="appointment-selected-status">'
                    f'{escape(str(appointment.get("approval_status") or "Pending"))}'
                    f"</div>",
                    unsafe_allow_html=True,
                )


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
            ["Date", "Time", "patient_name", "contact_number", "Reason", "Attendance / status"]
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
                    updated = (
                        client.table("appointments")
                        .update({"approval_status": selected_status})
                        .eq("appointment_id", appointment_id)
                        .select("appointment_id")
                        .execute()
                    )
                    if not updated.data:
                        raise RuntimeError("No matching appointment was updated.")
                except Exception as error:
                    st.error(f"Unable to save the attendance outcome: {error}")
                else:
                    try:
                        _log_appointment_action(
                            "APPOINTMENT ATTENDANCE",
                            f"Updated appointment {appointment_id} to {selected_status}",
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
            "SCHEDULE",
            f"Created online appointment {appointment_id} for "
            f"{visit_date.isoformat()} at {_format_time(appointment_time)}",
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
                    try:
                        _log_appointment_action(
                            "APPOINTMENT STATUS",
                            f"Updated online appointment {appointment_id} to {selected_status}",
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
                st.text(f"Received: {request.get('created_at', 'Unknown')}")
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
                    try:
                        _log_appointment_action(
                            "HELP REQUEST STATUS",
                            f"Updated confidential help request {request_id} "
                            f"to {selected_status}",
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
        except Exception as error:
            st.error(
                "Unable to load appointments from Supabase. Check the project API URL, "
                "run supabase/appointments.sql and "
                "supabase/appointments_admin_fields.sql, and verify SELECT permissions."
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

        this_month = appointments[
            appointments["requested_date"].astype(str).str.startswith(
                today.strftime("%Y-%m"), na=False
            )
        ] if not appointments.empty else appointments
        active_today = appointments[
            (appointments["requested_date"].astype(str) == today.isoformat())
            & appointments["approval_status"].isin(ACTIVE_STATUSES)
        ] if not appointments.empty else appointments
        active_month = this_month[
            this_month["approval_status"].isin(ACTIVE_STATUSES)
        ] if not this_month.empty else this_month
        pending_count = (
            int((appointments["approval_status"] == "Pending").sum())
            if not appointments.empty
            else 0
        )

        metrics = st.columns(3)
        metrics[0].metric("Visits today", len(active_today), border=True)
        metrics[1].metric("Pending requests", pending_count, border=True)
        metrics[2].metric("Active visits this month", len(active_month), border=True)

        schedule_tab, list_tab, help_tab = st.tabs(
            ["Calendar", "All appointments", "Confidential help requests"]
        )
        with schedule_tab:
            selected_date = st.session_state["appointment_selected_date"]
            with st.container(key="appointment-calendar-layout"):
                calendar_column, selected_day_column = st.columns(
                    [1.8, 0.9], gap="medium"
                )
                with calendar_column:
                    with st.container(
                        border=True, key="appointment-calendar-panel"
                    ):
                        _render_calendar(appointments, selected_date)
                with selected_day_column:
                    with st.container(
                        border=True, key="appointment-selected-day-panel"
                    ):
                        _render_selected_day(appointments, selected_date)
                        if st.button(
                            "Add appointment",
                            icon=":material/add:",
                            width="stretch",
                            key="appointment_selected_day_add",
                        ):
                            st.query_params["focus"] = "schedule"
                            st.rerun()

            with st.container(border=True, key="appointment-setting"):
                _render_schedule_form(client)
            with st.container(border=True):
                _render_appointment_history(appointments, client, today)

        with list_tab:
            with st.container(border=True):
                _render_schedule_list(appointments, client)

        with help_tab:
            with st.container(border=True):
                _render_help_requests(client)

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
