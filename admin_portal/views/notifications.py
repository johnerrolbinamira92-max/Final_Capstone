from datetime import datetime

import streamlit as st

from database import get_supabase_client


def _format_requested_time(value):
    if not value:
        return "Time not set"
    for time_format in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(str(value), time_format).strftime(
                "%I:%M %p"
            ).lstrip("0")
        except ValueError:
            continue
    return str(value)


def _load_notifications(client):
    items = []
    errors = []

    try:
        response = (
            client.table("appointments")
            .select(
                "appointment_id, patient_name, contact_number, reason, "
                "requested_date, requested_time_slot, approval_status, created_at"
            )
            .eq("approval_status", "Pending")
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
    except Exception as error:
        errors.append(("appointments", error))
    else:
        for appointment in response.data or []:
            items.append(
                {
                    "id": f"appointment:{appointment['appointment_id']}",
                    "kind": "appointment",
                    "categories": {"schedules"},
                    "title": appointment.get("patient_name") or "New appointment",
                    "summary": appointment.get("reason") or "Appointment request",
                    "contact": appointment.get("contact_number"),
                    "requested_date": appointment.get("requested_date"),
                    "requested_time": appointment.get("requested_time_slot"),
                    "status": appointment.get("approval_status") or "Pending",
                    "created_at": appointment.get("created_at"),
                    "message": None,
                }
            )

    try:
        response = (
            client.table("patient_help_requests")
            .select(
                "request_id, patient_name, patient_age, contact_number, message, "
                "requested_date, requested_time_slot, approval_status, created_at"
            )
            .eq("approval_status", "Pending")
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
    except Exception as error:
        errors.append(("patient help requests", error))
    else:
        for request in response.data or []:
            items.append(
                {
                    "id": f"help_request:{request['request_id']}",
                    "kind": "help_request",
                    "categories": {"schedules", "vent_out"},
                    "title": request.get("patient_name") or "Patient help request",
                    "summary": "Patient help request",
                    "contact": request.get("contact_number"),
                    "age": request.get("patient_age"),
                    "requested_date": request.get("requested_date"),
                    "requested_time": request.get("requested_time_slot"),
                    "status": request.get("approval_status") or "Pending",
                    "created_at": request.get("created_at"),
                    "message": request.get("message"),
                }
            )

    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items, errors


def _render_notification_list(items, read_ids, tab_key):
    selected_id = st.session_state.get("selected_notification_id")
    if selected_id not in {item["id"] for item in items}:
        selected_id = items[0]["id"] if items else None
        st.session_state["selected_notification_id"] = selected_id

    with st.container(border=True):
        st.markdown("#### Recent activity")
        if not items:
            st.info("There are no notifications in this category.")
        for item in items:
            label = f"{item['title']}  ·  {item['summary']}"
            if item.get("requested_date"):
                label += (
                    f"\n{item['requested_date']} · "
                    f"{_format_requested_time(item.get('requested_time'))}"
                )
            with st.container(border=True):
                if item["id"] not in read_ids:
                    st.badge("New", color="red")
                if st.button(
                    label,
                    key=f"notification_select_{tab_key}_{item['id']}",
                    type="primary" if item["id"] == selected_id else "secondary",
                    width="stretch",
                ):
                    st.session_state["selected_notification_id"] = item["id"]
                    st.session_state["notification_read_ids"] = (
                        set(read_ids) | {item["id"]}
                    )
                    st.rerun()

    return next((item for item in items if item["id"] == selected_id), None)


def _render_notification_detail(item, appointments_page):
    with st.container(border=True):
        if item is None:
            st.markdown("#### Notification details")
            st.info("Select a notification to see its details.")
            return

        st.markdown("#### Notification details")
        st.markdown(f"### {item['title']}")
        st.caption(item["summary"])
        st.badge(item["status"], color="blue")
        st.divider()

        details = [
            ("Received", item.get("created_at") or "Unknown"),
            ("Requested date", item.get("requested_date") or "Not provided"),
            ("Requested time", _format_requested_time(item.get("requested_time"))),
            ("Contact", item.get("contact") or "Not provided"),
        ]
        if item.get("age") is not None:
            details.insert(1, ("Age", str(item["age"])))

        for label, value in details:
            st.markdown(f"**{label}:** {value}")

        if item.get("message"):
            st.markdown("**Message from the patient**")
            st.write(item["message"])
        elif item.get("message") is None and item.get("summary"):
            st.markdown("**Request details**")
            st.write(item["summary"])

        if appointments_page is not None:
            st.page_link(
                appointments_page,
                label="Open calendar",
                icon=":material/calendar_month:",
                query_params={"focus": "schedule"},
            )


def _render_notification_tab(items, category, appointments_page, read_ids, tab_key):
    filtered_items = [
        item for item in items if category is None or category in item["categories"]
    ]
    list_column, detail_column = st.columns([0.85, 1.15], gap="large")
    with list_column:
        selected = _render_notification_list(filtered_items, read_ids, tab_key)
    with detail_column:
        _render_notification_detail(selected, appointments_page)


def show_notifications_page(*, appointments_page=None):
    with st.container(key="admin-notifications-page"):
        st.markdown(
            '<div class="notifications-eyebrow">Patient activity</div>',
            unsafe_allow_html=True,
        )
        st.markdown("# Notifications")
        st.write("Review appointment schedules and messages from patients.")

        client = get_supabase_client()
        if client is None:
            st.stop()

        items, errors = _load_notifications(client)
        read_ids = set(st.session_state.get("notification_read_ids", set()))
        unread_count = sum(item["id"] not in read_ids for item in items)
        action_column, count_column = st.columns(
            [1, 2], vertical_alignment="center"
        )
        with action_column:
            if st.button(
                "Mark all as read",
                key="notifications-mark-all-read",
                icon=":material/done_all:",
                width="stretch",
                disabled=unread_count == 0,
            ):
                st.session_state["notification_read_ids"] = read_ids | {
                    item["id"] for item in items
                }
                st.rerun()
        with count_column:
            st.caption(f"{unread_count} unread notification(s)")

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
            _render_notification_tab(items, None, appointments_page, read_ids, "all")
        with schedules_tab:
            _render_notification_tab(
                items, "schedules", appointments_page, read_ids, "schedules"
            )
        with vent_out_tab:
            _render_notification_tab(
                items, "vent_out", appointments_page, read_ids, "vent-out"
            )
