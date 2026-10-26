import pandas as pd
import streamlit as st
from database import get_local_connection


def show_audit_page():
    st.title("Administrative Audit Ledger")
    st.write("Review administrative actions recorded in the local archive.")

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
            st.info("No system administrative actions have been captured yet.")
            return

        timestamps = pd.to_datetime(
            df_logs.pop("timestamp"), errors="coerce", utc=True
        ).dt.tz_convert("Asia/Manila")
        df_logs.insert(0, "Date (Philippine Time)", timestamps.dt.strftime("%Y-%m-%d"))
        df_logs.insert(1, "Time (Philippine Time)", timestamps.dt.strftime("%H:%M:%S"))
        df_logs.columns = [
            "Date (Philippine Time)",
            "Time (Philippine Time)",
            "Action Type",
            "Action Details",
        ]
        st.caption("All ledger timestamps are displayed in Philippine Standard Time (UTC+08:00).")
        st.dataframe(
            df_logs,
            width="stretch",
            hide_index=True,
            alt="Administrative audit log entries",
        )
    except Exception as e:
        st.error(f"Audit ledger retrieval failure: {e}")


if __name__ == "__main__":
    show_audit_page()
