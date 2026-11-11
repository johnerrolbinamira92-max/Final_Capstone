import calendar
import datetime
import json
from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st

from database import get_local_connection
from views.record_tables import dataframe_to_storage

# Define static calendar threshold boundaries globally at the top level
MIN_BIRTH_DATE = datetime.date(1900, 1, 1)
BICOL_ADDRESS_FILE = (
    Path(__file__).resolve().parents[1] / "data" / "bicol_address_hierarchy.json"
)


@st.cache_data
def _load_bicol_address_hierarchy():
    with BICOL_ADDRESS_FILE.open(encoding="utf-8") as address_file:
        provinces = json.load(address_file)["provinces"]
    return {province["name"]: province for province in provinces}


def _clear_barangay_selection(barangay_key):
    st.session_state.pop(barangay_key, None)


def _clear_city_and_barangay_selection(city_key, barangay_key):
    _clear_barangay_selection(barangay_key)
    st.session_state.pop(city_key, None)


def _clear_birth_month_and_day(month_key, day_key):
    st.session_state.pop(month_key, None)
    st.session_state.pop(day_key, None)


def _clear_birth_day(day_key):
    st.session_state.pop(day_key, None)


def _calculate_age(birth_date, today=None):
    if birth_date is None:
        return None

    today = today or datetime.date.today()
    return today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )


def _render_birth_date(key_for):
    today = datetime.date.today()
    year_key = key_for("date_of_birth_year")
    month_key = key_for("date_of_birth_month")
    day_key = key_for("date_of_birth_day")

    st.markdown("**Date of Birth (DOB)**")
    year_column, month_column, day_column = st.columns(3)
    with year_column:
        year = st.selectbox(
            "Birth year",
            range(today.year, MIN_BIRTH_DATE.year - 1, -1),
            index=None,
            placeholder="Choose or search for a year",
            key=year_key,
            on_change=_clear_birth_month_and_day,
            args=(month_key, day_key),
        )

    latest_month = today.month if year == today.year else 12
    with month_column:
        month = st.selectbox(
            "Birth month",
            range(1, latest_month + 1),
            index=None,
            format_func=lambda value: calendar.month_name[value],
            placeholder="Choose month",
            disabled=year is None,
            key=month_key,
            on_change=_clear_birth_day,
            args=(day_key,),
        )

    if year is None or month is None:
        latest_day = 31
    elif year == today.year and month == today.month:
        latest_day = today.day
    else:
        latest_day = calendar.monthrange(year, month)[1]

    with day_column:
        day = st.selectbox(
            "Birth day",
            range(1, latest_day + 1),
            index=None,
            placeholder="Choose day",
            disabled=year is None or month is None,
            key=day_key,
        )

    if year is None or month is None or day is None:
        return None
    return datetime.date(year, month, day)


def _render_address_dropdowns(section, key_for, address_hierarchy):
    province_key = key_for(f"{section}_province")
    city_key = key_for(f"{section}_city")
    barangay_key = key_for(f"{section}_barangay")

    province_names = list(address_hierarchy)
    province_choice = st.selectbox(
        "Province",
        province_names,
        index=None,
        placeholder="Choose or search for a province",
        accept_new_options=True,
        key=province_key,
        on_change=_clear_city_and_barangay_selection,
        args=(city_key, barangay_key),
    )
    province = province_choice.strip() if province_choice else ""
    province_record = next(
        (
            record
            for name, record in address_hierarchy.items()
            if name.casefold() == province.casefold()
        ),
        None,
    )
    if province_record:
        province = province_record["name"]

    city_column, barangay_column = st.columns(2)
    with city_column:
        city_names = (
            [municipality["name"] for municipality in province_record["municipalities"]]
            if province_record
            else []
        )
        city_choice = st.selectbox(
            "City / Municipality",
            city_names,
            index=None,
            placeholder=(
                "Choose a province first"
                if not province
                else "Choose or search for a city / municipality"
            ),
            disabled=not province,
            accept_new_options=True,
            key=city_key,
            on_change=_clear_barangay_selection,
            args=(barangay_key,),
        )
        city = city_choice.strip() if city_choice else ""

    municipality = None
    if province_record and city:
        municipality = next(
            (
                item
                for item in province_record["municipalities"]
                if item["name"].casefold() == city.casefold()
            ),
            None,
        )
        if municipality:
            city = municipality["name"]

    with barangay_column:
        barangay_records = municipality["barangays"] if municipality else []
        barangay_counts = Counter(barangay["name"] for barangay in barangay_records)
        barangay_by_code = {
            barangay["code"]: barangay["name"] for barangay in barangay_records
        }

        def format_barangay(code):
            name = barangay_by_code.get(code)
            if name is None or barangay_counts[name] == 1:
                return name or code
            return f"{name} (PSGC {code})"

        barangay_choice = st.selectbox(
            "Barangay",
            list(barangay_by_code),
            format_func=format_barangay,
            index=None,
            placeholder=(
                "Choose a city / municipality first"
                if not city
                else "Choose or search for a barangay"
            ),
            disabled=not city,
            accept_new_options=True,
            key=barangay_key,
        )
        barangay = (
            barangay_by_code.get(barangay_choice, barangay_choice).strip()
            if barangay_choice
            else ""
        )

    st.caption(
        "Search the dropdowns by typing. If a location is missing, type its name "
        "and press Enter to use it."
    )

    return {
        "province": province,
        "city_municipality": city,
        "barangay": barangay,
    }


def _reset_encode_form():
    st.session_state["encode_form_version"] = (
        st.session_state.get("encode_form_version", 0) + 1
    )
    st.session_state.family_table_v2 = pd.DataFrame(columns=[
        "Full Name",
        "Age",
        "Civil Status",
        "Educational Attainment",
        "Relation to Client",
        "Occupation",
        "Monthly Income (PHP)",
    ])
    st.session_state.med_table = pd.DataFrame([{
        "Date (1)": None, "FPZ (1)": "", "Date (2)": None, "FPZ (2)": "",
        "Date (3)": None, "FPZ (3)": "",
    }])
    st.session_state["record_added_pending"] = False
    st.session_state["scroll_to_top"] = True


def _save_patient_record(payload, first_name, last_name):
    conn = get_local_connection()
    try:
        with conn:
            cursor = conn.cursor()
            columns = ", ".join(payload.keys())
            placeholders = ", ".join(["?"] * len(payload))
            query = f"INSERT INTO patients ({columns}) VALUES ({placeholders})"
            cursor.execute(query, list(payload.values()))
            patient_id = cursor.lastrowid

            cursor.execute(
                "INSERT INTO admin_logs (action_type, details) VALUES (?, ?)",
                (
                    "ENCODE",
                    f"Archived new 10-page profile folder for patient: "
                    f"{first_name} {last_name}",
                ),
            )

        saved_record = conn.execute(
            "SELECT 1 FROM patients WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        if saved_record is None:
            raise RuntimeError(
                f"Patient record {patient_id} was not found after the save committed."
            )
        return patient_id
    finally:
        conn.close()


def show_encode_page():
    form_version = st.session_state.get("encode_form_version", 0)
    widget_key = lambda name: f"encode_{form_version}_{name}"

    if st.session_state.pop("scroll_to_top", False):
        st.html(
            """
            <script>
              window.scrollTo(0, 0);
              const appView = document.querySelector('[data-testid="stAppViewContainer"]');
              const main = document.querySelector('section.main');
              if (appView) appView.scrollTop = 0;
              if (main) main.scrollTop = 0;
            </script>
            """,
            unsafe_allow_javascript=True,
        )

    with st.container(key="encode-page-header"):
        st.markdown(
            """
            <div class="encode-page-eyebrow">New patient record</div>
            <h1>Encode patient information</h1>
            <p>Digitized from the standard patient intake and clinical record sheets.</p>
            """,
            unsafe_allow_html=True,
        )

    # Initialize an empty family grid structure with clear column headers
    if "family_table_v2" not in st.session_state:
        st.session_state.family_table_v2 = pd.DataFrame(columns=[
            "Full Name", 
            "Age", 
            "Civil Status",
            "Educational Attainment", 
            "Relation to Client",
            "Occupation", 
            "Monthly Income (PHP)"
        ])

    if "med_table" not in st.session_state:
        st.session_state.med_table = pd.DataFrame([{
            "Date (1)": None, "FPZ (1)": "", "Date (2)": None, "FPZ (2)": "", "Date (3)": None, "FPZ (3)": ""
        }])

    address_hierarchy = _load_bicol_address_hierarchy()

    # --- Section Layout Form Setup ---
    st.markdown("### 🏢 Referral Context & Interview Logistics")
    c_ref1, c_ref2 = st.columns(2)
    with c_ref1:
        referral_noted_by = st.text_input("Information Noted By", placeholder="Enter staff name...", key=widget_key("referral_noted_by"))
        interview_date = st.date_input(
            "Date of Interview",
            value=None,
            min_value=MIN_BIRTH_DATE,
            max_value=datetime.date.today(),
            key=widget_key("interview_date"),
        )
        interview_place = st.text_input("Place of Interview", placeholder="Clinic, Home Address, Office...", key=widget_key("interview_place"))
    with c_ref2:
        means_of_referral = st.text_input("Means of Referral", placeholder="Walk-in, Letter, Hospital Transfer...", key=widget_key("means_of_referral"))
        primary_source_info = st.text_input("Primary Source of Information", placeholder="Patient, Mother, Guardian...", key=widget_key("primary_source_info"))

    interview_persons_present = st.text_area("Persons Present During the Interview", placeholder="List individual names...", key=widget_key("interview_persons_present"))

    st.divider()
    st.markdown("### 👤 Identifying Information: Core Profile")
    c_name1, c_name2, c_name3, c_name4 = st.columns(4)
    with c_name1: last_name = st.text_input("Last Name", placeholder="Dela Cruz", key=widget_key("last_name"))
    with c_name2: first_name = st.text_input("First Name", placeholder="Juan", key=widget_key("first_name"))
    with c_name3: middle_name = st.text_input("Middle Name", placeholder="R Ramos", key=widget_key("middle_name"))
    with c_name4: ext_name = st.text_input("Suffix", placeholder="Jr., III", key=widget_key("extension_name"))

    st.write("**Complete Client Residential Demographics:**")
    patient_address = _render_address_dropdowns(
        "patient_address",
        widget_key,
        address_hierarchy,
    )
    c_address1, c_address2 = st.columns(2)
    with c_address1:
        street_address = st.text_input(
            "Street / House Number",
            placeholder="Block 5 Lot 2",
            key=widget_key("street_address"),
            disabled=not patient_address["province"],
        )
    with c_address2:
        purok = st.text_input(
            "Purok",
            placeholder="Purok 1",
            key=widget_key("purok"),
            disabled=not patient_address["province"],
        )
    barangay = patient_address["barangay"]
    city_municipality = patient_address["city_municipality"]
    province = patient_address["province"]

    dob = _render_birth_date(widget_key)
    calculated_age = _calculate_age(dob)

    c_demo1, c_demo2, c_demo3, c_demo4 = st.columns(4)
    with c_demo1:
        age_key = widget_key("calculated_age")
        st.session_state[age_key] = (
            str(calculated_age) if calculated_age is not None else ""
        )
        st.text_input(
            "Calculated Age",
            key=age_key,
            disabled=True,
            placeholder="Select a full date of birth",
        )
    with c_demo2:
        sex = st.selectbox("Biological Sex", ["", "Male", "Female"], key=widget_key("sex"))
    with c_demo3:
        civil_status = st.selectbox("Civil Status", ["", "Single", "Married", "Widowed", "Separated"], key=widget_key("civil_status"))
        religion = st.text_input("Religion / Faith Affiliation", placeholder="Roman Catholic", key=widget_key("religion"))
    with c_demo4:
        educational = st.text_input("Highest Educational Attainment", placeholder="High School Graduate", key=widget_key("educational_attainment"))
        status = st.selectbox("Current Administrative Status", ["Alive", "Deceased"], key=widget_key("status"))

    work_experience = st.text_area("Client Work Experience & Career History Records", placeholder="Details...", key=widget_key("work_experience"))

    st.write("**Emergency Guardian Context Layout:**")
    c_guard1, c_guard2, c_guard3 = st.columns(3)
    with c_guard1:
        g_last_name = st.text_input("Guardian Last Name", placeholder="Dela Cruz", key=widget_key("guardian_last_name"))
        g_contact_person = st.text_input("Primary Contact Person Name", placeholder="Maria S. Dela Cruz", key=widget_key("guardian_contact_person"))
    with c_guard2:
        g_first_name = st.text_input("Guardian First Name", placeholder="Maria", key=widget_key("guardian_first_name"))
        g_contact_number = st.text_input("Active Contact Phone Number", placeholder="09123456789", key=widget_key("g_contact_number"))
    with c_guard3:
        g_middle_name = st.text_input("Guardian Middle Name", placeholder="Santos", key=widget_key("guardian_middle_name"))

    st.markdown("**Guardian address:**")
    guardian_address = _render_address_dropdowns(
        "guardian_address",
        widget_key,
        address_hierarchy,
    )
    g_province = guardian_address["province"]
    g_city = guardian_address["city_municipality"]
    g_barangay = guardian_address["barangay"]
    g_street = st.text_input(
        "Guardian Street / Zone",
        placeholder="Zone 1",
        key=widget_key("guardian_street_address"),
        disabled=not g_province,
    )

    st.divider()
    st.markdown("### 👨‍👩‍👧 Family Composition Table Grid")
    edited_family_df = st.data_editor(st.session_state.family_table_v2, num_rows="dynamic", width="stretch", key=widget_key("family_table"))

    st.divider()
    st.markdown("### 📊 Patient's Socio-Economic Classification Analytics")
    c_cl1, c_cl2, c_cl3 = st.columns(3)
    with c_cl1:
        annual_income = st.number_input(
            "Total Annual Income (PHP)",
            min_value=0.0,
            value=None,
            step=1000.0,
            format="%.2f",
            placeholder="0.00",
            key=widget_key("annual_income"),
        )
        class_after_interview = st.text_input("Classification After Interview Stage", placeholder="Classification status...", key=widget_key("classification_after_interview"))
    with c_cl2:
        poverty_threshold = st.number_input(
            "Poverty Threshold Per Year (PHP)",
            min_value=0.0,
            value=None,
            step=1000.0,
            format="%.2f",
            placeholder="0.00",
            key=widget_key("poverty_threshold"),
        )
        class_after_home_visit = st.text_input("Classification After Home Visit Verification", placeholder="Classification status...", key=widget_key("classification_after_home_visit"))
    with c_cl3:
        poverty_rating = st.text_input("Poverty Threshold Ratings", placeholder="Below Poverty Line", key=widget_key("poverty_rating"))

    st.divider()
    st.markdown("### 🧠 Comprehensive Chief Complaint Mapping")
    chief_complaint_patient = st.text_area("Chief Complaint: According to the Client / Patient Statement", key=widget_key("chief_complaint_patient"))
    chief_complaint_relatives = st.text_area("Chief Complaint: According to Reference / Relatives Statement", key=widget_key("chief_complaint_relatives"))

    c_comp1, c_comp2 = st.columns(2)
    with c_comp1:
        complaint_duration = st.text_input("Duration of Symptoms", placeholder="3 Months", key=widget_key("complaint_duration"))
        complaint_recent = st.text_input("Recent Manifestations", placeholder="Insomnia", key=widget_key("complaint_recent"))
    with c_comp2:
        complaint_onset = st.text_input("Onset of Condition", placeholder="Gradual after job loss", key=widget_key("complaint_onset"))
        complaint_previous_hospitalization = st.text_input("Previous Hospitalization Records", placeholder="None", key=widget_key("complaint_previous_hospitalization"))

    st.divider()
    st.markdown("### 📋 Clinical Intake Records, Examinations & Clinical Progression Sheets")
    interviewers_initial_impression = st.text_area("Interviewers Initial Impression Evaluation Notes", key=widget_key("interviewers_initial_impression"))
    history_of_illness = st.text_area("History of the Patient's Illness Narrative", key=widget_key("history_of_illness"))
    mse = st.text_area("Mental Status Examination (MSE) / Clinical Progress Notes", key=widget_key("mental_status_examination"))
    nurses_observation = st.text_area("Nurses Observation Summary During Consultation", key=widget_key("nurses_observation"))
    diagnosis = st.text_area("Official Medical Diagnosis Statement", key=widget_key("diagnosis"))
    treatment = st.text_area("Prescribed Treatment Plan Strategy", key=widget_key("treatment"))

    st.divider()
    st.markdown("### 💊 Parenteral Medication Log Sheet Grid")
    edited_med_df = st.data_editor(st.session_state.med_table, num_rows="dynamic", width="stretch", key=widget_key("med_table"))

    st.divider()
    record_added_pending = st.session_state.get("record_added_pending", False)
    submit_button = st.button(
        "Save Record",
        type="primary",
        disabled=record_added_pending,
    )

    if submit_button:
        if not last_name or not first_name:
            st.error("⚠️ Validation Error: Last Name and First Name fields must be filled.")
        else:
            try:
                # Convert active UI tabular frames to strings safely
                family_text_summary = dataframe_to_storage(edited_family_df)
                med_text_summary = dataframe_to_storage(edited_med_df)

                raw_payload = {
                    "referral_noted_by": referral_noted_by, "means_of_referral": means_of_referral,
                    "interview_date": str(interview_date) if interview_date else None, "interview_place": interview_place,
                    "interview_persons_present": interview_persons_present, "primary_source_of_information": primary_source_info,
                    "last_name": last_name, "first_name": first_name, "middle_name": middle_name, "extension_name": ext_name,
                    "calculated_age": calculated_age if calculated_age is not None else 0,
                    "street_address": street_address,
                    "purok": purok, "barangay": barangay,
                    "city_municipality": city_municipality, "province": province, "date_of_birth": str(dob) if dob else None,
                    "sex": sex, "civil_status": civil_status, "religion": religion, "educational_attainment": educational,
                    "status": status, "work_experience": work_experience, "guardian_last_name": g_last_name,
                    "guardian_first_name": g_first_name, "guardian_middle_name": g_middle_name, "guardian_street_address": g_street,
                    "g_barangay": g_barangay, "g_city": g_city, "g_province": g_province,
                    "guardian_contact_person": g_contact_person, "g_contact_number": g_contact_number,
                    "family_composition": family_text_summary,
                    "total_annual_income": (
                        float(annual_income) if annual_income is not None else 0.0
                    ),
                    "poverty_threshold_per_year": (
                        float(poverty_threshold)
                        if poverty_threshold is not None
                        else 0.0
                    ),
                    "poverty_rating": poverty_rating,
                    "classification_after_interview": class_after_interview, "classification_after_home_visit": class_after_home_visit,
                    "chief_complaint_patient": chief_complaint_patient, "chief_complaint_relatives": chief_complaint_relatives,
                    "complaint_duration": complaint_duration, "complaint_recent": complaint_recent, "complaint_onset": complaint_onset,
                    "complaint_previous_hospitalization": complaint_previous_hospitalization,
                    "interviewers_initial_impression": interviewers_initial_impression, "history_of_illness": history_of_illness,
                    "mental_status_examination": mse, "nurses_observation": nurses_observation, "diagnosis": diagnosis,
                    "treatment": treatment, "parenteral_medication_records": med_text_summary
                }

                # Filter empty parameters
                cleaned_payload = {k: v for k, v in raw_payload.items() if v != ""}

                patient_id = _save_patient_record(
                    cleaned_payload,
                    first_name,
                    last_name,
                )
                st.session_state["record_added_pending"] = True
                st.session_state["record_added_id"] = patient_id
                st.rerun()
            except Exception as e:
                st.error(f"❌ Storage Execution Error: {str(e)}")

    if st.session_state.get("record_added_pending"):
        patient_id = st.session_state.pop("record_added_id", None)
        if patient_id is not None:
            st.success(
                f"Record #{patient_id} was saved and verified in the local archive."
            )
        st.button(
            "✅ Record added — click here to clear the form",
            on_click=_reset_encode_form,
            type="primary",
        )

if __name__ == "__main__":
            show_encode_page()
