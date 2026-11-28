import re
from datetime import date

import pandas as pd
import streamlit as st
from database import get_local_connection


ACTION_CATEGORY_ORDER = (
    "Login / Logout",
    "Record Created",
    "Record Updated",
    "Record Deleted",
    "Session Logged",
    "Session Updated",
    "Session Deleted",
    "Appointment / Callback Action",
    "Export / Backup",
    "Other Action",
)

ACTION_LABELS = {
    "PATIENT RECORD ADDED": "Patient record added",
    "PATIENT RECORD EDITED": "Patient record edited",
    "PATIENT RECORD DELETED": "Patient record deleted",
    "APPOINTMENT SCHEDULED": "Appointment scheduled",
    "REQUEST CONFIRMED": "Request confirmed",
    "ADMIN APPOINTMENT SET": "Appointment set by admin",
    "APPOINTMENT RESCHEDULED": "Appointment rescheduled",
    "APPOINTMENT CANCELLED": "Appointment cancelled",
    "APPOINTMENT OUTCOME": "Appointment outcome recorded",
    "APPOINTMENT STATUS": "Appointment status updated",
    "HELP REQUEST STATUS": "Help request status updated",
}

STATUS_LABELS = {
    "Completed": "Appointment completed",
    "No-show": "No-show recorded",
    "Cancelled": "Appointment cancelled",
    "Scheduled": "Appointment scheduled",
    "Pending": "Appointment request updated",
}


def _action_category(action_type):
    normalized = str(action_type or "").strip().upper().replace("_", " ")
    if "LOGIN" in normalized or "LOGOUT" in normalized:
        return "Login / Logout"
    if "EXPORT" in normalized or "BACKUP" in normalized:
        return "Export / Backup"
    if "RETURN SESSION" in normalized or "SESSION" in normalized:
        if "DELET" in normalized or "REMOV" in normalized:
            return "Session Deleted"
        if "UPDAT" in normalized or "EDIT" in normalized:
            return "Session Updated"
        return "Session Logged"
    if "RECORD" in normalized:
        if "DELET" in normalized or "REMOV" in normalized:
            return "Record Deleted"
        if "ADD" in normalized or "CREAT" in normalized:
            return "Record Created"
        if "UPDAT" in normalized or "EDIT" in normalized or "MODIF" in normalized:
            return "Record Updated"
    if any(term in normalized for term in ("APPOINTMENT", "CALLBACK", "REQUEST")):
        return "Appointment / Callback Action"
    return "Other Action"


def _available_action_categories(action_types):
    categories = {_action_category(action_type) for action_type in action_types}
    ordered = [category for category in ACTION_CATEGORY_ORDER if category in categories]
    return ordered + sorted(categories.difference(ACTION_CATEGORY_ORDER))


def _filter_audit_entries(
    logs,
    action_filter="All Actions",
    selected_date=None,
    search_text="",
):
    timestamps = pd.to_datetime(logs["timestamp"], errors="coerce", utc=True).dt.tz_convert(
        "Asia/Manila"
    )
    action_types = logs["action_type"].fillna("").astype(str)
    raw_details = logs["details"].fillna("").astype(str)
    formatted = [
        _format_activity(action_type, details)
        for action_type, details in zip(action_types, raw_details)
    ]
    prepared = pd.DataFrame(
        {
            "_timestamp": timestamps,
            "_log_id": logs["log_id"],
            "_action_type": action_types,
            "_raw_details": raw_details,
            "Category": action_types.map(_action_category),
            "Action": [action for action, _ in formatted],
            "Details": [details for _, details in formatted],
            "Date and time (Philippine Time)": timestamps.map(
                lambda value: (
                    value.strftime("%b %d, %Y at %I:%M %p").replace(" 0", " ")
                    if pd.notna(value)
                    else "Unknown"
                )
            ),
        },
        index=logs.index,
    )
    prepared = prepared.sort_values(
        ["_timestamp", "_log_id"],
        ascending=[False, False],
        na_position="last",
        kind="stable",
    )

    if action_filter != "All Actions":
        prepared = prepared[prepared["Category"] == action_filter]
    if selected_date is not None:
        prepared = prepared[prepared["_timestamp"].dt.date == selected_date]

    search_text = str(search_text or "").strip()
    if search_text:
        searchable = prepared[
            ["_action_type", "_raw_details", "Category", "Action", "Details"]
        ].agg(" ".join, axis=1)
        prepared = prepared[
            searchable.str.contains(re.escape(search_text), case=False, na=False)
        ]

    return prepared[
        ["Date and time (Philippine Time)", "Category", "Action", "Details"]
    ].reset_index(drop=True)


def _format_activity(action_type, details):
    action_type = str(action_type or "").strip().upper()
    details = str(details or "").strip()
    action_label = ACTION_LABELS.get(
        action_type,
        action_type.replace("_", " ").title() or "Admin action",
    )

    legacy_record = re.fullmatch(
        r"Archived new 10-page profile folder for patient:\s*(.+)", details
    )
    if legacy_record:
        return "Patient record added", f"Added a patient record for {legacy_record[1]}."

    legacy_edit = re.fullmatch(
        r"Modified archived folder properties for Patient ID:\s*(\d+)\s*\((.+)\)",
        details,
    )
    if legacy_edit:
        return (
            "Patient record edited",
            f"Edited the patient record for {legacy_edit[2]} "
            f"(record {legacy_edit[1]}).",
        )

    legacy_delete = re.fullmatch(
        r"Deleted patient record\s+(\d+)\s*\((.+)\)", details
    )
    if legacy_delete:
        return (
            "Patient record deleted",
            f"Deleted the patient record for {legacy_delete[2]} "
            f"(record {legacy_delete[1]}).",
        )

    appointment_outcome = re.fullmatch(
        r"(.+): (Completed|No-show|Cancelled) on (.+) at (.+)\.", details
    ) or re.fullmatch(
        r"(.+): status changed from [\w-]+ to "
        r"(Completed|No-show|Cancelled) for (.+) at (.+)\.",
        details,
    )
    if action_type == "APPOINTMENT OUTCOME" and appointment_outcome:
        return (
            STATUS_LABELS[appointment_outcome[2]],
            f"{appointment_outcome[1]}: {appointment_outcome[3]} "
            f"at {appointment_outcome[4]}.",
        )

    legacy_status = re.fullmatch(
        r"Updated (?:(?:online )?appointment|appointments|help_request|"
        r"confidential help request) \S+ to ([\w-]+)",
        details,
    )
    if legacy_status:
        status = legacy_status[1].title()
        if status == "No-Show":
            status = "No-show"
        entity = "help request" if "help" in details.casefold() else "appointment"
        return (
            STATUS_LABELS.get(status, action_label),
            f"Updated the {entity} status to {status}.",
        )

    legacy_schedule = re.fullmatch(
        r"Created online appointment \S+ for (.+)", details
    )
    if legacy_schedule:
        return "Appointment scheduled", f"Scheduled an appointment for {legacy_schedule[1]}."

    return action_label, details or "Saved an administrative change."


def show_audit_page():
    with st.container(key="admin-activity-page"):
        st.markdown(
            '<div class="activity-eyebrow">Admin Actions</div>',
            unsafe_allow_html=True,
        )
        st.markdown("# Audit Trail")
        st.write(
            "Review saved administrative actions across patient records, sessions, "
            "appointments, and callbacks. "
            "Navigation and searches are not recorded."
        )

        try:
            conn = get_local_connection()
            try:
                df_logs = pd.read_sql_query(
                    "SELECT log_id, timestamp, action_type, details FROM admin_logs "
                    "ORDER BY timestamp DESC, log_id DESC",
                    conn,
                )
            finally:
                conn.close()

            if df_logs.empty:
                st.info("No audit entries have been captured yet.")
                return

            categories = _available_action_categories(df_logs["action_type"])
            filter_columns = st.columns([1.2, 1, 1.8], gap="small")
            with filter_columns[0]:
                action_filter = st.selectbox(
                    "Action type",
                    ["All Actions", *categories],
                    key="audit-trail-action-filter",
                )
            with filter_columns[1]:
                selected_date = st.date_input(
                    "Date (Manila)",
                    value=None,
                    key="audit-trail-date-filter",
                )
            with filter_columns[2]:
                search_text = st.text_input(
                    "Quick search",
                    placeholder="Keyword, record ID, or patient name...",
                    key="audit-trail-search",
                )

            filtered_logs = _filter_audit_entries(
                df_logs,
                action_filter=action_filter,
                selected_date=selected_date,
                search_text=search_text,
            )
            with st.container(border=True, key="audit-trail-table"):
                st.caption(
                    "Only saved changes are listed. Times are shown in Philippine "
                    "Standard Time (UTC+08:00)."
                )
                if filtered_logs.empty:
                    st.info("No audit entries match the selected filters.")
                else:
                    st.dataframe(
                        filtered_logs,
                        width="stretch",
                        hide_index=True,
                        alt="Administrative audit trail",
                    )
        except Exception as error:
            st.error(f"Unable to retrieve audit trail entries: {error}")


if __name__ == "__main__":
    show_audit_page()
