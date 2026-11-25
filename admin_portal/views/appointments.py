import calendar
import json
import sqlite3
from datetime import date, datetime, time
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from database import (
    SUPABASE_KEY,
    get_local_connection,
    get_supabase_client,
    is_supabase_connection_available,
    is_supabase_connection_error,
)


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
    "Declined",
    "Cancelled",
)
RESCHEDULE_TIME_SLOTS = tuple(
    time(hour, minute)
    for start_hour, end_hour in ((8, 11), (13, 15))
    for hour in range(start_hour, end_hour + 1)
    for minute in (0, 30)
) + (time(16, 0),)
WEEKDAY_LABELS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
APPOINTMENT_COLUMNS = [
    "appointment_id",
    "patient_id",
    "patient_name",
    "patient_email",
    "contact_number",
    "requested_date",
    "requested_time_slot",
    "approval_status",
    "reason",
]
PAGE_SIZE = 1000
APPOINTMENT_STYLES = """
<style>
.stTooltipContent,
[role="tooltip"],
[role="tooltip"] * {
    white-space: pre-line !important;
}
.st-key-admin-calendar-page {
    color: #e5efed;
}
.st-key-admin-calendar-page h1,
.st-key-admin-calendar-page h2,
.st-key-admin-calendar-page h3,
.st-key-admin-calendar-page h4 {
    color: #f5f1e7;
}
.st-key-admin-calendar-page [data-testid="stCaption"],
.st-key-admin-calendar-page [data-testid="stMarkdownContainer"] p {
    color: #a7bbb7;
}
.st-key-admin-calendar-page .st-key-appointment-calendar-panel [data-testid="stVerticalBlockBorderWrapper"],
.st-key-admin-calendar-page .st-key-appointment-selected-day-panel [data-testid="stVerticalBlockBorderWrapper"],
.st-key-admin-calendar-page .st-key-appointment-outcome-queue [data-testid="stVerticalBlockBorderWrapper"],
.st-key-admin-calendar-page .st-key-appointment-setting [data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid rgba(255, 255, 255, .08) !important;
    border-radius: 16px !important;
    background: #112926 !important;
    box-shadow: 0 14px 34px rgba(0, 0, 0, .2);
}
.st-key-admin-calendar-page .st-key-appointment-selected-day-panel [data-testid="stVerticalBlockBorderWrapper"] {
    padding: 24px 28px !important;
    min-height: 590px !important;
    box-sizing: border-box;
}
.st-key-admin-calendar-page [data-testid="stMetric"] {
    min-height: 5.25rem;
    border: 1px solid rgba(255, 255, 255, .08) !important;
    border-radius: 14px !important;
    background: #112926 !important;
    box-shadow: 0 8px 20px rgba(0, 0, 0, .12);
}
.st-key-admin-calendar-page [data-testid="stMetricLabel"],
.st-key-admin-calendar-page [data-testid="stMetricValue"],
.st-key-admin-calendar-page [data-testid="stMetricDelta"] {
    color: #e5efed !important;
}
.st-key-admin-calendar-page .st-key-appointment-calendar-panel [class*="st-key-appointment_day_"] button {
    position: relative;
    display: flex;
    width: 100%;
    min-height: 0 !important;
    height: auto !important;
    aspect-ratio: 1 / 1;
    align-items: center;
    justify-content: center;
    padding: .35rem !important;
    border: 1px solid transparent !important;
    border-radius: 10px !important;
    background: rgba(255, 255, 255, .03) !important;
    box-shadow: none !important;
    color: #e5efed !important;
    font-size: .94rem;
    font-weight: 600;
    text-align: center;
    transition: background 140ms ease, border-color 140ms ease;
}
.st-key-admin-calendar-page .st-key-appointment-calendar-panel [class*="st-key-appointment_day_"] button:hover {
    border-color: transparent !important;
    background: rgba(45, 212, 191, .12) !important;
    color: #f5f1e7 !important;
    transform: none !important;
}
.st-key-admin-calendar-page .st-key-appointment-calendar-panel [class*="st-key-appointment_day_"] button[kind="primary"] {
    border-color: #2dd4bf !important;
    background: #145349 !important;
    color: #ffffff !important;
}
.st-key-admin-calendar-page .st-key-appointment-calendar-panel [class*="st-key-appointment_day_"] button[kind="primary"]:hover {
    background: #145349 !important;
}
.st-key-admin-calendar-page .st-key-appointment-calendar-panel [class*="st-key-appointment_day_"] button:focus-visible {
    outline: 2px solid #2dd4bf !important;
    outline-offset: 2px;
}
.st-key-admin-calendar-page .st-key-appointment-calendar-header [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
}
.st-key-admin-calendar-page .appointment-calendar-empty-day {
    width: 100%;
    min-height: 0;
    aspect-ratio: 1 / 1;
    border: 0;
    border-radius: 10px;
    background: transparent;
}
.st-key-admin-calendar-page .st-key-appointment-calendar-weekdays [data-testid="stHorizontalBlock"],
.st-key-admin-calendar-page [class*="st-key-appointment-calendar-week-"] [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
}
.st-key-admin-calendar-page .st-key-appointment-calendar-panel [class*="st-key-appointment_previous_month"] button,
.st-key-admin-calendar-page .st-key-appointment-calendar-panel [class*="st-key-appointment_next_month"] button {
    width: 2.5rem;
    min-height: 2.5rem;
    height: 2.5rem;
    padding: 0 !important;
    border: 1px solid rgba(255, 255, 255, .1) !important;
    border-radius: 10px !important;
    background: rgba(255, 255, 255, .04) !important;
    color: #e5efed !important;
}
.st-key-admin-calendar-page .st-key-appointment-calendar-panel [class*="st-key-appointment_previous_month"] button:hover,
.st-key-admin-calendar-page .st-key-appointment-calendar-panel [class*="st-key-appointment_next_month"] button:hover {
    border-color: rgba(45, 212, 191, .35) !important;
    background: rgba(45, 212, 191, .12) !important;
}
.st-key-admin-calendar-page [class*="st-key-appointment-outcome-card-"] {
    box-sizing: border-box;
    margin: .55rem 0;
    padding: 12px 16px;
    border: 1px solid rgba(255, 255, 255, .07);
    border-radius: 12px;
    background: rgba(255, 255, 255, .025);
}
.st-key-admin-calendar-page [class*="st-key-appointment-outcome-card-"] [data-testid="stHorizontalBlock"] {
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.st-key-admin-calendar-page [class*="st-key-appointment-outcome-card-"] button {
    min-height: 2.25rem !important;
    padding: .3rem .55rem !important;
    border-radius: 999px !important;
    font-size: .78rem;
}
.st-key-admin-calendar-page .st-key-appointment-setting [data-testid="stTextInput"] input,
.st-key-admin-calendar-page .st-key-appointment-setting [data-testid="stTextArea"] textarea,
.st-key-admin-calendar-page .st-key-appointment-setting [data-testid="stDateInput"] input,
.st-key-admin-calendar-page .st-key-appointment-setting [data-testid="stTimeInput"] input {
    border-color: rgba(255, 255, 255, .14) !important;
    background: #0c201d !important;
    color: #f5f1e7 !important;
}
.st-key-admin-calendar-page .st-key-appointment-setting [data-testid="stForm"] {
    border: 0;
    padding: 0;
}
.st-key-admin-calendar-page .appointment-panel-eyebrow,
.st-key-admin-calendar-page .appointment-detail-label {
    color: #91aba5;
    font-size: .67rem;
    font-weight: 700;
    letter-spacing: .12em;
    line-height: 1.4;
    text-transform: uppercase;
}
.st-key-admin-calendar-page .appointment-selected-date {
    margin: .15rem 0 .75rem;
    color: #f5f1e7;
    font-size: 1.25rem;
    font-weight: 700;
    line-height: 1.3;
}
.st-key-admin-calendar-page [class*="st-key-appointment-selected-entry-"] [data-testid="stVerticalBlockBorderWrapper"] {
    box-sizing: border-box;
    height: auto !important;
    min-height: 0 !important;
    overflow: visible !important;
    margin-top: 1rem;
    padding: 16px 18px 20px 18px !important;
    border: 1px solid #31534f !important;
    border-radius: 12px !important;
    background: #102824 !important;
}
.st-key-admin-calendar-page [class*="st-key-appointment-selected-entry-"] [data-testid="stVerticalBlock"],
.st-key-admin-calendar-page [class*="st-key-appointment-cancel-confirmation-"] [data-testid="stVerticalBlock"],
.st-key-admin-calendar-page [class*="st-key-appointment-reschedule-panel-"] [data-testid="stVerticalBlock"],
.st-key-admin-calendar-page [class*="st-key-appointment-cancel-confirmation-"] [data-testid="stVerticalBlockBorderWrapper"],
.st-key-admin-calendar-page [class*="st-key-appointment-reschedule-panel-"] [data-testid="stVerticalBlockBorderWrapper"] {
    height: auto !important;
    min-height: 0 !important;
    overflow: visible !important;
}
.st-key-admin-calendar-page .appointment-selected-name {
    margin: .15rem 0 0;
    color: #f5f1e7;
    font-size: 1rem;
    font-weight: 700;
    line-height: 1.35;
    overflow-wrap: anywhere;
}
.st-key-admin-calendar-page .appointment-metadata-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: .85rem 1rem;
}
.st-key-admin-calendar-page .appointment-detail-value {
    margin-top: .2rem;
    color: #e5efed;
    font-size: .85rem;
    line-height: 1.45;
    overflow-wrap: anywhere;
}
.st-key-admin-calendar-page .appointment-status-pill {
    display: inline-flex;
    align-items: center;
    padding: .22rem .62rem;
    border-radius: 999px;
    font-size: .68rem;
    font-weight: 700;
    line-height: 1.35;
    white-space: nowrap;
}
.st-key-admin-calendar-page .appointment-status-scheduled {
    background: #1b4d46;
    color: #6ee7b7;
}
.st-key-admin-calendar-page .appointment-status-pending {
    background: rgba(217, 164, 79, .16);
    color: #e8c98d;
}
.st-key-admin-calendar-page .appointment-status-cancelled {
    background: rgba(229, 139, 125, .16);
    color: #efb0a5;
}
.st-key-admin-calendar-page .appointment-status-declined {
    background: rgba(229, 139, 125, .16);
    color: #efb0a5;
}
.st-key-admin-calendar-page .appointment-status-no-show {
    background: rgba(229, 139, 125, .16);
    color: #efb0a5;
}
.st-key-admin-calendar-page .appointment-detail-quote {
    margin: 10px 0 14px;
    padding: .8rem .9rem;
    border: 1px solid rgba(255, 255, 255, .04);
    border-radius: 10px;
    background: #0c201d;
}
.st-key-admin-calendar-page .appointment-detail-quote p {
    margin: .35rem 0 0;
    color: #d7e5e1;
    font-size: .86rem;
    line-height: 1.55;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
}
.st-key-admin-calendar-page .appointment-history-scroll {
    overflow-x: auto;
    border: 1px solid rgba(255, 255, 255, .08);
    border-radius: 12px;
    background: #0c201d;
}
.st-key-admin-calendar-page .appointment-history-table {
    width: 100%;
    border-collapse: collapse;
    color: #e5efed;
    font-size: .85rem;
}
.st-key-admin-calendar-page .appointment-history-table th,
.st-key-admin-calendar-page .appointment-history-table td {
    padding: .8rem .9rem;
    border-bottom: 1px solid rgba(255, 255, 255, .07);
    text-align: left;
    vertical-align: middle;
}
.st-key-admin-calendar-page .appointment-history-table th {
    color: #91aba5;
    font-size: .67rem;
    font-weight: 700;
    letter-spacing: .08em;
    text-transform: uppercase;
    white-space: nowrap;
}
.st-key-admin-calendar-page .appointment-history-table td {
    color: #d7e5e1;
}
.st-key-admin-calendar-page .appointment-history-table tr:last-child td {
    border-bottom: 0;
}
.st-key-admin-calendar-page .appointment-history-table tbody tr:hover {
    background: rgba(45, 212, 191, .04);
}
@media (max-width: 700px) {
    .st-key-admin-calendar-page .appointment-metadata-grid {
        grid-template-columns: minmax(0, 1fr);
    }
}
</style>
"""


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


def _format_patient_email(value):
    if value is None or pd.isna(value) or not str(value).strip():
        return "Not provided (Guest)"
    return str(value).strip()


def _calendar_appointment_status_label(appointment):
    status = appointment.get("approval_status") or "Pending"
    if status == "Scheduled":
        return (
            "Confirmed"
            if appointment.get("event_source") == "help_request"
            else "Scheduled by admin"
        )
    return status


def _appointment_status_class(status):
    normalized_status = str(status).strip().casefold()
    if normalized_status in {
        "completed",
        "attended",
        "scheduled",
        "rescheduled",
        "confirmed",
        "scheduled by admin",
    }:
        return "scheduled"
    if normalized_status == "cancelled":
        return "cancelled"
    if normalized_status == "declined":
        return "declined"
    if normalized_status in {"no-show", "did not attend"}:
        return "no-show"
    return "pending"


def _appointment_status_badge(status):
    label = (
        "Pending"
        if status is None or pd.isna(status) or not str(status).strip()
        else str(status)
    )
    status_class = _appointment_status_class(label)
    return (
        f'<span class="appointment-status-pill appointment-status-{status_class}">'
        f"{escape(label)}</span>"
    )


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
                "request_id, patient_name, patient_age, patient_email, "
                "contact_number, message, requested_date, requested_time_slot, "
                "approval_status, created_at"
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
            "patient_email": request.get("patient_email"),
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


def _ensure_appointment_snapshot_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS appointment_snapshot_cache (
            snapshot_id INTEGER PRIMARY KEY CHECK (snapshot_id = 1),
            snapshot_json TEXT NOT NULL,
            synced_at TEXT NOT NULL
        )
        """
    )


def _save_appointment_snapshot(appointments):
    payload = {
        "columns": list(appointments.columns),
        "records": json.loads(
            appointments.to_json(orient="records", date_format="iso")
        ),
    }
    synced_at = datetime.now(ZoneInfo("Asia/Manila")).isoformat(
        timespec="seconds"
    )
    conn = get_local_connection()
    try:
        _ensure_appointment_snapshot_table(conn)
        conn.execute(
            """
            INSERT INTO appointment_snapshot_cache (
                snapshot_id, snapshot_json, synced_at
            )
            VALUES (1, ?, ?)
            ON CONFLICT(snapshot_id) DO UPDATE SET
                snapshot_json = excluded.snapshot_json,
                synced_at = excluded.synced_at
            """,
            (json.dumps(payload), synced_at),
        )
        conn.commit()
    finally:
        conn.close()
    return synced_at


def _load_appointment_snapshot():
    conn = get_local_connection()
    try:
        _ensure_appointment_snapshot_table(conn)
        conn.commit()
        row = conn.execute(
            """
            SELECT snapshot_json, synced_at
            FROM appointment_snapshot_cache
            WHERE snapshot_id = 1
            """
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    try:
        payload = json.loads(row["snapshot_json"])
        columns = payload["columns"]
        records = payload["records"]
        if (
            not isinstance(columns, list)
            or not all(isinstance(column, str) for column in columns)
            or not set(APPOINTMENT_COLUMNS).issubset(columns)
            or "event_source" not in columns
            or not isinstance(records, list)
            or not isinstance(row["synced_at"], str)
        ):
            raise ValueError("The cached appointment snapshot is incomplete.")
        return pd.DataFrame.from_records(records, columns=columns), row["synced_at"]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("The cached appointment snapshot is invalid.") from error


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
def _render_appointment_metrics(
    client,
    initial_appointments,
    today,
):
    if client is None or not st.session_state.get(
        "appointment_metrics_initialized"
    ):
        counts = _appointment_summary_counts(initial_appointments, today)
        st.session_state["appointment_metrics_initialized"] = True
    else:
        try:
            counts = _load_appointment_summary_counts(client, today)
        except Exception as error:
            if is_supabase_connection_error(error):
                is_supabase_connection_available.clear()
                counts = _appointment_summary_counts(initial_appointments, today)
            else:
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
    today = datetime.now(ZoneInfo("Asia/Manila")).date()
    with st.container(key="appointment-calendar-header"):
        left_controls, title_col, right_control = st.columns(
            [2, 5, 2],
            vertical_alignment="center",
        )
        with left_controls:
            today_col, previous_col = st.columns([1.35, 0.65], gap="small")
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
            st.markdown(
                f"### {month_start.strftime('%B %Y')}",
                text_alignment="center",
            )
        with right_control:
            with st.container(horizontal=True, horizontal_alignment="right"):
                if st.button(
                    " ",
                    icon=":material/chevron_right:",
                    key="appointment_next_month",
                    help="Show the next month",
                ):
                    st.session_state[month_state_key] = _month_offset(month_start, 1)
                    st.rerun()

    confirmed_by_date = {}
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

    dot_day_keys = set()
    for requested_date in confirmed_by_date:
        try:
            appointment_date = date.fromisoformat(str(requested_date))
        except (TypeError, ValueError):
            continue
        if (
            appointment_date.year == month_start.year
            and appointment_date.month == month_start.month
        ):
            dot_day_keys.add(appointment_date.isoformat())
    dot_styles = "\n".join(
        f"""
        .st-key-admin-calendar-page .st-key-appointment-calendar-panel
        [class*="st-key-appointment_day_{day_key}"] button::after {{
            content: "•";
            position: absolute;
            bottom: .28rem;
            color: #2dd4bf;
            font-size: 1.05rem;
            line-height: 1;
        }}
        """
        for day_key in sorted(dot_day_keys)
    )
    st.html(
        f"""
        <style>
        .st-key-admin-calendar-page .st-key-appointment-calendar-panel
        [class*="st-key-appointment_day_{today.isoformat()}"] button:not([kind="primary"]) {{
            border-color: rgba(45, 212, 191, .58) !important;
            box-shadow: inset 0 0 0 1px rgba(45, 212, 191, .22) !important;
        }}
        {dot_styles}
        </style>
        """
    )

    with st.container(key="appointment-calendar-weekdays"):
        weekday_columns = st.columns(7, gap="small")
        for column, label in zip(weekday_columns, WEEKDAY_LABELS):
            with column:
                st.caption(f"**{label}**")

    month_rows = calendar.Calendar(firstweekday=calendar.SUNDAY).monthdayscalendar(
        month_start.year, month_start.month
    )
    for week_index, week in enumerate(month_rows):
        with st.container(key=f"appointment-calendar-week-{week_index}"):
            day_columns = st.columns(7, gap="small")
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
                    label = str(day_number)
                    button_options = {
                        "label": label,
                        "key": f"appointment_day_{day_key}",
                        "type": (
                            "primary"
                            if day_date == selected_date
                            else "secondary"
                        ),
                        "width": "stretch",
                    }
                    if day_appointments is not None and not day_appointments.empty:
                        names_and_times = []
                        for appointment in day_appointments.to_dict(
                            orient="records"
                        ):
                            name = appointment.get("patient_name")
                            if (
                                name is None
                                or pd.isna(name)
                                or not str(name).strip()
                            ):
                                name = "Patient"
                            names_and_times.append(
                                f"{name} "
                                f"({_format_time(appointment.get('requested_time_slot'))})"
                            )
                        button_options["help"] = (
                            f"{day_date:%b} {day_date.day}:\n"
                            + "\n".join(
                                f"• {name_and_time}"
                                for name_and_time in names_and_times
                            )
                        )
                    if st.button(**button_options):
                        st.session_state["appointment_selected_date"] = day_date
                        st.session_state["appointment_form_date"] = day_date
                        st.rerun()

    st.caption(
        "A teal dot marks one or more confirmed or rescheduled visits. "
        "Select a date to schedule a visit."
    )


def _render_selected_day(appointments, selected_date, client):
    if appointments.empty:
        day_appointments = appointments
    else:
        day_appointments = appointments[
            appointments["requested_date"] == selected_date.isoformat()
        ]

    display_date = (
        f"{selected_date.strftime('%A, %B')} {selected_date.day}, {selected_date.year}"
    )
    st.markdown(
        '<div class="appointment-panel-eyebrow">Selected day</div>'
        f'<div class="appointment-selected-date">{escape(display_date)}</div>',
        unsafe_allow_html=True,
    )
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
            row_key = str(
                appointment.get("appointment_id") or f"appointment-{index}"
            ).replace(":", "-")
            cancel_key = f"appointment-cancel-confirm-{row_key}"
            reschedule_key = f"appointment-reschedule-open-{row_key}"
            cancel_status = (
                "Declined"
                if appointment.get("event_source") == "help_request"
                else "Cancelled"
            )
            status_label = _calendar_appointment_status_label(appointment)
            metadata = [
                ("Time", _format_time(appointment.get("requested_time_slot"))),
                ("Status", _appointment_status_badge(status_label)),
                ("Contact", _format_optional(appointment.get("contact_number"))),
                (
                    "Email",
                    _format_patient_email(appointment.get("patient_email")),
                ),
            ]
            quote_label = None
            quote_text = None
            if appointment.get("event_source") == "help_request":
                age = appointment.get("patient_age")
                if age is not None and not pd.isna(age):
                    metadata.append(("Age", str(age)))
                message = appointment.get("message")
                if message and not pd.isna(message):
                    quote_label = "Message"
                    quote_text = str(message)
                received_at = appointment.get("created_at")
                if received_at is not None and not pd.isna(received_at):
                    metadata.append(
                        ("Received", _format_received_at(received_at))
                    )
            else:
                metadata.append(
                    (
                        "Patient app ID",
                        _format_optional(appointment.get("patient_id")),
                    )
                )
                reason = _format_optional(appointment.get("reason"))
                if reason != "Not provided":
                    quote_label = "Reason"
                    quote_text = reason

            metadata_markup = "".join(
                '<div class="appointment-detail-item">'
                f'<div class="appointment-detail-label">{escape(label)}</div>'
                '<div class="appointment-detail-value">'
                f'{value if label == "Status" else escape(value)}'
                "</div></div>"
                for label, value in metadata
            )
            quote_markup = (
                '<div class="appointment-detail-quote">'
                f'<div class="appointment-detail-label">{escape(quote_label)}</div>'
                f"<p>{escape(quote_text)}</p></div>"
                if quote_label is not None
                else ""
            )
            with st.container(
                border=True,
                key=f"appointment-selected-entry-{row_key}",
            ):
                name_column, reschedule_column, cancel_column = st.columns(
                    [5, 0.65, 0.65],
                    vertical_alignment="center",
                    gap="small",
                )
                with name_column:
                    st.markdown(
                        '<div class="appointment-detail-label">Patient</div>'
                        f'<div class="appointment-selected-name">'
                        f"{escape(patient_name)}</div>",
                        unsafe_allow_html=True,
                    )
                with reschedule_column:
                    if st.button(
                        "",
                        key=f"appointment-icon-reschedule-{row_key}",
                        icon=":material/calendar_month:",
                        help=(
                            "Reschedule appointment"
                            if client is not None
                            else "Reschedule appointment is unavailable in offline snapshot mode."
                        ),
                        disabled=client is None,
                        width="content",
                    ):
                        st.session_state[reschedule_key] = True
                        st.session_state.pop(cancel_key, None)
                        st.rerun()
                with cancel_column:
                    if st.button(
                        "",
                        key=f"appointment-icon-cancel-{row_key}",
                        icon=":material/close:",
                        help=(
                            "Cancel appointment"
                            if client is not None
                            else "Cancel appointment is unavailable in offline snapshot mode."
                        ),
                        disabled=client is None,
                        width="content",
                    ):
                        st.session_state[cancel_key] = True
                        st.session_state.pop(reschedule_key, None)
                        st.rerun()

                st.markdown(
                    f'<div class="appointment-metadata-grid">'
                    f"{metadata_markup}</div>{quote_markup}",
                    unsafe_allow_html=True,
                )

                if st.session_state.get(cancel_key):
                    with st.container(
                        border=True,
                        key=f"appointment-cancel-confirmation-{row_key}",
                    ):
                        st.warning(f"Cancel appointment for {patient_name}?")
                        confirm_column, keep_column = st.columns([1, 1])
                        confirm_cancel = False
                        with confirm_column:
                            confirm_cancel = st.button(
                                "Confirm Cancel",
                                key=f"appointment-confirm-cancel-{row_key}",
                                type="primary",
                                disabled=client is None,
                                help=(
                                    "Unavailable in offline snapshot mode."
                                    if client is None
                                    else None
                                ),
                                width="stretch",
                            )
                        with keep_column:
                            if st.button(
                                "Keep",
                                key=f"appointment-keep-{row_key}",
                                width="stretch",
                            ):
                                st.session_state.pop(cancel_key, None)
                                st.rerun()
                        if confirm_cancel:
                            st.session_state.pop(cancel_key, None)
                            if not _update_appointment_outcome(
                                client,
                                appointment,
                                cancel_status,
                            ):
                                st.session_state[cancel_key] = True

                if st.session_state.get(reschedule_key):
                    with st.container(
                        border=True,
                        key=f"appointment-reschedule-panel-{row_key}",
                    ):
                        st.markdown("**Reschedule appointment**")
                        current_date_value = appointment.get("requested_date")
                        try:
                            current_date = date.fromisoformat(
                                str(current_date_value)[:10]
                            )
                        except (TypeError, ValueError):
                            current_date = selected_date
                        current_time_value = appointment.get(
                            "requested_time_slot"
                        )
                        try:
                            current_time = time.fromisoformat(
                                str(current_time_value)
                            )
                        except (TypeError, ValueError):
                            current_time = RESCHEDULE_TIME_SLOTS[0]
                        if current_time not in RESCHEDULE_TIME_SLOTS:
                            current_time = RESCHEDULE_TIME_SLOTS[0]

                        date_column, time_column = st.columns(2)
                        with date_column:
                            new_date = st.date_input(
                                "New Date",
                                value=current_date,
                                key=f"appointment-reschedule-date-{row_key}",
                            )
                        with time_column:
                            new_time = st.selectbox(
                                "New Time",
                                RESCHEDULE_TIME_SLOTS,
                                index=RESCHEDULE_TIME_SLOTS.index(current_time),
                                format_func=_format_time,
                                key=f"appointment-reschedule-time-{row_key}",
                            )
                        confirm_column, close_column = st.columns([1, 1])
                        confirm_reschedule = False
                        with confirm_column:
                            confirm_reschedule = st.button(
                                "Confirm",
                                key=f"appointment-confirm-reschedule-{row_key}",
                                type="primary",
                                disabled=client is None,
                                help=(
                                    "Unavailable in offline snapshot mode."
                                    if client is None
                                    else None
                                ),
                                width="stretch",
                            )
                        with close_column:
                            if st.button(
                                "Cancel",
                                key=f"appointment-close-reschedule-{row_key}",
                                width="stretch",
                            ):
                                st.session_state.pop(reschedule_key, None)
                                st.rerun()
                        if confirm_reschedule:
                            st.session_state.pop(reschedule_key, None)
                            if not _reschedule_appointment(
                                client,
                                appointment,
                                new_date,
                                new_time,
                            ):
                                st.session_state[reschedule_key] = True


def _render_appointment_history(appointments):
    st.markdown("#### Appointment History")
    st.caption("Only finalized appointments are shown here.")
    if appointments.empty:
        st.info("There is no appointment history yet.")
        return

    status_labels = {
        "Completed": "Attended",
        "Attended": "Attended",
        "Cancelled": "Cancelled",
        "No-show": "Did not attend",
        "Did not attend": "Did not attend",
        "Declined": "Declined",
    }
    history = appointments[
        appointments["approval_status"].isin(status_labels)
    ].copy()
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
        status_labels
    )
    history["Reason"] = history["reason"].fillna("")
    history = history.sort_values(
        ["requested_date", "requested_time_slot", "patient_name"],
        ascending=[False, False, True],
        kind="stable",
        na_position="last",
    )
    table_rows = []
    for row in history.to_dict(orient="records"):
        cells = (
            row["Date"],
            row["Time"],
            row.get("patient_name"),
            row.get("contact_number"),
            row["Reason"],
        )
        cell_markup = "".join(
            f"<td>{'' if value is None or pd.isna(value) else escape(str(value))}</td>"
            for value in cells
        )
        status = row["Attendance / status"]
        table_rows.append(
            f"<tr>{cell_markup}"
            f"<td>{_appointment_status_badge(status)}</td></tr>"
        )
    st.markdown(
        """
        <div class="appointment-history-scroll">
          <table class="appointment-history-table"
                 aria-label="Past appointments and attendance outcomes">
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Time</th>
                <th scope="col">Patient</th>
                <th scope="col">Contact</th>
                <th scope="col">Reason</th>
                <th scope="col">Attendance / status</th>
              </tr>
            </thead>
            <tbody>
        """
        + "".join(table_rows)
        + """
            </tbody>
          </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _update_appointment_outcome(
    client, appointment, status, *, return_to_awaiting_outcomes=False
):
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
    if return_to_awaiting_outcomes:
        st.session_state["scroll_to_awaiting_outcomes"] = True
    st.rerun()
    return True


def _reschedule_appointment(client, appointment, new_date, new_time):
    if new_time < time(8, 0) or new_time > time(16, 0):
        st.error("Choose an appointment time between 8:00am and 4:00pm.")
        return False

    help_request = appointment.get("event_source") == "help_request"
    table_name = "patient_help_requests" if help_request else "appointments"
    id_column = "request_id" if help_request else "appointment_id"
    record_id = (
        str(appointment["appointment_id"]).removeprefix("help_request:")
        if help_request
        else appointment["appointment_id"]
    )
    new_time_value = new_time.strftime("%H:%M:%S")
    try:
        response = (
            client.table(table_name)
            .update(
                {
                    "requested_date": new_date.isoformat(),
                    "requested_time_slot": new_time_value,
                    "approval_status": "Rescheduled",
                }
            )
            .eq(id_column, record_id)
            .select(id_column)
            .execute()
        )
        if not response.data:
            raise RuntimeError("No matching appointment was rescheduled.")
    except Exception as error:
        st.error("Unable to reschedule this appointment in Supabase.")
        with st.expander("Technical details"):
            st.code(str(error))
        return False

    try:
        _log_appointment_action(
            "APPOINTMENT RESCHEDULED",
            f"{appointment.get('patient_name') or 'Patient'}: "
            f"{appointment.get('requested_date') or 'date not set'} at "
            f"{_format_time(appointment.get('requested_time_slot'))} moved to "
            f"{new_date.isoformat()} at {_format_time(new_time_value)}.",
        )
    except Exception as error:
        st.warning(
            "The appointment was rescheduled, but its local activity entry "
            f"could not be written: {error}"
        )

    st.session_state["appointment_flash"] = (
        f"Appointment for {appointment.get('patient_name') or 'Patient'} "
        f"rescheduled to {new_date.isoformat()} at {_format_time(new_time_value)}."
    )
    st.session_state["appointment_selected_date"] = new_date
    st.session_state["appointment_calendar_month"] = new_date.replace(day=1)
    st.rerun()
    return True


def _render_awaiting_outcomes(appointments, client, *, now=None):
    now = now or datetime.now(ZoneInfo("Asia/Manila"))
    st.markdown('<div id="visits-awaiting-outcome"></div>', unsafe_allow_html=True)
    st.markdown("### Visits Awaiting Outcome")
    if st.session_state.pop("scroll_to_awaiting_outcomes", False):
        st.html(
            """
            <script>
            requestAnimationFrame(() => {
                const section = document.getElementById("visits-awaiting-outcome");
                if (section) {
                    section.scrollIntoView({ behavior: "smooth", block: "start" });
                }
            });
            </script>
            """,
            unsafe_allow_javascript=True,
        )
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

    if client is None:
        st.caption("Outcome actions are unavailable while showing an offline snapshot.")

    for scheduled_at, appointment in waiting:
        patient_name = appointment.get("patient_name") or "Patient"
        identity = appointment.get("appointment_id")
        if pd.isna(identity):
            identity = patient_name
        row_key = str(identity).replace(":", "-")
        with st.container(
            horizontal=True,
            border=True,
            key=f"appointment-outcome-card-{row_key}",
            wrap=False,
            horizontal_alignment="distribute",
            vertical_alignment="center",
            gap="small",
        ):
            with st.container(width="content", gap="xxsmall"):
                st.markdown(
                    f"**{escape(str(patient_name))}** · "
                    f"{scheduled_at:%b %d, %Y} · "
                    f"{_format_time(appointment.get('requested_time_slot'))}"
                )
            with st.container(
                horizontal=True,
                width="content",
                wrap=False,
                gap="xsmall",
            ):
                if st.button(
                    "Done",
                    key=f"appointment-outcome-done-{row_key}",
                    icon=":material/check_circle:",
                    width="content",
                    disabled=client is None,
                ):
                    _update_appointment_outcome(
                        client,
                        appointment,
                        "Completed",
                        return_to_awaiting_outcomes=True,
                    )
                if st.button(
                    "Cancel",
                    key=f"appointment-outcome-cancel-{row_key}",
                    icon=":material/event_busy:",
                    width="content",
                    disabled=client is None,
                ):
                    _update_appointment_outcome(
                        client,
                        appointment,
                        "Cancelled",
                        return_to_awaiting_outcomes=True,
                    )
                if st.button(
                    "Did not come",
                    key=f"appointment-outcome-no-show-{row_key}",
                    icon=":material/person_off:",
                    width="content",
                    disabled=client is None,
                ):
                    _update_appointment_outcome(
                        client,
                        appointment,
                        "No-show",
                        return_to_awaiting_outcomes=True,
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
    st.markdown("### Set an Appointment")
    st.caption(
        "Patient-app requests appear here with Pending status. "
        "Appointments entered by an admin are saved as Scheduled."
    )
    with st.form("schedule_appointment_form"):
        patient_column, schedule_column = st.columns(2)
        with patient_column:
            patient_name = st.text_input(
                "Patient Name",
                key="appointment_form_patient_name",
            ).strip()
            patient_id = st.text_input(
                "Patient App ID (Optional)",
                key="appointment_form_patient_id",
                help="Use the patient ID from the connected patient app when available.",
            ).strip()
            contact_number = st.text_input(
                "Contact Number",
                key="appointment_form_contact",
            ).strip()
        with schedule_column:
            visit_date = st.date_input(
                "Visit Date",
                key="appointment_form_date",
                format="MM/DD/YYYY",
            )
            visit_time = st.time_input(
                "Visit Time (Philippine Time)",
                key="appointment_form_time",
                format="12h",
            )
        reason = st.text_area(
            "Notes / Reason for Visit (Optional)",
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
    if visit_time < time(8, 0) or visit_time > time(16, 0):
        st.error("Choose a visit time between 8:00am and 4:00pm.")
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
            "ADMIN APPOINTMENT SET",
            f"Set an appointment for {patient_name} on {visit_date.isoformat()} at "
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
                st.write(
                    "**Email:** "
                    f"{_format_patient_email(appointment.get('patient_email'))}"
                )
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
                    action_type = (
                        "REQUEST CONFIRMED"
                        if status == "Pending" and selected_status == "Scheduled"
                        else {
                            "Scheduled": "APPOINTMENT SCHEDULED",
                            "Cancelled": "APPOINTMENT CANCELLED",
                            "Completed": "APPOINTMENT OUTCOME",
                            "No-show": "APPOINTMENT OUTCOME",
                        }.get(selected_status, "APPOINTMENT STATUS")
                    )
                    action_details = (
                        f"Confirmed the appointment request for "
                        f"{appointment.get('patient_name') or 'Patient'} on "
                        f"{appointment.get('requested_date') or 'date not set'} "
                        f"at {_format_time(appointment.get('requested_time_slot'))}."
                        if action_type == "REQUEST CONFIRMED"
                        else (
                            f"{appointment.get('patient_name') or 'Patient'}: "
                            f"status changed from {status} to {selected_status} "
                            f"for {appointment.get('requested_date') or 'date not set'} "
                            f"at {_format_time(appointment.get('requested_time_slot'))}."
                        )
                    )
                    try:
                        _log_appointment_action(
                            action_type,
                            action_details,
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
                "request_id, patient_name, patient_age, patient_email, "
                "contact_number, message, requested_date, requested_time_slot, "
                "approval_status, created_at"
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
                st.text(f"Patient: {request.get('patient_name') or 'Not provided'}")
                st.text(
                    "Email: "
                    f"{_format_patient_email(request.get('patient_email'))}"
                )
                st.text(f"Age: {request.get('patient_age') or 'Not provided'}")
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
                    action_type = (
                        "REQUEST CONFIRMED"
                        if status == "Pending" and selected_status == "Scheduled"
                        else {
                            "Scheduled": "APPOINTMENT SCHEDULED",
                            "Cancelled": "APPOINTMENT CANCELLED",
                            "Completed": "APPOINTMENT OUTCOME",
                            "No-show": "APPOINTMENT OUTCOME",
                        }.get(selected_status, "HELP REQUEST STATUS")
                    )
                    action_details = (
                        f"Confirmed the patient request for "
                        f"{request.get('patient_name') or 'Patient'} on "
                        f"{requested_date} at {requested_time}."
                        if action_type == "REQUEST CONFIRMED"
                        else (
                            f"{request.get('patient_name') or 'Patient'}: "
                            f"help request status changed from {status} to "
                            f"{selected_status} for {requested_date} at "
                            f"{requested_time}."
                        )
                    )
                    try:
                        _log_appointment_action(
                            action_type,
                            action_details,
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


@st.fragment(run_every="15s")
def _monitor_appointment_connectivity():
    is_online = bool(SUPABASE_KEY) and is_supabase_connection_available()
    state_key = "appointment_supabase_connection_online"
    previous_state = st.session_state.get(state_key)
    if previous_state is None:
        st.session_state[state_key] = is_online
    elif previous_state != is_online:
        st.session_state[state_key] = is_online
        st.rerun()
    st.empty()


def show_appointments_page():
    with st.container(key="admin-calendar-page"):
        st.html(APPOINTMENT_STYLES)
        _monitor_appointment_connectivity()
        st.markdown(
            '<div class="calendar-eyebrow">Appointment Management</div>',
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
                is_supabase_connection_available.clear()
                st.rerun()

            if st.button(
                "Set an Appointment",
                type="primary",
                icon=":material/add:",
                width="stretch",
                key="appointment_jump_to_form",
            ):
                st.query_params["focus"] = "schedule"
                st.rerun()

        client = None
        if SUPABASE_KEY and is_supabase_connection_available():
            client = get_supabase_client()

        calendar_appointments = None
        if client is not None:
            try:
                appointments = _load_appointments(client)
                calendar_appointments = _load_calendar_appointments(
                    client, appointments
                )
            except Exception as error:
                if is_supabase_connection_error(error):
                    is_supabase_connection_available.clear()
                    client = None
                else:
                    st.error(
                        "Unable to load the appointment calendar from Supabase. "
                        "Check the project API URL, run the appointment and "
                        "patient-help-request SQL setup scripts, and verify "
                        "SELECT permissions."
                    )
                    with st.expander("Technical details"):
                        st.code(str(error))
                    return

        if client is not None and calendar_appointments is not None:
            try:
                _save_appointment_snapshot(calendar_appointments)
            except sqlite3.Error as error:
                st.warning(
                    "Appointments loaded from Supabase, but the offline snapshot "
                    f"could not be saved: {error}"
                )
        else:
            try:
                cached_snapshot = _load_appointment_snapshot()
            except (sqlite3.Error, ValueError) as error:
                st.error(f"Unable to read the offline appointment snapshot: {error}")
                return
            if cached_snapshot is None:
                st.info(
                    "Supabase is unavailable and no offline appointment snapshot "
                    "is available yet."
                )
                return
            calendar_appointments, synced_at = cached_snapshot
            st.badge(
                f"Showing cached offline snapshot (last synced {synced_at})",
                icon=":material/wifi_off:",
                color="gray",
            )

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

        focus = st.query_params.get("focus")
        focused_tab = {
            "schedule": "Set an Appointment",
            "history": "Appointment History",
        }.get(focus)
        if focused_tab is not None:
            st.session_state["appointment_sections"] = focused_tab

        calendar_tab, schedule_tab, history_tab = st.tabs(
            ["Calendar", "Set an Appointment", "Appointment History"],
            default=focused_tab,
            key="appointment_sections",
            on_change="rerun",
        )
        with calendar_tab:
            _render_appointment_metrics(client, calendar_appointments, today)
            with st.container(key="appointment-calendar-content"):
                with st.container(key="appointment-calendar-layout"):
                    calendar_column, selected_day_column = st.columns(
                        [1.8, 0.9], gap="medium"
                    )
                    with calendar_column:
                        with st.container(
                            border=True, key="appointment-calendar-panel"
                        ):
                            selected_date = st.session_state[
                                "appointment_selected_date"
                            ]
                            _render_calendar(calendar_appointments, selected_date)
                    with selected_day_column:
                        with st.container(
                            border=True,
                            height=590,
                            key="appointment-selected-day-panel",
                        ):
                            _render_selected_day(
                                calendar_appointments,
                                st.session_state["appointment_selected_date"],
                                client,
                            )

            with st.container(border=True, key="appointment-outcome-queue"):
                _render_awaiting_outcomes(calendar_appointments, client)

        with schedule_tab:
            with st.container(border=True, key="appointment-setting"):
                if client is None:
                    st.info(
                        "Appointment scheduling requires an active Supabase "
                        "connection."
                    )
                else:
                    _render_schedule_form(client)

        with history_tab:
            with st.container(border=True, key="appointment-history"):
                _render_appointment_history(calendar_appointments)

        if focus == "schedule":
            target_selector = ".st-key-appointment-setting"
        elif focus == "history":
            target_selector = ".st-key-appointment-history"
        else:
            target_selector = None

        if target_selector:
            st.html(
                f"""
                <script>
                requestAnimationFrame(() => requestAnimationFrame(() => {{
                  document.querySelector("{target_selector}")
                    ?.scrollIntoView({{ behavior: "smooth", block: "center" }});
                }}));
                </script>
                """,
                unsafe_allow_javascript=True,
            )
            st.query_params.pop("focus", None)


if __name__ == "__main__":
    show_appointments_page()
