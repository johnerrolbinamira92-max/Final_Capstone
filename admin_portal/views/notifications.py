import json
import sqlite3
from datetime import date, datetime, time
from html import escape
from zoneinfo import ZoneInfo

import streamlit as st

from database import (
    SUPABASE_KEY,
    SUPABASE_URL,
    get_local_connection,
    get_supabase_client,
    is_supabase_connection_available,
    is_supabase_connection_error,
)
from views.appointments import (
    _format_patient_email,
    _format_received_at,
    _latest_activity_sort_key,
    _log_appointment_action,
)
from views.privacy import mask_patient_name


MANILA_TZ = ZoneInfo("Asia/Manila")
CALLBACK_TIME_SLOTS = [
    time(hour, minute).strftime("%I:%M%p").lstrip("0").lower()
    for hour in range(8, 17)
    if hour != 12
    for minute in (0, 30)
    if hour < 16 or minute == 0
]
UNRESPONDED_STATUSES = {
    "",
    "awaiting",
    "awaiting confirmation",
    "pending",
    "unresponded",
}
ARCHIVED_STATUSES = {"cancelled", "canceled", "declined"}
NOTIFICATION_STYLES = """
<style>
.st-key-admin-notifications-page [class*="st-key-notification-row-"] {
    position: relative;
    margin-bottom: .45rem;
    padding: .55rem .7rem;
    border: 1px solid rgba(255, 255, 255, .08);
    border-radius: 14px;
    background: #112926;
    box-shadow: 0 8px 20px rgba(0, 0, 0, .12);
}
.st-key-admin-notifications-page .st-key-notification-date-filter-row {
    margin-bottom: .45rem;
}
.st-key-admin-notifications-page .notification-archive-divider {
    height: 1px;
    margin: .45rem 0 .6rem;
    background: rgba(148, 163, 184, .22);
}
.st-key-admin-notifications-page [class*="st-key-notification-row-selected-"] {
    border-color: rgba(45, 212, 191, .22);
    background: rgba(45, 212, 191, .12);
}
.st-key-admin-notifications-page [class*="st-key-notification-row-"]:hover {
    border-color: rgba(45, 212, 191, .28);
}
.st-key-admin-notifications-page .notification-row-name {
    color: #f5f1e7;
    font-size: .92rem;
    font-weight: 700;
    line-height: 1.35;
    overflow-wrap: anywhere;
}
.st-key-admin-notifications-page [class*="st-key-notification-select-"] {
    position: absolute !important;
    z-index: 2;
    inset: 0;
    margin: 0 !important;
}
.st-key-admin-notifications-page [class*="st-key-notification-select-"] button {
    position: absolute !important;
    inset: 0;
    width: 100% !important;
    height: 100% !important;
    min-height: 100% !important;
    justify-content: flex-start !important;
    margin: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    color: transparent !important;
    opacity: 0 !important;
    text-align: left !important;
}
.st-key-admin-notifications-page [class*="st-key-notification-detail-card-"] {
    padding: 24px 28px;
    border: 1px solid rgba(255, 255, 255, .08);
    border-radius: 16px;
    background: #112926;
    box-shadow: 0 14px 34px rgba(0, 0, 0, .2);
}
.st-key-admin-notifications-page .notification-detail-eyebrow {
    margin: 0 0 .25rem;
    color: #91aba5;
    font-size: .68rem;
    font-weight: 700;
    letter-spacing: .12em;
    line-height: 1.4;
    text-transform: uppercase;
}
.st-key-admin-notifications-page .notification-message-eyebrow {
    margin-top: 24px;
    margin-bottom: 0;
}
.st-key-admin-notifications-page .notification-field-label {
    margin: 0 0 6px;
    color: #91aba5;
    font-size: .68rem;
    font-weight: 700;
    letter-spacing: .12em;
    line-height: 1.4;
    text-transform: uppercase;
}
.st-key-admin-notifications-page .notification-detail-name {
    margin: 0;
    color: #f5f1e7;
    font-size: clamp(1.25rem, 2vw, 1.55rem);
    font-weight: 700;
    line-height: 1.25;
    overflow-wrap: anywhere;
}
.st-key-admin-notifications-page .notification-field-value {
    color: #f5f1e7;
    font-size: .9rem;
    font-weight: 500;
    line-height: 1.45;
    overflow-wrap: anywhere;
}
.st-key-admin-notifications-page [class*="st-key-notification-metadata-"] {
    margin-top: 20px;
    row-gap: 22px;
}
.st-key-admin-notifications-page .notification-status-wrap {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: .35rem;
}
.st-key-admin-notifications-page .notification-status-pill,
.st-key-admin-notifications-page .notification-new-pill {
    display: inline-flex;
    align-items: center;
    padding: .22rem .62rem;
    border-radius: 999px;
    font-size: .68rem;
    font-weight: 700;
    line-height: 1.35;
    white-space: nowrap;
}
.st-key-admin-notifications-page .notification-status-awaiting {
    background: rgba(217, 164, 79, .16);
    color: #e8c98d;
}
.st-key-admin-notifications-page .notification-status-scheduled {
    background: #1b4d46;
    color: #6ee7b7;
}
.st-key-admin-notifications-page .notification-status-cancelled {
    background: rgba(229, 139, 125, .16);
    color: #efb0a5;
}
.st-key-admin-notifications-page .notification-guest-pill {
    display: inline-flex;
    align-items: center;
    padding: .22rem .62rem;
    border-radius: 999px;
    background: rgba(169, 199, 193, .12);
    color: #b7cbc6;
    font-size: .68rem;
    font-weight: 700;
    line-height: 1.35;
}
.st-key-admin-notifications-page .notification-new-pill {
    padding: .16rem .48rem;
    background: rgba(45, 212, 191, .12);
    color: #9bd9ce;
    font-size: .62rem;
}
.st-key-admin-notifications-page .st-key-notification-mark-all-read-row [data-testid="stButton"] button {
    padding: 6px 14px !important;
    border: 1px solid rgba(255, 255, 255, .16) !important;
    border-radius: 8px !important;
    background: rgba(255, 255, 255, .06) !important;
    color: #e6f4f1 !important;
    box-shadow: none !important;
}
.st-key-admin-notifications-page .st-key-notification-mark-all-read-row [data-testid="stButton"] button:hover {
    border-color: rgba(255, 255, 255, .28) !important;
    background: rgba(255, 255, 255, .1) !important;
}
.st-key-admin-notifications-page [class*="st-key-notification-message-quote-"] {
    display: flex;
    align-items: center;
    min-height: 52px;
    margin-top: 8px;
    margin-bottom: 1.1rem;
    padding: 14px 16px;
    border-radius: 12px;
    background: #0c201d;
}
.st-key-admin-notifications-page .notification-message-text {
    margin: 0;
    color: #d7e5e1;
    font-size: .9rem;
    line-height: 1.6;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
}
.st-key-admin-notifications-page [class*="st-key-notification-actions-"] {
    margin-top: 1.4rem;
    padding-top: .5rem;
    row-gap: 18px;
}
.st-key-admin-notifications-page [class*="st-key-notification-detail-card-"] button {
    min-height: 2.45rem;
    border-radius: 999px !important;
    padding-inline: 1rem !important;
}
</style>
"""


def _notification_admin_id(admin_user_id=None):
    if admin_user_id is not None:
        return str(admin_user_id)
    profile = st.session_state.get("admin_profile") or {}
    return str(profile.get("user_id") or "local")


def _load_notification_read_ids(admin_user_id=None):
    conn = get_local_connection()
    try:
        rows = conn.execute(
            "SELECT notification_id FROM admin_notification_reads "
            "WHERE admin_user_id = ?",
            (_notification_admin_id(admin_user_id),),
        ).fetchall()
        return {row["notification_id"] for row in rows}
    finally:
        conn.close()


def _mark_notifications_read(
    notification_ids,
    admin_user_id=None,
    *,
    invalidate_cache=False,
):
    notification_ids = {
        str(notification_id) for notification_id in notification_ids
    }
    if not notification_ids:
        return

    conn = get_local_connection()
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO admin_notification_reads "
            "(admin_user_id, notification_id) VALUES (?, ?)",
            [
                (_notification_admin_id(admin_user_id), notification_id)
                for notification_id in notification_ids
            ],
        )
        conn.commit()
    finally:
        conn.close()
    if invalidate_cache:
        st.cache_data.clear()


def _format_requested_time(value):
    if not value:
        return "Time not set"
    for time_format in ("%H:%M:%S", "%H:%M"):
        try:
            return (
                datetime.strptime(str(value), time_format)
                .strftime("%I:%M%p")
                .lstrip("0")
                .lower()
            )
        except ValueError:
            continue
    return str(value)


def _parse_requested_time(value):
    if not value:
        return None
    for time_format in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(str(value), time_format).time()
        except ValueError:
            continue
    return None


def _format_requested_date(value):
    try:
        return date.fromisoformat(str(value)).strftime("%m/%d/%Y")
    except (TypeError, ValueError):
        return str(value or "Not provided")


def _parse_notification_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _parse_notification_updated_date(value):
    if not value:
        return None
    try:
        updated_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=MANILA_TZ)
    else:
        updated_at = updated_at.astimezone(MANILA_TZ)
    return updated_at.date()


def _partition_notification_items(items, today=None):
    today = today or date.today()
    not_responded = []
    responded = []
    archived = []

    for item in items:
        status = str(item.get("status") or "Pending").strip().casefold()
        requested_date = _parse_notification_date(item.get("requested_date"))

        if status in ARCHIVED_STATUSES:
            reference_date = (
                _parse_notification_updated_date(item.get("updated_at"))
                or requested_date
            )
            if reference_date is not None and (today - reference_date).days <= 15:
                archived.append(item)
            continue

        if status in UNRESPONDED_STATUSES:
            if requested_date is not None and requested_date < today:
                if (today - requested_date).days <= 15:
                    archived.append(item)
                continue
            not_responded.append(item)
            continue

        responded.append(item)

    return not_responded, responded, archived


def _filter_notification_items_by_date(items, requested_date):
    if requested_date is None:
        return items
    return [
        item
        for item in items
        if _parse_notification_date(item.get("requested_date")) == requested_date
    ]


def _filter_notification_items_by_search(items, query):
    normalized_query = str(query or "").strip().casefold()
    if not normalized_query:
        return items
    return [
        item
        for item in items
        if normalized_query
        in " ".join(
            str(item.get(field) or "")
            for field in ("title", "contact")
        ).casefold()
    ]


def _past_unanswered_sort_key(item):
    activity_key = _latest_activity_sort_key(item)
    requested_date = _parse_notification_date(item.get("requested_date"))
    return (
        activity_key[0],
        activity_key[1],
        requested_date or date.min,
        activity_key[2],
    )


def _partition_archived_notification_items(items, today=None):
    today = today or date.today()
    past_unanswered = []
    cancelled_requests = []

    for item in items:
        status = str(item.get("status") or "Pending").strip().casefold()
        if status in ARCHIVED_STATUSES:
            cancelled_requests.append(item)
            continue
        requested_date = _parse_notification_date(item.get("requested_date"))
        if (
            status in UNRESPONDED_STATUSES
            and requested_date is not None
            and requested_date < today
        ):
            past_unanswered.append(item)

    past_unanswered.sort(key=_past_unanswered_sort_key, reverse=True)
    cancelled_requests.sort(
        key=_latest_activity_sort_key,
        reverse=True,
    )
    return past_unanswered, cancelled_requests


def _notification_status_label(status):
    status_text = str(status or "").strip()
    return {
        "awaiting": "Awaiting confirmation",
        "awaiting confirmation": "Awaiting confirmation",
        "pending": "Awaiting confirmation",
        "unresponded": "Awaiting confirmation",
        "scheduled": "Confirmed",
        "confirmed": "Confirmed",
        "rescheduled": "Rescheduled",
        "cancelled": "Cancelled",
        "canceled": "Cancelled",
        "declined": "Declined",
        "done": "Done",
        "completed": "Done",
    }.get(status_text.casefold(), status_text or "Awaiting confirmation")


def _new_untoasted_notifications(items, read_ids, toasted_ids):
    return [
        item
        for item in items
        if item["id"] not in toasted_ids and item["id"] not in read_ids
    ]


def _select_notification_item(item_id, tab_key):
    selected_key = f"notification_selected_item:{tab_key}"
    if st.session_state.get(selected_key) != item_id:
        st.session_state["callback_action_mode"] = None
    st.session_state[selected_key] = item_id
    st.session_state[f"notification_opened_item:{tab_key}"] = item_id


def _notification_status_pill(status):
    status_key = str(status or "Pending").strip().casefold()
    if status_key in ("scheduled", "confirmed", "rescheduled", "done", "completed"):
        status_class = "scheduled"
    elif status_key in ARCHIVED_STATUSES:
        status_class = "cancelled"
    else:
        status_class = "awaiting"
    label = escape(
        "Awaiting"
        if status_key in UNRESPONDED_STATUSES
        else _notification_status_label(status)
    )
    return (
        '<span class="notification-status-pill '
        f'notification-status-{status_class}">{label}</span>'
    )


@st.cache_data(ttl=20, show_spinner=False)
def _load_notification_table(_client, table_name):
    if table_name == "appointments":
        select_columns = (
            "appointment_id, patient_name, patient_email, contact_number, "
            "reason, requested_date, requested_time_slot, approval_status, "
            "created_at, updated_at"
        )
        id_column = "appointment_id"
    elif table_name == "patient_help_requests":
        select_columns = (
            "request_id, patient_name, patient_age, patient_email, "
            "contact_number, message, requested_date, requested_time_slot, "
            "approval_status, created_at, updated_at"
        )
        id_column = "request_id"
    else:
        raise ValueError(f"Unsupported notification source: {table_name}")

    response = (
        _client.table(table_name)
        .select(select_columns)
        .order("updated_at", desc=True)
        .order("created_at", desc=True)
        .order(id_column, desc=True)
        .limit(500)
        .execute()
    )
    return response.data or []


def _clear_notification_cache():
    _load_notification_table.clear()


def _load_notifications(client):
    items = []
    errors = []

    try:
        appointments = _load_notification_table(client, "appointments")
    except Exception as error:
        errors.append(("appointments", error))
    else:
        for appointment in appointments:
            status = appointment.get("approval_status") or "Pending"
            items.append(
                {
                    "id": f"appointment:{appointment['appointment_id']}",
                    "record_id": appointment["appointment_id"],
                    "appointment_id": appointment["appointment_id"],
                    "kind": "appointment",
                    "categories": {"schedules"},
                    "title": appointment.get("patient_name") or "New appointment",
                    "summary": appointment.get("reason") or "Appointment request",
                    "email": appointment.get("patient_email"),
                    "contact": appointment.get("contact_number"),
                    "requested_date": appointment.get("requested_date"),
                    "requested_time": appointment.get("requested_time_slot"),
                    "status": status,
                    "created_at": appointment.get("created_at"),
                    "updated_at": appointment.get("updated_at"),
                    "message": None,
                }
            )

    try:
        requests = _load_notification_table(client, "patient_help_requests")
    except Exception as error:
        errors.append(("patient help requests", error))
    else:
        for request in requests:
            status = request.get("approval_status") or "Pending"
            items.append(
                {
                    "id": f"help_request:{request['request_id']}",
                    "record_id": request["request_id"],
                    "request_id": request["request_id"],
                    "kind": "help_request",
                    "categories": {"schedules", "vent_out"},
                    "title": request.get("patient_name") or "Patient",
                    "summary": "Patient Help Request",
                    "email": request.get("patient_email"),
                    "contact": request.get("contact_number"),
                    "age": request.get("patient_age"),
                    "requested_date": request.get("requested_date"),
                    "requested_time": request.get("requested_time_slot"),
                    "status": status,
                    "created_at": request.get("created_at"),
                    "updated_at": request.get("updated_at"),
                    "message": request.get("message"),
                }
            )

    items.sort(key=_latest_activity_sort_key, reverse=True)
    if not errors:
        try:
            _save_notification_snapshot(items)
        except sqlite3.Error as error:
            errors.append(("local notification snapshot", error))
    return items, errors


def _ensure_notification_snapshot_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_snapshot_cache (
            snapshot_id INTEGER PRIMARY KEY CHECK (snapshot_id = 1),
            snapshot_json TEXT NOT NULL,
            synced_at TEXT NOT NULL
        )
        """
    )


def _save_notification_snapshot(items):
    cached_items = [
        {**item, "categories": sorted(item["categories"])}
        for item in items
    ]
    synced_at = datetime.now(MANILA_TZ).isoformat(timespec="seconds")
    conn = get_local_connection()
    try:
        _ensure_notification_snapshot_table(conn)
        conn.execute(
            """
            INSERT INTO notification_snapshot_cache (
                snapshot_id, snapshot_json, synced_at
            )
            VALUES (1, ?, ?)
            ON CONFLICT(snapshot_id) DO UPDATE SET
                snapshot_json = excluded.snapshot_json,
                synced_at = excluded.synced_at
            """,
            (json.dumps(cached_items), synced_at),
        )
        conn.commit()
    finally:
        conn.close()
    return synced_at


def _load_notification_snapshot():
    conn = get_local_connection()
    try:
        _ensure_notification_snapshot_table(conn)
        conn.commit()
        row = conn.execute(
            """
            SELECT snapshot_json, synced_at
            FROM notification_snapshot_cache
            WHERE snapshot_id = 1
            """
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    try:
        items = json.loads(row["snapshot_json"])
        if not isinstance(items, list) or not isinstance(row["synced_at"], str):
            raise ValueError("The cached notification snapshot is incomplete.")
        for item in items:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or not isinstance(item.get("title"), str)
                or not isinstance(item.get("status"), str)
                or not isinstance(item.get("categories"), list)
                or not all(
                    isinstance(category, str)
                    for category in item["categories"]
                )
            ):
                raise ValueError("The cached notification snapshot is invalid.")
            item["categories"] = set(item["categories"])
        return items, row["synced_at"]
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError("The cached notification snapshot is invalid.") from error


def _toggle_callback_list_revealed():
    key = "callback_list_revealed"
    st.session_state[key] = not st.session_state[key]


def _toggle_callback_detail_revealed():
    key = "callback_detail_revealed"
    st.session_state[key] = not st.session_state[key]


def _clear_notification_filters():
    st.session_state["notification-request-search"] = ""
    st.session_state["notification-requested-date-filter"] = None
    st.session_state["notification-requested-date-filter-value"] = None


def _save_notification_date_filter():
    st.session_state["notification-requested-date-filter-value"] = st.session_state[
        "notification-requested-date-filter"
    ]


def _render_notification_request_rows(
    items,
    read_ids,
    tab_key,
    list_revealed,
    selected_id,
):
    for item in items:
        row_id = item["id"].replace(":", "-")
        is_selected = item["id"] == selected_id
        row_key = (
            f"notification-row-selected-{row_id}"
            if is_selected
            else f"notification-row-{row_id}"
        )
        with st.container(key=row_key):
            name_column, status_column = st.columns(
                [1.4, 1], vertical_alignment="center"
            )
            with name_column:
                display_name = (
                    str(item.get("title") or "Patient")
                    if list_revealed
                    else mask_patient_name(item.get("title"))
                )
                st.markdown(
                    '<div class="notification-row-name">'
                    f"{escape(display_name)}</div>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"{_format_requested_date(item.get('requested_date'))} · "
                    f"{_format_requested_time(item.get('requested_time'))}"
                )
            with status_column:
                pills = [_notification_status_pill(item.get("status"))]
                if item["id"] not in read_ids:
                    pills.append(
                        '<span class="notification-new-pill">New</span>'
                    )
                st.markdown(
                    '<div class="notification-status-wrap">'
                    + "".join(pills)
                    + "</div>",
                    unsafe_allow_html=True,
                )
            st.button(
                display_name,
                key=f"notification-select-{tab_key}-{row_id}",
                type="tertiary",
                on_click=_select_notification_item,
                args=(item["id"], tab_key),
                help="Select this patient request",
                width="stretch",
            )


def _render_notification_list(items, read_ids, tab_key, client):
    st.session_state.setdefault("callback_list_revealed", False)
    st.session_state.setdefault("callback_detail_revealed", False)
    list_revealed = st.session_state["callback_list_revealed"]
    detail_revealed = st.session_state["callback_detail_revealed"]
    list_column, detail_column = st.columns([1.05, 1.35], gap="large")
    with list_column:
        with st.container(key="notification-date-filter-row"):
            date_column, search_column, clear_column = st.columns(
                [1.2, 1.15, 0.22],
                gap="small",
                vertical_alignment="bottom",
            )
            with date_column:
                requested_date_filter = st.date_input(
                    "Requested date",
                    value=st.session_state.get(
                        "notification-requested-date-filter-value"
                    ),
                    key="notification-requested-date-filter",
                    help="Filter this tab by the requested date.",
                    on_change=_save_notification_date_filter,
                )
            with search_column:
                search_query = st.text_input(
                    "Search requests",
                    placeholder="Search name or contact...",
                    key="notification-request-search",
                    label_visibility="collapsed",
                    autocomplete="off",
                )
            with clear_column:
                st.button(
                    "✕",
                    key="notification-clear-requested-date-filter",
                    help="Clear search",
                    type="tertiary",
                    width="content",
                    disabled=(
                        not search_query.strip()
                        and requested_date_filter is None
                    ),
                    on_click=_clear_notification_filters,
                )
        visible_items = _filter_notification_items_by_date(
            items, requested_date_filter
        )
        visible_items = _filter_notification_items_by_search(
            visible_items, search_query
        )
        archived_groups = None
        if tab_key == "archived":
            archived_groups = _partition_archived_notification_items(
                visible_items
            )
            visible_items = [
                *archived_groups[0],
                *archived_groups[1],
            ]
        with st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center",
            gap="small",
        ):
            st.markdown("#### Patient Requests")
            st.button(
                "Hide" if list_revealed else "Show",
                key="toggle_callback_list_btn",
                icon=(
                    ":material/visibility_off:"
                    if list_revealed
                    else ":material/visibility:"
                ),
                help="Hide patient names" if list_revealed else "Reveal patient names",
                type="tertiary",
                width="content",
                on_click=_toggle_callback_list_revealed,
            )
    if not visible_items:
        with list_column:
            with st.container(
                height=470,
                border=False,
                key="notification-patient-requests-list",
            ):
                if archived_groups is None:
                    st.info(
                        "There are no requests matching the selected filters."
                        if requested_date_filter is not None
                        or search_query.strip()
                        else "There are no notifications in this category."
                    )
                else:
                    st.markdown("##### Past Unanswered Schedules (0)")
                    st.caption("None")
                    st.markdown(
                        '<div class="notification-archive-divider"></div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown("##### Cancelled Requests (0)")
                    st.caption("None")
        return

    selected_key = f"notification_selected_item:{tab_key}"
    selected_id = st.session_state.get(selected_key)
    if not any(item["id"] == selected_id for item in visible_items):
        selected_id = visible_items[0]["id"]
        st.session_state[selected_key] = selected_id
    selected_item = next(
        item for item in visible_items if item["id"] == selected_id
    )

    read_error = None
    opened_id = st.session_state.pop(
        f"notification_opened_item:{tab_key}", None
    )
    if opened_id == selected_item["id"] and opened_id not in read_ids:
        try:
            _mark_notifications_read([opened_id])
        except Exception as error:
            read_error = str(error)
        else:
            read_ids.add(opened_id)

    with list_column:
        with st.container(
            height=470,
            border=False,
            key="notification-patient-requests-list",
        ):
            if archived_groups is None:
                _render_notification_request_rows(
                    visible_items,
                    read_ids,
                    tab_key,
                    list_revealed,
                    selected_id,
                )
            else:
                past_unanswered, cancelled_requests = archived_groups
                st.markdown(
                    "##### Past Unanswered Schedules "
                    f"({len(past_unanswered)})"
                )
                if past_unanswered:
                    _render_notification_request_rows(
                        past_unanswered,
                        read_ids,
                        tab_key,
                        list_revealed,
                        selected_id,
                    )
                else:
                    st.caption("None")
                st.markdown(
                    '<div class="notification-archive-divider"></div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"##### Cancelled Requests ({len(cancelled_requests)})"
                )
                if cancelled_requests:
                    _render_notification_request_rows(
                        cancelled_requests,
                        read_ids,
                        tab_key,
                        list_revealed,
                        selected_id,
                    )
                else:
                    st.caption("None")

    with detail_column:
        if read_error is not None:
            st.error(
                "Unable to save this notification's read status: "
                f"{read_error}"
            )
        _render_notification_detail(
            selected_item, client, tab_key, detail_revealed
        )


def _validate_schedule_choice(requested_date, requested_time, *, help_request):
    today = datetime.now(MANILA_TZ).date()
    if requested_date < today:
        return "Choose today or a future date."
    if help_request and requested_date.weekday() > 4:
        return "Callback appointments are available Monday through Friday."
    if requested_time < time(8, 0) or requested_time > time(16, 0):
        return "Choose an appointment time between 8:00am and 4:00pm."
    if help_request and (
        requested_time.minute not in (0, 30) or requested_time.second
    ):
        return "Choose a callback time on the hour or half-hour."
    return None


def _update_notification(client, item, updates):
    table_name = (
        "patient_help_requests"
        if item["kind"] == "help_request"
        else "appointments"
    )
    id_column = "request_id" if item["kind"] == "help_request" else "appointment_id"
    try:
        response = (
            client.table(table_name)
            .update(updates)
            .eq(id_column, item["record_id"])
            .select(id_column)
            .execute()
        )
        if not response.data:
            raise RuntimeError("The request was not updated; no matching record was returned.")
    except Exception as error:
        st.error("Unable to update this appointment in Supabase.")
        with st.expander("Technical details"):
            st.code(str(error))
        return False

    from views.appointments import _invalidate_schedule_data_caches

    _invalidate_schedule_data_caches()

    new_status = updates["approval_status"]
    scheduled_date = updates.get("requested_date", item.get("requested_date"))
    scheduled_time = updates.get("requested_time_slot", item.get("requested_time"))
    schedule_changed = (
        "requested_date" in updates
        and str(updates["requested_date"]) != str(item.get("requested_date"))
    ) or (
        "requested_time_slot" in updates
        and str(updates["requested_time_slot"])
        != str(item.get("requested_time"))
    )
    if new_status == "Scheduled" and item.get("status") == "Pending":
        action_type = "REQUEST CONFIRMED"
    elif new_status == "Scheduled" and (
        item.get("status") == "Scheduled" or schedule_changed
    ):
        action_type = "APPOINTMENT RESCHEDULED"
    else:
        action_type = {
            "Scheduled": "APPOINTMENT SCHEDULED",
            "Rescheduled": "APPOINTMENT RESCHEDULED",
            "Cancelled": "APPOINTMENT CANCELLED",
        }.get(new_status, "APPOINTMENT STATUS")
    if action_type == "REQUEST CONFIRMED":
        action_details = (
            f"Confirmed a request for {item.get('title') or 'Patient'} on "
            f"{_format_requested_date(scheduled_date)} at "
            f"{_format_requested_time(scheduled_time)}."
        )
    elif action_type == "APPOINTMENT STATUS":
        action_details = (
            f"Changed appointment status for {item.get('title') or 'Patient'} "
            f"to {new_status} on {_format_requested_date(scheduled_date)} at "
            f"{_format_requested_time(scheduled_time)}."
        )
    elif action_type == "APPOINTMENT RESCHEDULED":
        action_details = (
            f"Rescheduled the appointment for {item.get('title') or 'Patient'} "
            f"from {_format_requested_date(item.get('requested_date'))} at "
            f"{_format_requested_time(item.get('requested_time'))} to "
            f"{_format_requested_date(scheduled_date)} at "
            f"{_format_requested_time(scheduled_time)}."
        )
    else:
        action_verb = {
            "APPOINTMENT RESCHEDULED": "Rescheduled",
            "APPOINTMENT SCHEDULED": "Scheduled",
            "APPOINTMENT CANCELLED": "Cancelled",
        }[action_type]
        action_details = (
            f"{action_verb} an appointment for {item.get('title') or 'Patient'} "
            f"on {_format_requested_date(scheduled_date)} at "
            f"{_format_requested_time(scheduled_time)}."
        )
    try:
        _log_appointment_action(action_type, action_details)
    except Exception as error:
        st.warning(
            "The appointment was updated, but its local activity entry "
            f"could not be written: {error}"
        )

    confirmation = {
        "Scheduled": "Request confirmed",
        "Rescheduled": "Appointment rescheduled",
        "Cancelled": "Appointment cancelled",
    }.get(new_status, f"Appointment status updated to {new_status}")
    st.session_state["notification_flash"] = (
        f"{confirmation}: {item['title']}."
    )
    return True


def _render_notification_actions(client, item, tab_key):
    st.session_state.setdefault("callback_action_mode", None)
    status = str(item.get("status") or "Pending").strip().casefold()
    if status not in UNRESPONDED_STATUSES | {
        "scheduled",
        "confirmed",
        "rescheduled",
        "cancelled",
        "canceled",
    }:
        return

    st.markdown("#### Appointment Response")
    if client is None:
        st.caption(
            "Actions are unavailable while showing the cached offline snapshot."
        )
        return
    try:
        requested_date = date.fromisoformat(item["requested_date"])
    except (TypeError, ValueError):
        requested_date = None
    requested_time = _parse_requested_time(item.get("requested_time"))
    is_help_request = item["kind"] == "help_request"
    is_confirmed = status in ("scheduled", "confirmed", "rescheduled")
    is_cancelled = status in ARCHIVED_STATUSES
    if is_cancelled:
        action_columns = st.columns(1)
        reschedule_column = action_columns[0]
        cancel_column = None
    else:
        action_columns = st.columns(3 if not is_confirmed else 2)
        reschedule_column = (
            action_columns[1] if not is_confirmed else action_columns[0]
        )
        cancel_column = (
            action_columns[2] if not is_confirmed else action_columns[1]
        )

    confirm_clicked = False
    if not is_confirmed and not is_cancelled:
        with action_columns[0]:
            confirm_clicked = st.button(
                "Confirm",
                key=f"notification_accept_{tab_key}_{item['id']}",
                type="primary",
                icon=":material/check:",
                width="stretch",
            )

    with reschedule_column:
        if st.button(
            "Reschedule",
            key=f"notification_reschedule_{tab_key}_{item['id']}",
            icon=":material/edit_calendar:",
            width="stretch",
        ):
            st.session_state["callback_action_mode"] = "reschedule"
            st.rerun()

    if cancel_column is not None:
        with cancel_column:
            if st.button(
                "Cancel",
                key=f"notification_cancel_{tab_key}_{item['id']}",
                icon=":material/event_busy:",
                width="stretch",
            ):
                st.session_state["callback_action_mode"] = "cancel"
                st.rerun()

    if confirm_clicked:
        st.session_state["callback_action_mode"] = None
        error = (
            "The original date or time is missing. Choose a replacement schedule."
            if requested_date is None or requested_time is None
            else _validate_schedule_choice(
                requested_date,
                requested_time,
                help_request=is_help_request,
            )
        )
        if error:
            st.error(error)
        elif _update_notification(
            client,
            item,
            {
                "requested_date": requested_date.isoformat(),
                "requested_time_slot": requested_time.strftime("%H:%M:%S"),
                "approval_status": "Scheduled",
            },
        ):
            st.rerun()

    if st.session_state.get("callback_action_mode") == "reschedule":
        st.markdown("#### Choose a New Schedule")
        try:
            fallback_date = date.fromisoformat(item.get("requested_date") or "")
        except ValueError:
            fallback_date = datetime.now(MANILA_TZ).date()
        requested_time_label = _format_requested_time(item.get("requested_time"))
        time_index = (
            CALLBACK_TIME_SLOTS.index(requested_time_label)
            if requested_time_label in CALLBACK_TIME_SLOTS
            else 0
        )
        date_column, time_column = st.columns(2)
        with date_column:
            new_date = st.date_input(
                "Appointment date",
                value=fallback_date,
                key=f"notification_reschedule_date_{tab_key}_{item['id']}",
                format="MM/DD/YYYY",
            )
        with time_column:
            if is_help_request:
                new_time_label = st.selectbox(
                    "Appointment time",
                    CALLBACK_TIME_SLOTS,
                    index=time_index,
                    key=f"notification_reschedule_time_{tab_key}_{item['id']}",
                )
                new_time = datetime.strptime(new_time_label, "%I:%M%p").time()
            else:
                new_time = st.time_input(
                    "Appointment time",
                    value=requested_time or time(9, 0),
                    key=f"notification_reschedule_time_{tab_key}_{item['id']}",
                    format="12h",
                )

        save_column, dismiss_column = st.columns(2)
        with save_column:
            save_reschedule = st.button(
                "Save reschedule"
                if is_confirmed or is_cancelled
                else "Set schedule and confirm",
                key=f"notification_save_reschedule_{tab_key}_{item['id']}",
                type="primary",
                width="stretch",
            )
        with dismiss_column:
            if st.button(
                "Keep current schedule",
                key=f"notification_dismiss_reschedule_{tab_key}_{item['id']}",
                width="stretch",
            ):
                st.session_state["callback_action_mode"] = None
                st.rerun()

        if save_reschedule:
            error = _validate_schedule_choice(
                new_date,
                new_time,
                help_request=is_help_request,
            )
            if error:
                st.error(error)
            elif _update_notification(
                client,
                item,
                {
                    "requested_date": new_date.isoformat(),
                    "requested_time_slot": new_time.strftime("%H:%M:%S"),
                    "approval_status": (
                        "Rescheduled"
                        if is_confirmed or is_cancelled
                        else "Scheduled"
                    ),
                },
            ):
                st.session_state["callback_action_mode"] = None
                st.rerun()

    if st.session_state.get("callback_action_mode") == "cancel":
        st.warning("Cancel this appointment request?")
        confirmed = st.checkbox(
            "Confirm cancellation",
            key=f"notification_cancel_confirm_{tab_key}_{item['id']}",
        )
        if st.button(
            "Confirm cancellation",
            key=f"notification_cancel_confirm_button_{tab_key}_{item['id']}",
            disabled=not confirmed,
        ):
            if _update_notification(
                client, item, {"approval_status": "Cancelled"}
            ):
                st.session_state["callback_action_mode"] = None
                st.rerun()


def _mask_callback_email(value):
    email = str(value or "").strip()
    if not email or email.casefold() in {
        "guest",
        "n/a",
        "not provided",
        "not provided (guest)",
    }:
        return email
    local_part, separator, domain = email.partition("@")
    if separator:
        return f"{local_part[:2]}••••@{domain}"
    return f"{email[:2]}••••"


def _mask_callback_contact(value):
    contact = str(value or "").strip()
    if (
        not contact
        or contact.casefold() in {"guest", "n/a", "not provided"}
        or len(contact) <= 7
    ):
        return contact
    return f"{contact[:4]}••••{contact[-3:]}"


def _render_notification_detail(item, client, tab_key, detail_revealed):
    email = item.get("email")
    metadata = [
        ("Email", email),
        ("Contact Number", item.get("contact") or "Not provided"),
        ("Age", item.get("age") if item.get("age") is not None else "Not provided"),
        ("Received Timestamp", _format_received_at(item.get("created_at"))),
        (
            "Requested Date & Time",
            f"{_format_requested_date(item.get('requested_date'))} · "
            f"{_format_requested_time(item.get('requested_time'))}",
        ),
    ]
    with st.container(key=f"notification-detail-card-{tab_key}"):
        header_column, status_column, reveal_column = st.columns(
            [3.2, 1, 1.35], vertical_alignment="center"
        )
        with header_column:
            display_name = (
                str(item.get("title") or "Patient")
                if detail_revealed
                else mask_patient_name(item.get("title"))
            )
            st.markdown(
                '<div class="notification-detail-eyebrow">Patient request</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="notification-detail-name">'
                f"{escape(display_name)}</div>",
                unsafe_allow_html=True,
            )
        with status_column:
            st.markdown(
                '<div class="notification-status-wrap">'
                f"{_notification_status_pill(item.get('status'))}</div>",
                unsafe_allow_html=True,
            )
        with reveal_column:
            st.button(
                "Hide" if detail_revealed else "Show",
                key="toggle_callback_detail_btn",
                icon=(
                    ":material/visibility_off:"
                    if detail_revealed
                    else ":material/visibility:"
                ),
                help="Hide patient details" if detail_revealed else "Reveal patient details",
                type="tertiary",
                width="content",
                on_click=_toggle_callback_detail_revealed,
            )

        with st.container(key=f"notification-metadata-{tab_key}"):
            for row_index in range(0, len(metadata), 2):
                left_column, right_column = st.columns(2, gap="medium")
                for column, (label, value) in zip(
                    (left_column, right_column),
                    metadata[row_index : row_index + 2],
                ):
                    with column:
                        st.markdown(
                            '<div class="notification-field-label">'
                            f"{escape(label)}</div>",
                            unsafe_allow_html=True,
                        )
                        if label == "Email":
                            email_label = _format_patient_email(value)
                            if email_label == "Not provided (Guest)":
                                st.markdown(
                                    '<span class="notification-guest-pill">'
                                    "Guest</span>",
                                    unsafe_allow_html=True,
                                )
                                continue
                            value = (
                                email_label
                                if detail_revealed
                                else _mask_callback_email(email_label)
                            )
                        elif label == "Contact Number" and not detail_revealed:
                            value = _mask_callback_contact(value)
                        st.markdown(
                            '<div class="notification-field-value">'
                            f"{escape(str(value))}</div>",
                            unsafe_allow_html=True,
                        )

        if item.get("message"):
            st.markdown(
                '<div class="notification-detail-eyebrow '
                'notification-message-eyebrow">'
                "Message from the patient</div>",
                unsafe_allow_html=True,
            )
            message = item["message"]
        else:
            st.markdown(
                '<div class="notification-detail-eyebrow '
                'notification-message-eyebrow">'
                "Request details</div>",
                unsafe_allow_html=True,
            )
            message = item.get("summary") or "No additional details were provided."
        with st.container(key=f"notification-message-quote-{tab_key}"):
            st.markdown(
                '<div class="notification-message-text">'
                f"{escape(str(message))}</div>",
                unsafe_allow_html=True,
            )

        with st.container(key=f"notification-actions-{tab_key}"):
            _render_notification_actions(client, item, tab_key)


def _render_notification_tab(items, category, read_ids, tab_key, client):
    filtered_items = [
        item for item in items if category is None or category in item["categories"]
    ]
    _render_notification_list(filtered_items, read_ids, tab_key, client)


def _render_notification_items(items, client):
    items.sort(key=_latest_activity_sort_key, reverse=True)
    try:
        read_ids = _load_notification_read_ids()
    except Exception as error:
        st.error("Unable to load saved notification read status.")
        with st.expander("Technical details"):
            st.code(str(error))
        return

    not_responded, responded, archived = _partition_notification_items(items)
    visible_items = [*not_responded, *responded, *archived]
    unread_ids = {
        item["id"] for item in visible_items if item["id"] not in read_ids
    }
    if unread_ids:
        with st.container(
            horizontal=True,
            horizontal_alignment="right",
            vertical_alignment="center",
            key="notification-mark-all-read-row",
        ):
            if st.button(
                "Mark all as read",
                key="notification-mark-all-as-read",
                type="tertiary",
                width="content",
            ):
                try:
                    _mark_notifications_read(
                        unread_ids,
                        invalidate_cache=True,
                    )
                except Exception as error:
                    st.error("Unable to mark notifications as read.")
                    with st.expander("Technical details"):
                        st.code(str(error))
                else:
                    st.rerun()

    not_responded_tab, responded_tab, archived_tab = st.tabs(
        [
            f"Not Responded ({len(not_responded)})",
            f"Responded ({len(responded)})",
            f"Archived ({len(archived)})",
        ],
        on_change="rerun",
    )
    if not_responded_tab.open:
        with not_responded_tab:
            _render_notification_tab(
                not_responded,
                None,
                read_ids,
                "not-responded",
                client,
            )
    if responded_tab.open:
        with responded_tab:
            _render_notification_tab(
                responded,
                None,
                read_ids,
                "responded",
                client,
            )
    if archived_tab.open:
        with archived_tab:
            _render_notification_tab(
                archived,
                None,
                read_ids,
                "archived",
                client,
            )


def _render_cached_notification_feed():
    try:
        cached_snapshot = _load_notification_snapshot()
    except (sqlite3.Error, ValueError) as error:
        st.error(f"Unable to read the offline notification snapshot: {error}")
        return

    if cached_snapshot is None:
        st.info(
            "Supabase is unavailable and no offline notification snapshot "
            "is available yet."
        )
        return

    items, synced_at = cached_snapshot
    st.badge(
        f"Showing cached offline snapshot (last synced {synced_at})",
        icon=":material/wifi_off:",
        color="gray",
    )
    _render_notification_items(items, client=None)


@st.fragment(run_every="5s")
def _render_live_notification_feed(client):
    if (
        not SUPABASE_URL
        or not SUPABASE_KEY
        or not is_supabase_connection_available()
    ):
        _render_cached_notification_feed()
        return

    if client is None:
        client = get_supabase_client()
    if client is None:
        _render_cached_notification_feed()
        return

    items, errors = _load_notifications(client)
    if any(is_supabase_connection_error(error) for _, error in errors):
        is_supabase_connection_available.clear()
        _render_cached_notification_feed()
        return

    for source, error in errors:
        st.error(f"Unable to load {source}.")
        with st.expander("Technical details"):
            st.code(str(error))

    if errors:
        st.warning("Some notification sources could not be loaded.")

    _render_notification_items(items, client)


@st.fragment(run_every="5s")
def render_notification_alerts(cached_items=None, cached_read_ids=None):
    items = None
    if (
        SUPABASE_URL
        and SUPABASE_KEY
        and is_supabase_connection_available()
    ):
        client = get_supabase_client()
        if client is not None:
            live_items, errors = _load_notifications(client)
            if errors:
                if any(is_supabase_connection_error(error) for _, error in errors):
                    is_supabase_connection_available.clear()
                else:
                    st.caption(
                        "Live notification updates are temporarily unavailable."
                    )
            else:
                items = live_items

    using_cached_feed = items is None
    if items is None:
        if cached_items is None:
            return
        items = cached_items

    if using_cached_feed and cached_read_ids is not None:
        read_ids = cached_read_ids
    else:
        try:
            read_ids = _load_notification_read_ids()
        except Exception as error:
            st.error("Unable to load saved notification read status.")
            with st.expander("Technical details"):
                st.code(str(error))
            return

    current_ids = {item["id"] for item in items}
    toasted_key = f"notification_toasted_ids:{_notification_admin_id()}"
    if toasted_key not in st.session_state:
        st.session_state[toasted_key] = current_ids
    else:
        toasted_ids = st.session_state[toasted_key]
        for item in _new_untoasted_notifications(
            items, read_ids, toasted_ids
        ):
            st.toast(f"New notification: {item['title']}", icon="🔔")
        st.session_state[toasted_key] = toasted_ids | current_ids


def show_notifications_page(*, appointments_page=None):
    with st.container(key="admin-notifications-page"):
        st.markdown(NOTIFICATION_STYLES, unsafe_allow_html=True)
        st.markdown(
            '<div class="notifications-eyebrow">Patient Activity</div>',
            unsafe_allow_html=True,
        )
        st.markdown("# Callback Requests")
        st.write("Review patient callback requests and manage their responses.")
        if "notification_flash" in st.session_state:
            st.success(st.session_state.pop("notification_flash"))

        client = (
            get_supabase_client()
            if SUPABASE_URL and SUPABASE_KEY
            else None
        )
        _render_live_notification_feed(client)
