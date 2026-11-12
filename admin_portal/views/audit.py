import re

import pandas as pd
import streamlit as st
from database import get_local_connection


ACTION_LABELS = {
    "PATIENT RECORD ADDED": "Patient record added",
    "PATIENT RECORD EDITED": "Patient record edited",
    "PATIENT RECORD DELETED": "Patient record deleted",
    "APPOINTMENT SCHEDULED": "Appointment scheduled",
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
            '<div class="activity-eyebrow">Admin actions</div>',
            unsafe_allow_html=True,
        )
        st.markdown("# Activity history")
        st.write(
            "Review patient record and appointment changes saved by administrators. "
            "Navigation and searches are not recorded."
        )

        try:
            conn = get_local_connection()
            try:
                df_logs = pd.read_sql_query(
                    "SELECT timestamp, action_type, details FROM admin_logs ORDER BY log_id DESC",
                    conn,
                )
            finally:
                conn.close()

            if df_logs.empty:
                st.info("No administrative activity has been captured yet.")
                return

            timestamps = pd.to_datetime(
                df_logs.pop("timestamp"), errors="coerce", utc=True
            ).dt.tz_convert("Asia/Manila")
            df_logs.insert(
                0,
                "Date and time (Philippine Time)",
                timestamps.map(
                    lambda value: (
                        value.strftime("%b %d, %Y at %I:%M %p").replace(" 0", " ")
                        if pd.notna(value)
                        else "Unknown"
                    )
                ),
            )
            formatted = [
                _format_activity(action_type, details)
                for action_type, details in zip(
                    df_logs["action_type"], df_logs["details"]
                )
            ]
            df_logs["Action"] = [action for action, _ in formatted]
            df_logs["Details"] = [details for _, details in formatted]
            df_logs = df_logs.drop(columns=["action_type", "details"])
            with st.container(border=True, key="activity-history-table"):
                st.caption(
                    "Only saved changes are listed. Times are shown in Philippine "
                    "Standard Time (UTC+08:00)."
                )
                st.dataframe(
                    df_logs,
                    width="stretch",
                    hide_index=True,
                    alt="Administrative activity history",
                )
        except Exception as error:
            st.error(f"Unable to retrieve activity history: {error}")


if __name__ == "__main__":
    show_audit_page()
