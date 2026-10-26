import os
import sqlite3
from urllib.parse import urlparse
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client, Client

# Load secure environmental variables
load_dotenv()

DB_FILE = os.getenv("DB_FILE", "hfrc_local_archive.db")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

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

    conn.commit()
    conn.close()

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
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.error(f"Failed to instantiate cloud connection: {e}")
        return None

# Automatically run offline check on boot initialization
initialize_local_database()
