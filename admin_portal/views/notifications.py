from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from database import get_local_connection, get_supabase_client
from views.appointments import _format_received_at, _log_appointment_action


MANILA_TZ = ZoneInfo("Asia/Manila")
CALLBACK_TIME_SLOTS = [
    time(hour, minute).strftime("%I:%M%p").lstrip("0").lower()
    for hour in range(9, 17)
    for minute in (0, 30)
]


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


def _mark_notifications_read(notification_ids, admin_user_id=None):
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


def _notification_status_label(status):
    return {
        "Pending": "Awaiting confirmation",
        "Scheduled": "Confirmed",
        "Rescheduled": "Rescheduled",
        "Cancelled": "Cancelled",
    }.get(status, status or "Awaiting confirmation")


def _new_unread_notifications(items, read_ids, seen_ids):
    return [
        item
        for item in items
        if item["id"] not in seen_ids and item["id"] not in read_ids
    ]


def _is_recent_notification_update(updated_at):
    if not updated_at:
        return False
    try:
        scheduled_at = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=MANILA_TZ)
    else:
        scheduled_at = scheduled_at.astimezone(MANILA_TZ)
    return datetime.now(MANILA_TZ) - scheduled_at < timedelta(days=1)


def _load_notifications(client):
    items = []
    errors = []

    try:
        response = (
            client.table("appointments")
            .select(
                "appointment_id, patient_name, contact_number, reason, "
                "requested_date, requested_time_slot, approval_status, created_at, "
                "updated_at"
            )
            .in_(
                "approval_status",
                ["Pending", "Scheduled", "Rescheduled", "Cancelled"],
            )
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
    except Exception as error:
        errors.append(("appointments", error))
    else:
        for appointment in response.data or []:
            status = appointment.get("approval_status") or "Pending"
            if status != "Pending" and not _is_recent_notification_update(
                appointment.get("updated_at")
            ):
                continue
            items.append(
                {
                    "id": f"appointment:{appointment['appointment_id']}",
                    "record_id": appointment["appointment_id"],
                    "kind": "appointment",
                    "categories": {"schedules"},
                    "title": appointment.get("patient_name") or "New appointment",
                    "summary": appointment.get("reason") or "Appointment request",
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
        response = (
            client.table("patient_help_requests")
            .select(
                "request_id, patient_name, patient_age, contact_number, message, "
                "requested_date, requested_time_slot, approval_status, created_at, "
                "updated_at"
            )
            .in_(
                "approval_status",
                ["Pending", "Scheduled", "Rescheduled", "Cancelled"],
            )
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
    except Exception as error:
        errors.append(("patient help requests", error))
    else:
        for request in response.data or []:
            status = request.get("approval_status") or "Pending"
            if status != "Pending" and not _is_recent_notification_update(
                request.get("updated_at")
            ):
                continue
            items.append(
                {
                    "id": f"help_request:{request['request_id']}",
                    "record_id": request["request_id"],
                    "kind": "help_request",
                    "categories": {"schedules", "vent_out"},
                    "title": request.get("patient_name") or "Patient",
                    "summary": "Patient Help Request",
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

    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items, errors


def _render_notification_list(items, read_ids, tab_key):
    selected_id = st.session_state.get("selected_notification_id")
    if selected_id not in {item["id"] for item in items}:
        selected_id = None

    with st.container(border=True):
        st.markdown("#### Recent activity")
        if not items:
            st.info("There are no notifications in this category.")
        for item in items:
            heading = (
                "Patient Help Request"
                if item["kind"] == "help_request"
                else "Appointment Request"
            )
            with st.expander(
                f"{heading} - {item['title']}",
                key=f"notification-preview-{tab_key}-{item['id']}",
            ):
                if item["id"] not in read_ids:
                    st.badge("New", color="red")
                st.write(f"**Name:** {item['title']}")
                st.write(
                    f"**Date:** {_format_requested_date(item.get('requested_date'))}"
                )
                st.write(
                    f"**Time:** {_format_requested_time(item.get('requested_time'))}"
                )
                st.badge(
                    _notification_status_label(item.get("status")),
                    color=(
                        "green"
                        if item.get("status") in ("Scheduled", "Rescheduled")
                        else "red"
                        if item.get("status") == "Cancelled"
                        else "orange"
                    ),
                )
                if item.get("contact"):
                    st.write(f"**Contact:** {item['contact']}")
                if item.get("age") is not None:
                    st.write(f"**Age:** {item['age']}")
                if item.get("message"):
                    st.write(f"**Message:** {item['message']}")
                elif item.get("summary"):
                    st.write(f"**Reason:** {item['summary']}")
                received_at = item.get("created_at")
                if received_at:
                    st.write(f"**Received:** {_format_received_at(received_at)}")
                if st.button(
                    "Open response details",
                    key=f"notification_select_{tab_key}_{item['id']}",
                    type="primary" if item["id"] == selected_id else "secondary",
                    width="stretch",
                ):
                    try:
                        _mark_notifications_read([item["id"]])
                    except Exception as error:
                        st.error(
                            "Unable to save this notification's read status: "
                            f"{error}"
                        )
                    else:
                        read_ids.add(item["id"])
                    st.session_state["selected_notification_id"] = item["id"]
                    selected_id = item["id"]

    return next((item for item in items if item["id"] == selected_id), None)


def _validate_schedule_choice(requested_date, requested_time, *, help_request):
    today = datetime.now(MANILA_TZ).date()
    if requested_date < today:
        return "Choose today or a future date."
    if help_request and requested_date.weekday() > 4:
        return "Callback appointments are available Monday through Friday."
    if help_request and (
        requested_time < time(9, 0) or requested_time > time(16, 30)
    ):
        return "Choose a callback time between 9:00am and 4:30pm."
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
    action_type = {
        "Scheduled": (
            "APPOINTMENT RESCHEDULED"
            if item.get("status") == "Scheduled" or schedule_changed
            else "APPOINTMENT SCHEDULED"
        ),
        "Rescheduled": "APPOINTMENT RESCHEDULED",
        "Cancelled": "APPOINTMENT CANCELLED",
    }.get(new_status, "APPOINTMENT STATUS")
    if action_type == "APPOINTMENT STATUS":
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

    if new_status in ("Scheduled", "Rescheduled"):
        scheduled_date_value = date.fromisoformat(updates["requested_date"])
        st.session_state["appointment_selected_date"] = scheduled_date_value
        st.session_state["appointment_form_date"] = scheduled_date_value
        st.session_state["appointment_calendar_month"] = scheduled_date_value.replace(day=1)
        st.session_state["appointment_flash"] = (
            f"Appointment for {item['title']} scheduled successfully."
        )
    else:
        st.session_state["notification_flash"] = (
            f"Appointment for {item['title']} cancelled."
        )
    return True


def _open_scheduled_day(appointments_page):
    if appointments_page is not None:
        st.switch_page(appointments_page)
    st.rerun()


def _render_notification_actions(client, item, appointments_page, tab_key):
    if item["status"] not in ("Pending", "Scheduled", "Rescheduled"):
        return

    st.markdown("#### Appointment response")
    try:
        requested_date = date.fromisoformat(item["requested_date"])
    except (TypeError, ValueError):
        requested_date = None
    requested_time = _parse_requested_time(item.get("requested_time"))
    is_help_request = item["kind"] == "help_request"
    fallback_date = requested_date or datetime.now(MANILA_TZ).date()
    requested_time_label = _format_requested_time(item.get("requested_time"))
    time_index = (
        CALLBACK_TIME_SLOTS.index(requested_time_label)
        if requested_time_label in CALLBACK_TIME_SLOTS
        else 0
    )
    date_key = f"notification_reschedule_date_{tab_key}_{item['id']}"
    time_key = f"notification_reschedule_time_{tab_key}_{item['id']}"
    is_confirmed = item["status"] in ("Scheduled", "Rescheduled")
    if is_confirmed:
        reschedule_column, cancel_column = st.columns(
            [1.4, 1], vertical_alignment="bottom"
        )
        accept_column = None
    else:
        reschedule_column, accept_column, cancel_column = st.columns(
            [1.4, 1, 1], vertical_alignment="bottom"
        )
    with reschedule_column:
        new_date = st.date_input(
            "Appointment date",
            value=fallback_date,
            key=date_key,
            format="MM/DD/YYYY",
        )
        if is_help_request:
            new_time_label = st.selectbox(
                "Appointment time",
                CALLBACK_TIME_SLOTS,
                index=time_index,
                key=time_key,
            )
            new_time = datetime.strptime(new_time_label, "%I:%M%p").time()
        else:
            new_time = st.time_input(
                "Appointment time",
                value=requested_time or time(9, 0),
                key=time_key,
                format="12h",
            )

    if accept_column is not None:
        with accept_column:
            if st.button(
                "Confirm appointment",
                key=f"notification_accept_{tab_key}_{item['id']}",
                type="primary",
                icon=":material/check:",
                width="stretch",
            ):
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
                    _open_scheduled_day(appointments_page)

    with cancel_column:
        if st.button(
            "Cancel appointment",
            key=f"notification_cancel_{tab_key}_{item['id']}",
            icon=":material/event_busy:",
            width="stretch",
        ):
            st.session_state["confirm_cancel_notification_id"] = item["id"]
            st.rerun()

    if st.button(
        "Reschedule appointment" if is_confirmed else "Set schedule and confirm",
        key=f"notification_reschedule_{tab_key}_{item['id']}",
        icon=":material/edit_calendar:",
        width="stretch",
    ):
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
                "approval_status": "Rescheduled" if is_confirmed else "Scheduled",
            },
        ):
            _open_scheduled_day(appointments_page)

    if st.session_state.get("confirm_cancel_notification_id") == item["id"]:
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
                st.session_state.pop("confirm_cancel_notification_id", None)
                st.rerun()


def _render_notification_detail(item, appointments_page, client, tab_key):
    with st.container(border=True):
        if item is None:
            st.markdown("#### Notification details")
            st.info("Select a notification to see its details.")
            return

        st.markdown("#### Notification details")
        heading = (
            "Patient Help Request"
            if item["kind"] == "help_request"
            else "Appointment Request"
        )
        st.markdown(f"### {heading}")
        status = item.get("status")
        st.badge(
            _notification_status_label(status),
            color=(
                "green"
                if status in ("Scheduled", "Rescheduled")
                else "red"
                if status == "Cancelled"
                else "orange"
            ),
        )
        with st.container(border=True):
            st.write(f"**Name:** {item['title']}")
            if item.get("age") is not None:
                st.write(f"**Age:** {item['age']}")
            st.write(
                f"**Date:** {_format_requested_date(item.get('requested_date'))}"
            )
            st.write(
                f"**Time:** {_format_requested_time(item.get('requested_time'))}"
            )
            st.write(f"**Received:** {_format_received_at(item.get('created_at'))}")
            st.write(f"**Contact:** {item.get('contact') or 'Not provided'}")

        if item.get("message"):
            st.markdown("**Message from the patient**")
            st.write(item["message"])
        elif item.get("summary"):
            st.markdown("**Request details**")
            st.write(item["summary"])

        _render_notification_actions(client, item, appointments_page, tab_key)

        if appointments_page is not None:
            st.page_link(
                appointments_page,
                label="Open calendar",
                icon=":material/calendar_month:",
                query_params={"focus": "schedule"},
            )


def _render_notification_tab(items, category, appointments_page, read_ids, tab_key, client):
    filtered_items = [
        item for item in items if category is None or category in item["categories"]
    ]
    list_column, detail_column = st.columns([0.85, 1.15], gap="large")
    with list_column:
        selected = _render_notification_list(filtered_items, read_ids, tab_key)
    with detail_column:
        _render_notification_detail(selected, appointments_page, client, tab_key)


@st.fragment(run_every="5s")
def _render_live_notification_feed(client, appointments_page):
    items, errors = _load_notifications(client)
    current_ids = {item["id"] for item in items}
    try:
        read_ids = _load_notification_read_ids()
    except Exception as error:
        st.error("Unable to load saved notification read status.")
        with st.expander("Technical details"):
            st.code(str(error))
        return

    selected_id = st.session_state.get("selected_notification_id")
    if selected_id not in current_ids:
        st.session_state.pop("selected_notification_id", None)

    for source, error in errors:
        st.error(f"Unable to load {source}.")
        with st.expander("Technical details"):
            st.code(str(error))

    if errors:
        st.warning("Some notification sources could not be loaded.")

    all_tab, schedules_tab, vent_out_tab = st.tabs(
        ["All notifications", "Schedules", "Vent-out notes"]
    )
    with all_tab:
        _render_notification_tab(
            items, None, appointments_page, read_ids, "all", client
        )
    with schedules_tab:
        _render_notification_tab(
            items, "schedules", appointments_page, read_ids, "schedules", client
        )
    with vent_out_tab:
        _render_notification_tab(
            items, "vent_out", appointments_page, read_ids, "vent-out", client
        )


@st.fragment(run_every="5s")
def render_notification_alerts():
    client = get_supabase_client()
    if client is None:
        return

    items, errors = _load_notifications(client)
    if errors:
        st.caption("Live notification updates are temporarily unavailable.")
        return

    try:
        read_ids = _load_notification_read_ids()
    except Exception as error:
        st.error("Unable to load saved notification read status.")
        with st.expander("Technical details"):
            st.code(str(error))
        return

    current_ids = {item["id"] for item in items}
    seen_key = f"notification_seen_ids:{_notification_admin_id()}"
    if seen_key not in st.session_state:
        st.session_state[seen_key] = current_ids
    else:
        seen_ids = st.session_state[seen_key]
        for item in _new_unread_notifications(items, read_ids, seen_ids):
            st.toast(f"New notification: {item['title']}", icon="🔔")
        st.session_state[seen_key] = seen_ids | current_ids

    unread_count = len(current_ids - read_ids)
    if unread_count:
        st.badge(f"{unread_count} unread notification(s)", color="red")


def show_notifications_page(*, appointments_page=None):
    with st.container(key="admin-notifications-page"):
        st.markdown(
            '<div class="notifications-eyebrow">Patient activity</div>',
            unsafe_allow_html=True,
        )
        st.markdown("# Notifications")
        st.write("Review appointment schedules and messages from patients.")
        if "notification_flash" in st.session_state:
            st.success(st.session_state.pop("notification_flash"))

        client = get_supabase_client()
        if client is None:
            st.stop()

        _render_live_notification_feed(client, appointments_page)
