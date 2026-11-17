import datetime
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

import httpx
import streamlit as st
from supabase import create_client, Client
from supabase.lib.client_options import SyncClientOptions
from supabase_auth.errors import (
    AuthApiError,
    AuthInvalidCredentialsError,
    AuthRetryableError,
    AuthUnknownError,
)
from postgrest.exceptions import APIError as PostgrestAPIError
from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ADMIN_PORTAL_DIR = Path(__file__).resolve().parent
ENV_FILE = REPOSITORY_ROOT / ".env"

load_dotenv(dotenv_path=ENV_FILE)

configured_db_file = os.getenv("DB_FILE")
DB_FILE = Path(configured_db_file).expanduser() if configured_db_file else (
    ADMIN_PORTAL_DIR / "hfrc_local_archive.db"
)
if not DB_FILE.is_absolute():
    DB_FILE = ADMIN_PORTAL_DIR / DB_FILE
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
LOCAL_ADMIN_EMAIL = os.getenv("LOCAL_ADMIN_EMAIL", "").strip().casefold()
LOCAL_ADMIN_PASSWORD = os.getenv("LOCAL_ADMIN_PASSWORD", "")
LOCAL_ADMIN_DISPLAY_NAME = (
    os.getenv("LOCAL_ADMIN_DISPLAY_NAME", "Offline Administrator").strip()
    or "Offline Administrator"
)
LOCAL_ADMIN_ROLE = os.getenv("LOCAL_ADMIN_ROLE", "admin").strip() or "admin"

PASSWORD_HASH_ITERATIONS = 600_000
AUTH_REQUEST_TIMEOUT_SECONDS = 5
SUPABASE_REQUEST_TIMEOUT_SECONDS = 5
CONNECTIVITY_CHECK_TIMEOUT_SECONDS = 2


class OnlineAuthenticationUnavailable(ConnectionError):
    """Raised when Supabase cannot complete an online admin sign-in."""


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )


def _write_local_admin_user(
    cursor: sqlite3.Cursor,
    email: str,
    display_name: str,
    role: str,
    password: str,
    *,
    replace: bool,
) -> None:
    normalized_email = email.strip().casefold()
    if not normalized_email or not password:
        raise ValueError("A local administrator email and password are required.")

    salt = secrets.token_bytes(16)
    password_digest = _password_hash(password, salt)
    conflict_action = (
        "DO UPDATE SET display_name = excluded.display_name, "
        "role = excluded.role, password_salt = excluded.password_salt, "
        "password_hash = excluded.password_hash, "
        "hash_iterations = excluded.hash_iterations, "
        "updated_at = CURRENT_TIMESTAMP"
        if replace
        else "DO NOTHING"
    )
    cursor.execute(
        "INSERT INTO local_admin_users "
        "(email, display_name, role, password_salt, password_hash, hash_iterations) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        f"ON CONFLICT(email) {conflict_action}",
        (
            normalized_email,
            (display_name or "").strip() or normalized_email,
            (role or "").strip() or "admin",
            salt.hex(),
            password_digest.hex(),
            PASSWORD_HASH_ITERATIONS,
        ),
    )

# --- ENGINE 1: LOCAL OFFLINE SQLITE ENGINE ---
def get_local_connection():
    """Establishes an instant connection to the local, offline database cabinet."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_local_database():
    """Builds the master database schemas safely without dropping existing rows."""
    conn = get_local_connection()
    cursor = conn.cursor()
    
    # 1. Master Patient 10-Page File Schema
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        patient_id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_case_number TEXT,
        date_registered TEXT DEFAULT CURRENT_DATE,
        
        -- Page 1: Referral & Intake
        referral_noted_by TEXT,
        means_of_referral TEXT,
        interview_date TEXT,
        interview_place TEXT,
        interview_persons_present TEXT,
        primary_source_of_information TEXT,
        
        -- Core Identification Profile
        last_name TEXT NOT NULL,
        first_name TEXT NOT NULL,
        middle_name TEXT,
        extension_name TEXT,
        calculated_age INTEGER DEFAULT 0,
        street_address TEXT,
        purok TEXT,
        barangay TEXT,
        city_municipality TEXT,
        province TEXT,
        date_of_birth TEXT,
        sex TEXT,
        civil_status TEXT,
        religion TEXT,
        educational_attainment TEXT,
        status TEXT DEFAULT 'Alive',
        work_experience TEXT,
        
        -- Nearest Relatives / Guardians
        guardian_last_name TEXT,
        guardian_first_name TEXT,
        guardian_middle_name TEXT,
        guardian_street_address TEXT,
        g_barangay TEXT,
        g_city TEXT,
        g_province TEXT,
        guardian_contact_person TEXT,
        
        -- Household & Socio-Economic Classifications
        family_composition TEXT,
        total_annual_income REAL DEFAULT 0.0,
        poverty_threshold_per_year REAL DEFAULT 0.0,
        poverty_rating TEXT,
        classification_after_interview TEXT,
        classification_after_home_visit TEXT,
        
        -- Clinical Intake Mapping & Complaints
        chief_complaint_patient TEXT,
        chief_complaint_relatives TEXT,
        complaint_duration TEXT,
        complaint_recent TEXT,
        complaint_onset TEXT,
        complaint_previous_hospitalization TEXT,
        
        -- Clinical Intake Sheets & Logs
        interviewers_initial_impression TEXT,
        history_of_illness TEXT,
        mental_status_examination TEXT,
        nurses_observation TEXT,
        diagnosis TEXT,
        treatment TEXT,
        parenteral_medication_records TEXT
    );
    """)

    existing_columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(patients)").fetchall()
    }
    if "patient_case_number" not in existing_columns:
        cursor.execute("ALTER TABLE patients ADD COLUMN patient_case_number TEXT")
        existing_columns.add("patient_case_number")

    current_year = datetime.date.today().year
    case_number_pattern = re.compile(
        rf"BOC-{current_year}-(\d+)",
        re.IGNORECASE,
    )
    existing_case_numbers = cursor.execute(
        "SELECT patient_id, patient_case_number FROM patients "
        "ORDER BY patient_id"
    ).fetchall()
    used_case_numbers = {
        row["patient_case_number"].strip().casefold()
        for row in existing_case_numbers
        if row["patient_case_number"] and row["patient_case_number"].strip()
    }
    sequence = max(
        (
            int(match.group(1))
            for row in existing_case_numbers
            if row["patient_case_number"]
            and (match := case_number_pattern.fullmatch(row["patient_case_number"].strip()))
        ),
        default=0,
    )
    for row in existing_case_numbers:
        if row["patient_case_number"] and row["patient_case_number"].strip():
            continue
        while True:
            sequence += 1
            case_number = f"BOC-{current_year}-{sequence:04d}"
            if case_number.casefold() not in used_case_numbers:
                break
        cursor.execute(
            "UPDATE patients SET patient_case_number = ? WHERE patient_id = ?",
            (case_number, row["patient_id"]),
        )
        used_case_numbers.add(case_number.casefold())

    cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_case_number_unique
    ON patients(patient_case_number COLLATE NOCASE)
    WHERE patient_case_number IS NOT NULL AND TRIM(patient_case_number) != ''
    """)

    if "purok" not in existing_columns:
        cursor.execute("ALTER TABLE patients ADD COLUMN purok TEXT")
        existing_columns.add("purok")

    legacy_guardian_columns = {
        "g_barangay": "guardian_barangay",
        "g_city": "guardian_city_municipality",
        "g_province": "guardian_province",
        "g_contact_number": "guardian_contact_number",
    }
    for column in legacy_guardian_columns:
        if column not in existing_columns:
            cursor.execute(f"ALTER TABLE patients ADD COLUMN {column} TEXT")
            existing_columns.add(column)

    for column, legacy_column in legacy_guardian_columns.items():
        if legacy_column in existing_columns:
            cursor.execute(
                f"UPDATE patients SET {column} = {legacy_column} "
                f"WHERE ({column} IS NULL OR {column} = '') "
                f"AND {legacy_column} IS NOT NULL"
            )
    
    # 2. Local Appointment & Request Tracker Pipeline
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        appointment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        patient_name TEXT NOT NULL,
        contact_number TEXT,
        requested_date TEXT,
        requested_timeslot TEXT,
        approval_status TEXT DEFAULT 'Pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(patient_id) REFERENCES patients(patient_id) ON DELETE SET NULL
    );
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_appointments_requested_date
    ON appointments(requested_date);
    """)

    # 3. Local Admin Audit Activity Log Ledger
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        action_type TEXT NOT NULL,
        details TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patient_return_sessions (
        return_session_id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        session_date TEXT NOT NULL,
        session_time TEXT NOT NULL,
        notes TEXT,
        attendance_status TEXT NOT NULL,
        interview_place TEXT,
        information_noted_by TEXT,
        interview_persons_present TEXT,
        chief_complaint_patient TEXT,
        chief_complaint_relatives TEXT,
        recent_manifestations TEXT,
        new_hospitalization_since_last_visit TEXT,
        mental_status_examination TEXT,
        nurses_observation TEXT,
        diagnosis_statement TEXT,
        treatment_plan TEXT,
        parenteral_medication_records TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
    );
    """)
    return_session_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(patient_return_sessions)"
        ).fetchall()
    }
    new_return_session_columns = {
        "interview_place": "TEXT",
        "information_noted_by": "TEXT",
        "interview_persons_present": "TEXT",
        "chief_complaint_patient": "TEXT",
        "chief_complaint_relatives": "TEXT",
        "recent_manifestations": "TEXT",
        "new_hospitalization_since_last_visit": "TEXT",
        "mental_status_examination": "TEXT",
        "nurses_observation": "TEXT",
        "diagnosis_statement": "TEXT",
        "treatment_plan": "TEXT",
        "parenteral_medication_records": "TEXT",
    }
    for column, column_type in new_return_session_columns.items():
        if column not in return_session_columns:
            cursor.execute(
                f"ALTER TABLE patient_return_sessions "
                f"ADD COLUMN {column} {column_type}"
            )
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_patient_return_sessions_patient
    ON patient_return_sessions(patient_id, session_date DESC, session_time DESC);
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_notification_reads (
        admin_user_id TEXT NOT NULL,
        notification_id TEXT NOT NULL,
        read_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (admin_user_id, notification_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS local_admin_users (
        email TEXT PRIMARY KEY COLLATE NOCASE,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL,
        password_salt TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        hash_iterations INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    if LOCAL_ADMIN_EMAIL and LOCAL_ADMIN_PASSWORD:
        existing_local_admin = cursor.execute(
            "SELECT 1 FROM local_admin_users WHERE email = ?",
            (LOCAL_ADMIN_EMAIL,),
        ).fetchone()
        if existing_local_admin is None:
            _write_local_admin_user(
                cursor,
                LOCAL_ADMIN_EMAIL,
                LOCAL_ADMIN_DISPLAY_NAME,
                LOCAL_ADMIN_ROLE,
                LOCAL_ADMIN_PASSWORD,
                replace=False,
            )

    conn.commit()
    conn.close()


def get_next_patient_case_number(year=None):
    """Return the next BOC case number for the requested year."""
    target_year = int(year or datetime.date.today().year)
    year_label = f"{target_year:04d}"
    pattern = re.compile(rf"BOC-{year_label}-(\d+)", re.IGNORECASE)
    conn = get_local_connection()
    try:
        case_numbers = conn.execute(
            "SELECT patient_case_number FROM patients "
            "WHERE patient_case_number IS NOT NULL"
        ).fetchall()
        sequence = max(
            (
                int(match.group(1))
                for row in case_numbers
                if (match := pattern.fullmatch(row["patient_case_number"].strip()))
            ),
            default=0,
        )
        if sequence >= 9999:
            raise ValueError(
                f"No four-digit Patient ID sequence numbers remain for {year_label}."
            )
        return f"BOC-{year_label}-{sequence + 1:04d}"
    finally:
        conn.close()


def cache_local_admin_user(
    email: str,
    display_name: str,
    role: str,
    password: str,
) -> None:
    """Store an online-authenticated admin's current password as a salted hash."""
    conn = get_local_connection()
    try:
        _write_local_admin_user(
            conn.cursor(),
            email,
            display_name,
            role,
            password,
            replace=True,
        )
        conn.commit()
    finally:
        conn.close()


def authenticate_local_admin(email: str, password: str) -> dict[str, str]:
    """Verify an administrator against the local PBKDF2 credential cache."""
    normalized_email = email.strip().casefold()
    conn = get_local_connection()
    try:
        admin = conn.execute(
            "SELECT email, display_name, role, password_salt, password_hash, "
            "hash_iterations FROM local_admin_users WHERE email = ?",
            (normalized_email,),
        ).fetchone()
    finally:
        conn.close()

    if admin is None:
        raise PermissionError("Invalid administrator email or password.")

    candidate_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(admin["password_salt"]),
        admin["hash_iterations"],
    )
    if not hmac.compare_digest(candidate_hash.hex(), admin["password_hash"]):
        raise PermissionError("Invalid administrator email or password.")

    return {
        "user_id": f"local:{admin['email']}",
        "email": admin["email"],
        "display_name": admin["display_name"],
        "role": admin["role"],
        "auth_mode": "offline",
    }


def is_supabase_connection_error(error: Exception) -> bool:
    """Identify transport and upstream availability errors, not credential denials."""
    if isinstance(error, (httpx.RequestError, AuthRetryableError)):
        return True
    if isinstance(error, AuthUnknownError):
        return is_supabase_connection_error(error.original_error)
    if isinstance(error, AuthApiError):
        return error.status in (404, 408) or error.status >= 500
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        return status in (404, 408) or status >= 500
    if isinstance(error, PostgrestAPIError):
        code = str(error.code or "")
        if not code.isdigit():
            return False
        status = int(code)
        return status in (404, 408) or 500 <= status <= 599
    return False


@st.cache_data(ttl=5, show_spinner=False)
def is_supabase_connection_available() -> bool:
    """Return whether the configured Supabase endpoint can be reached promptly."""
    if not SUPABASE_URL:
        return False
    try:
        parsed_url = urlparse(SUPABASE_URL)
    except ValueError:
        return False
    if (
        parsed_url.scheme != "https"
        or not parsed_url.hostname
        or parsed_url.hostname in {"supabase.co", "www.supabase.co", "app.supabase.com"}
    ):
        return False

    try:
        response = httpx.get(
            f"{SUPABASE_URL.rstrip('/')}/auth/v1/health",
            timeout=httpx.Timeout(
                CONNECTIVITY_CHECK_TIMEOUT_SECONDS,
                connect=1,
            ),
        )
    except (httpx.RequestError, httpx.InvalidURL):
        return False
    return response.status_code != 404 and response.status_code < 500


def authenticate_admin(email: str, password: str) -> dict:
    """Authenticate a private-app administrator through Supabase Auth and RLS."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise OnlineAuthenticationUnavailable(
            "Supabase authentication is not configured."
        )
    normalized_email = email.strip()
    if not normalized_email or not password:
        raise PermissionError("Enter your administrator email and password.")

    try:
        parsed_url = urlparse(SUPABASE_URL)
    except ValueError as error:
        raise OnlineAuthenticationUnavailable(
            "The Supabase authentication URL is invalid."
        ) from error
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise OnlineAuthenticationUnavailable(
            "The Supabase authentication URL is invalid."
        )

    timeout = httpx.Timeout(AUTH_REQUEST_TIMEOUT_SECONDS, connect=2)
    with httpx.Client(timeout=timeout) as auth_http_client:
        options = SyncClientOptions(
            auto_refresh_token=False,
            persist_session=False,
            postgrest_client_timeout=AUTH_REQUEST_TIMEOUT_SECONDS,
            postgrest_client_retry=False,
            httpx_client=auth_http_client,
        )
        try:
            auth_client = create_client(
                SUPABASE_URL,
                SUPABASE_ANON_KEY,
                options=options,
            )
        except (ValueError, RuntimeError) as error:
            raise OnlineAuthenticationUnavailable(
                "The Supabase authentication client could not be initialized."
            ) from error

        try:
            response = auth_client.auth.sign_in_with_password(
                {"email": normalized_email, "password": password}
            )
        except AuthInvalidCredentialsError as error:
            raise PermissionError(
                "Invalid administrator email or password."
            ) from error
        except AuthApiError as error:
            if is_supabase_connection_error(error):
                raise OnlineAuthenticationUnavailable(
                    "Supabase authentication is temporarily unavailable."
                ) from error
            if error.status == 429:
                raise PermissionError(
                    "Online sign-in is temporarily rate-limited. Try again later."
                ) from error
            raise PermissionError(
                "Invalid administrator email or password."
            ) from error
        except (AuthRetryableError, AuthUnknownError, httpx.RequestError) as error:
            raise OnlineAuthenticationUnavailable(
                "Supabase authentication is temporarily unavailable."
            ) from error

        if not response.user:
            raise PermissionError("Invalid administrator email or password.")

        try:
            admin = (
                auth_client.table("admin_users")
                .select("user_id,display_name")
                .eq("user_id", response.user.id)
                .maybe_single()
                .execute()
            )
        except (httpx.RequestError, PostgrestAPIError) as error:
            if is_supabase_connection_error(error):
                raise OnlineAuthenticationUnavailable(
                    "Supabase authorization is temporarily unavailable."
                ) from error
            raise RuntimeError(
                "Supabase could not verify administrator authorization."
            ) from error

        if not admin.data:
            raise PermissionError(
                "This Supabase account is not authorized for the admin system."
            )
        return {
            "user_id": response.user.id,
            "email": response.user.email,
            "display_name": admin.data["display_name"],
            "role": "admin",
            "auth_mode": "online",
        }


# --- ENGINE 2: CLOUD SUPABASE ENGINE (Patient Web/Mobile App) ---
@st.cache_resource
def get_supabase_client() -> Client | None:
    """Safely connects to your cloud Supabase database infrastructure."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("Missing Supabase credentials in your .env environment file.")
        return None
    parsed_url = urlparse(SUPABASE_URL)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        st.error("SUPABASE_URL must be the HTTPS API URL for your Supabase project.")
        return None
    if parsed_url.hostname in {"supabase.co", "www.supabase.co", "app.supabase.com"}:
        st.error(
            "SUPABASE_URL is the generic Supabase site, not a project API URL. "
            "Use the project URL from Supabase Project Settings > API."
        )
        return None
    if SUPABASE_KEY.startswith("sb_publishable_"):
        st.error(
            "The admin scheduler needs a server-side Supabase secret/service-role key. "
            "Keep it in this desktop app's .env file only; never put it in the patient app."
        )
        return None
    try:
        client = httpx.Client(
            timeout=httpx.Timeout(SUPABASE_REQUEST_TIMEOUT_SECONDS, connect=2)
        )
        options = SyncClientOptions(
            postgrest_client_timeout=SUPABASE_REQUEST_TIMEOUT_SECONDS,
            postgrest_client_retry=False,
            httpx_client=client,
        )
        return create_client(SUPABASE_URL, SUPABASE_KEY, options=options)
    except Exception as e:
        st.error(f"Failed to instantiate cloud connection: {e}")
        return None

# Automatically run offline check on boot initialization
initialize_local_database()
