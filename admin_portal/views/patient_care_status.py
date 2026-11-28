from datetime import date, datetime
from zoneinfo import ZoneInfo


CARE_STATUS_ACTIVE = "Active"
CARE_STATUS_LOST_TO_FOLLOW_UP = "Lost to Follow-Up"
CARE_STATUS_DECEASED = "Deceased"
CARE_STATUS_COLORS = {
    CARE_STATUS_ACTIVE: "#00a394",
    CARE_STATUS_LOST_TO_FOLLOW_UP: "#f2b84b",
    CARE_STATUS_DECEASED: "#94a3b8",
}
CARE_STATUS_DATE_COLUMNS = ("date_encoded", "date_registered", "created_at")


def _parse_care_date(value):
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(ZoneInfo("Asia/Manila")).date()
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    date_text = str(value).strip()
    if not date_text:
        return None
    try:
        parsed_datetime = datetime.fromisoformat(
            date_text.replace("Z", "+00:00")
        )
    except ValueError:
        parsed_datetime = None
    if parsed_datetime is not None:
        if parsed_datetime.tzinfo is not None:
            return parsed_datetime.astimezone(ZoneInfo("Asia/Manila")).date()
        return parsed_datetime.date()
    try:
        return date.fromisoformat(date_text[:10])
    except ValueError:
        return None


def classify_patient_care_status(
    status,
    *initial_dates,
    latest_return_session_date=None,
    today=None,
):
    if str(status or "").strip().casefold() == "deceased":
        return CARE_STATUS_DECEASED

    reference_dates = [
        parsed_date
        for parsed_date in (
            *(_parse_care_date(value) for value in initial_dates),
            _parse_care_date(latest_return_session_date),
        )
        if parsed_date is not None
    ]
    latest_care_date = max(reference_dates, default=None)
    today = today or datetime.now(ZoneInfo("Asia/Manila")).date()
    if latest_care_date is not None and (today - latest_care_date).days <= 365:
        return CARE_STATUS_ACTIVE
    return CARE_STATUS_LOST_TO_FOLLOW_UP


def load_patient_care_statuses(connection, *, today=None):
    patient_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(patients)")
    }
    if not {"patient_id", "status"}.issubset(patient_columns):
        raise ValueError("The patient table is missing required status columns.")

    date_selects = [
        f'p."{column}" AS "{column}"'
        if column in patient_columns
        else f'NULL AS "{column}"'
        for column in CARE_STATUS_DATE_COLUMNS
    ]
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    has_return_sessions = "patient_return_sessions" in tables
    if has_return_sessions:
        session_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(patient_return_sessions)"
            )
        }
        has_return_sessions = {
            "patient_id",
            "session_date",
        }.issubset(session_columns)

    session_join = (
        """
        LEFT JOIN (
            SELECT patient_id, MAX(session_date) AS latest_return_session_date
            FROM patient_return_sessions
            GROUP BY patient_id
        ) AS sessions ON sessions.patient_id = p.patient_id
        """
        if has_return_sessions
        else ""
    )
    session_date = (
        "sessions.latest_return_session_date"
        if has_return_sessions
        else "NULL"
    )
    rows = connection.execute(
        f"""
        SELECT p.patient_id, p.status, {", ".join(date_selects)},
               {session_date} AS latest_return_session_date
        FROM patients AS p
        {session_join}
        """
    ).fetchall()

    return {
        row["patient_id"]: classify_patient_care_status(
            row["status"],
            *(row[column] for column in CARE_STATUS_DATE_COLUMNS),
            latest_return_session_date=row["latest_return_session_date"],
            today=today,
        )
        for row in rows
    }
