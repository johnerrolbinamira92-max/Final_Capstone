import calendar
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from database import get_local_connection, get_supabase_client


ACTIVE_STATUSES = ("Pending", "Scheduled")
APPOINTMENT_STATUSES = ("Pending", "Scheduled", "Completed", "Cancelled")
WEEKDAY_LABELS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
APPOINTMENT_COLUMNS = [
    "appointment_id",
    "patient_id",
    "patient_name",
    "contact_number",
    "requested_date",
    "requested_time_slot",
    "approval_status",
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
    previous_col, title_col, next_col = st.columns([1, 5, 1])
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
                    st.button(
                        " ",
                        key=f"appointment_empty_{month_start:%Y_%m}_{week_index}_{day_index}",
                        disabled=True,
                        width="stretch",
                    )
                    continue

                day_date = date(month_start.year, month_start.month, day_number)
                day_key = day_date.isoformat()
                appointment_count = int(active_counts.get(day_key, 0))
                label = (
                    f"{day_number}\n● {appointment_count}"
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
    st.markdown(f"#### Visits for {display_date}")
    if day_appointments.empty:
        st.caption("No appointments are recorded for this date yet.")
        return

    display = day_appointments.copy()
    display["Time"] = display["requested_time_slot"].map(_format_time)
    display = display.rename(
        columns={
            "patient_name": "Patient",
            "contact_number": "Contact",
            "approval_status": "Status",
        }
    )
    st.dataframe(
        display[["Time", "Patient", "Contact", "Status"]],
        hide_index=True,
        width="stretch",
        alt=f"Appointments scheduled for {selected_date.isoformat()}",
    )


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
    st.markdown("#### Schedule a visit")
    st.caption(
        "Patient-app requests appear here with Pending status. "
        "Appointments entered by an admin are saved as Scheduled."
    )
    with st.form("schedule_appointment_form"):
        patient_id = st.text_input(
            "Patient app ID (optional)",
            key="appointment_form_patient_id",
            help="Use the patient ID from the connected patient app when available.",
        ).strip()
        patient_name = st.text_input(
            "Patient name",
            key="appointment_form_patient_name",
        ).strip()
        contact_number = st.text_input(
            "Contact number",
            key="appointment_form_contact",
        ).strip()
        visit_col, time_col = st.columns(2)
        with visit_col:
            visit_date = st.date_input(
                "Visit date",
                key="appointment_form_date",
                format="MM/DD/YYYY",
            )
        with time_col:
            visit_time = st.time_input(
                "Visit time (Philippine time)",
                key="appointment_form_time",
                format="12h",
            )
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


def show_appointments_page():
    st.title("Appointment Schedule")
    st.write(
        "Plan patient visits and review upcoming appointments. "
        "Appointment dates and times use Philippine local time."
    )

    client = get_supabase_client()
    if client is None:
        return

    try:
        appointments = _load_appointments(client)
    except Exception as error:
        st.error(
            "Unable to load appointments from Supabase. Check the project API URL, "
            "run the appointments SQL migration, and verify SELECT permissions."
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
        st.session_state["appointment_form_time"] = time(9, 0)

    if "appointment_form_patient_id" not in st.session_state:
        st.session_state["appointment_form_patient_id"] = ""
    if "appointment_form_patient_name" not in st.session_state:
        st.session_state["appointment_form_patient_name"] = ""
    if "appointment_form_contact" not in st.session_state:
        st.session_state["appointment_form_contact"] = ""

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

    calendar_tab, list_tab = st.tabs(["Calendar", "Schedule list"])
    with calendar_tab:
        selected_date = st.session_state["appointment_selected_date"]
        calendar_col, detail_col = st.columns([3, 2])
        with calendar_col:
            with st.container(border=True):
                _render_calendar(appointments, selected_date)
        with detail_col:
            with st.container(border=True):
                _render_selected_day(appointments, selected_date)
        with st.container(border=True):
            _render_schedule_form(client)

    with list_tab:
        with st.container(border=True):
            _render_schedule_list(appointments, client)


if __name__ == "__main__":
    show_appointments_page()
