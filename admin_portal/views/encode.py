import datetime
import json
from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st

from database import (
    get_local_connection,
    get_next_patient_case_number,
)
from views.patient_intake import (
    ADMINISTRATIVE_STATUS_OPTIONS,
    CIVIL_STATUS_OPTIONS,
    EDUCATIONAL_ATTAINMENT_OPTIONS,
    FIELD_LABELS,
    INFORMATION_NOTED_BY_OPTIONS,
    MIN_BIRTH_DATE,
    SECTION_TITLES,
    SEX_OPTIONS,
)
from views.record_tables import (
    DATE_DISPLAY_FORMAT,
    FAMILY_COLUMNS,
    MEDICATION_COLUMN_LABELS,
    MEDICATION_COLUMNS,
    dataframe_from_storage,
    dataframe_to_storage,
    family_column_config,
)

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


def _is_four_digit_value(value):
    return (
        len(value) == 4
        and value.isascii()
        and value.isdigit()
        and int(value) > 0
    )


def _refresh_case_number_sequence(year_key, sequence_key):
    year = st.session_state.get(year_key, "")
    if _is_four_digit_value(year):
        error_key = f"{sequence_key}_error"
        try:
            st.session_state[sequence_key] = get_next_patient_case_number(
                int(year)
            ).rsplit("-", 1)[1]
        except ValueError as error:
            st.session_state[sequence_key] = ""
            st.session_state[error_key] = str(error)
        else:
            st.session_state.pop(error_key, None)


def _initialize_case_number_inputs(year_key, sequence_key):
    if year_key not in st.session_state:
        st.session_state[year_key] = str(datetime.date.today().year)
    refresh_case_number = st.session_state.pop(
        "encode_case_number_refresh_pending",
        False,
    )
    if sequence_key not in st.session_state:
        st.session_state[sequence_key] = ""
        refresh_case_number = True
    if refresh_case_number:
        st.session_state[sequence_key] = ""
        st.session_state.pop(f"{sequence_key}_error", None)
        _refresh_case_number_sequence(year_key, sequence_key)


def _calculate_age(birth_date, today=None):
    if birth_date is None:
        return None

    today = today or datetime.date.today()
    return today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )


def _render_birth_date(key_for, initial_date=None):
    today = datetime.date.today()
    if initial_date is not None and not MIN_BIRTH_DATE <= initial_date <= today:
        initial_date = None
    return st.date_input(
        FIELD_LABELS["date_of_birth"].rstrip(":"),
        value=initial_date,
        min_value=MIN_BIRTH_DATE,
        max_value=today,
        format=DATE_DISPLAY_FORMAT,
        key=key_for("date_of_birth_input"),
    )


def _render_address_dropdowns(
    section,
    key_for,
    address_hierarchy,
    initial_values=None,
):
    province_key = key_for(f"{section}_province")
    city_key = key_for(f"{section}_city")
    barangay_key = key_for(f"{section}_barangay")
    initial_values = initial_values or {}

    province_names = list(address_hierarchy)
    initial_province = str(initial_values.get("province") or "").strip()
    if province_key not in st.session_state and initial_province:
        province_match = next(
            (
                name
                for name in province_names
                if name.casefold() == initial_province.casefold()
            ),
            initial_province,
        )
        st.session_state[province_key] = province_match

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
        initial_city = str(initial_values.get("city_municipality") or "").strip()
        if city_key not in st.session_state and initial_city:
            city_match = next(
                (
                    name
                    for name in city_names
                    if name.casefold() == initial_city.casefold()
                ),
                initial_city,
            )
            st.session_state[city_key] = city_match
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
        initial_barangay = str(initial_values.get("barangay") or "").strip()
        if barangay_key not in st.session_state and initial_barangay:
            barangay_code = next(
                (
                    code
                    for code, name in barangay_by_code.items()
                    if name.casefold() == initial_barangay.casefold()
                ),
                initial_barangay,
            )
            st.session_state[barangay_key] = barangay_code

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


def _reset_encode_form(*, scroll_to_top=True):
    st.session_state["encode_form_version"] = (
        st.session_state.get("encode_form_version", 0) + 1
    )
    st.session_state.family_table_v2 = pd.DataFrame(columns=FAMILY_COLUMNS)
    st.session_state.med_table = pd.DataFrame([{
        "Date (1)": None, "FPZ (1)": "", "Date (2)": None, "FPZ (2)": "",
        "Date (3)": None, "FPZ (3)": "",
    }])
    st.session_state["record_added_pending"] = False
    st.session_state.pop("record_added_case_number", None)
    st.session_state["scroll_to_top"] = scroll_to_top


def _open_encode_dialog():
    st.session_state["show_encode_dialog"] = True
    st.session_state["encode_case_number_refresh_pending"] = True


def _save_patient_record(payload, first_name, last_name):
    conn = get_local_connection()
    try:
        with conn:
            case_number = str(payload.get("patient_case_number", "")).strip()
            if not case_number:
                raise ValueError("Patient ID / Case Number is required.")
            payload["patient_case_number"] = case_number

            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            duplicate = cursor.execute(
                "SELECT patient_id FROM patients "
                "WHERE patient_case_number = ? COLLATE NOCASE",
                (case_number,),
            ).fetchone()
            if duplicate is not None:
                raise ValueError(
                    f"Patient ID / Case Number '{case_number}' is already in use."
                )

            columns = ", ".join(payload.keys())
            placeholders = ", ".join(["?"] * len(payload))
            query = f"INSERT INTO patients ({columns}) VALUES ({placeholders})"
            cursor.execute(query, list(payload.values()))
            patient_id = cursor.lastrowid

            cursor.execute(
                "INSERT INTO admin_logs (action_type, details) VALUES (?, ?)",
                (
                    "PATIENT RECORD ADDED",
                    f"Added patient record for {first_name} {last_name} "
                    f"(record {patient_id}).",
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
    encode_success_toast = st.session_state.pop("encode_success_toast", None)
    if encode_success_toast:
        st.toast(encode_success_toast)

    form_version = st.session_state.get("encode_form_version", 0)
    widget_key = lambda name: f"encode_{form_version}_{name}"

    if st.session_state.pop("scroll_to_top", False):
        st.html(
            """
            <script>
              const scrollEncodePageToTop = () => {
                const scrollTargets = [
                  document.scrollingElement,
                  document.querySelector('[data-testid="stAppViewContainer"]'),
                  document.querySelector('[data-testid="stMain"]'),
                  document.querySelector('section.main'),
                ];
                scrollTargets.forEach((target) => {
                  if (target) target.scrollTop = 0;
                });
                window.scrollTo({ top: 0, behavior: "smooth" });
              };

              requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                  scrollEncodePageToTop();
                  setTimeout(scrollEncodePageToTop, 120);
                });
              });
            </script>
            """,
            unsafe_allow_javascript=True,
        )

    with st.container(key="encode-page-header"):
        st.markdown(
            """
            <div class="encode-page-eyebrow">New Patient Record</div>
            <h1>Encode Patient Information</h1>
            <p>Digitized from the standard patient intake and clinical record sheets.</p>
            """,
            unsafe_allow_html=True,
        )

    if "family_table_v2" not in st.session_state:
        st.session_state.family_table_v2 = pd.DataFrame(columns=FAMILY_COLUMNS)
    else:
        st.session_state.family_table_v2 = dataframe_from_storage(
            dataframe_to_storage(st.session_state.family_table_v2),
            FAMILY_COLUMNS,
        )

    if "med_table" not in st.session_state:
        st.session_state.med_table = pd.DataFrame([{
            "Date (1)": None, "FPZ (1)": "", "Date (2)": None, "FPZ (2)": "", "Date (3)": None, "FPZ (3)": ""
        }])

    address_hierarchy = _load_bicol_address_hierarchy()

    year_key = widget_key("patient_case_year")
    sequence_key = widget_key("patient_case_sequence")
    _initialize_case_number_inputs(year_key, sequence_key)

    today = datetime.date.today()
    with st.container(border=True, key="encode-intake-section-administration"):
        st.markdown(f"#### {SECTION_TITLES['administration']}")
        st.markdown(f"**{FIELD_LABELS['patient_case_number']}**")
        with st.container(
            horizontal=True,
            wrap=False,
            vertical_alignment="center",
            gap="small",
        ):
            st.markdown("**BOC -**", width="content")
            patient_year = st.text_input(
                "Year",
                key=year_key,
                max_chars=4,
                placeholder="YYYY",
                on_change=_refresh_case_number_sequence,
                args=(year_key, sequence_key),
                label_visibility="collapsed",
                width=76,
            ).strip()
            st.markdown("**-**", width="content")
            patient_sequence = st.text_input(
                "Unique number",
                key=sequence_key,
                max_chars=4,
                placeholder="0001",
                label_visibility="collapsed",
                width=80,
            ).strip()
        patient_case_number = (
            f"BOC-{patient_year}-{patient_sequence}"
            if _is_four_digit_value(patient_year)
            and _is_four_digit_value(patient_sequence)
            else ""
        )
        st.caption(
            "The unique number is auto-filled from the selected year and remains "
            "editable."
        )
        sequence_error = st.session_state.get(f"{sequence_key}_error")
        if sequence_error:
            st.error(sequence_error)
        status = st.selectbox(
            FIELD_LABELS["status"],
            ADMINISTRATIVE_STATUS_OPTIONS,
            key=widget_key("status"),
        )

    with st.container(border=True, key="encode-intake-section-referral"):
        st.markdown(f"#### {SECTION_TITLES['referral']}")
        referral_left, referral_right = st.columns(2)
        with referral_left:
            referral_noted_by = st.selectbox(
                FIELD_LABELS["referral_noted_by"],
                INFORMATION_NOTED_BY_OPTIONS,
                index=None,
                accept_new_options=True,
                key=widget_key("referral_noted_by_select"),
            )
            referring_person_or_instance = st.text_input(
                FIELD_LABELS["referring_person_or_instance"],
                key=widget_key("referring_person_or_instance"),
            )
            date_of_referral = st.date_input(
                FIELD_LABELS["date_of_referral"],
                value=None,
                min_value=MIN_BIRTH_DATE,
                max_value=today,
                format=DATE_DISPLAY_FORMAT,
                key=widget_key("date_of_referral"),
            )
        with referral_right:
            means_of_referral = st.text_input(
                FIELD_LABELS["means_of_referral"],
                key=widget_key("means_of_referral"),
            )
            referral_request = st.text_area(
                FIELD_LABELS["referral_request"],
                key=widget_key("referral_request"),
            )
        agreements_made_for_further_interviewing = st.text_area(
            FIELD_LABELS["agreements_made_for_further_interviewing"],
            key=widget_key("agreements_made_for_further_interviewing"),
        )

    with st.container(border=True, key="encode-intake-section-interview"):
        st.markdown(f"#### {SECTION_TITLES['interview']}")
        interview_left, interview_right = st.columns(2)
        with interview_left:
            interview_date = st.date_input(
                FIELD_LABELS["interview_date"],
                value=None,
                min_value=MIN_BIRTH_DATE,
                max_value=today,
                format=DATE_DISPLAY_FORMAT,
                key=widget_key("interview_date"),
            )
            interview_place = st.text_input(
                FIELD_LABELS["interview_place"],
                key=widget_key("interview_place"),
            )
        with interview_right:
            interview_persons_present = st.text_area(
                FIELD_LABELS["interview_persons_present"],
                key=widget_key("interview_persons_present"),
            )
            primary_source_info = st.text_input(
                FIELD_LABELS["primary_source_of_information"],
                key=widget_key("primary_source_info"),
            )

    with st.container(border=True, key="encode-intake-section-identifying"):
        st.markdown(f"#### {SECTION_TITLES['identifying']}")
        st.markdown(f"##### {SECTION_TITLES['client']}")
        st.markdown(f"**{FIELD_LABELS['client_name']}**")
        name_columns = st.columns(4)
        with name_columns[0]:
            first_name = st.text_input(
                "First Name",
                placeholder="Juan",
                key=widget_key("first_name"),
            )
        with name_columns[1]:
            middle_name = st.text_input(
                "Middle Name",
                placeholder="R Ramos",
                key=widget_key("middle_name"),
            )
        with name_columns[2]:
            last_name = st.text_input(
                "Last Name",
                placeholder="Dela Cruz",
                key=widget_key("last_name"),
            )
        with name_columns[3]:
            ext_name = st.text_input(
                "Extension Name",
                placeholder="Jr., III",
                key=widget_key("extension_name"),
            )

        dob = _render_birth_date(widget_key)
        calculated_age = _calculate_age(dob)
        age_key = widget_key("calculated_age")
        st.session_state[age_key] = (
            str(calculated_age) if calculated_age is not None else ""
        )
        st.text_input(
            FIELD_LABELS["age"],
            key=age_key,
            disabled=True,
            placeholder="Calculated from Date of Birth",
        )

        st.markdown(f"**{FIELD_LABELS['address']}**")
        patient_address = _render_address_dropdowns(
            "patient_address",
            widget_key,
            address_hierarchy,
        )
        address_columns = st.columns(2)
        with address_columns[0]:
            street_address = st.text_input(
                "Street / House Number",
                placeholder="Block 5 Lot 2",
                key=widget_key("street_address"),
                disabled=not patient_address["province"],
            )
        with address_columns[1]:
            purok = st.text_input(
                "Purok",
                placeholder="Purok 1",
                key=widget_key("purok"),
                disabled=not patient_address["province"],
            )
        barangay = patient_address["barangay"]
        city_municipality = patient_address["city_municipality"]
        province = patient_address["province"]

        demo_left, demo_right = st.columns(2)
        with demo_left:
            sex = st.selectbox(
                FIELD_LABELS["sex"],
                SEX_OPTIONS,
                index=None,
                key=widget_key("sex_v2"),
            )
            civil_status = st.selectbox(
                FIELD_LABELS["civil_status"],
                CIVIL_STATUS_OPTIONS,
                key=widget_key("civil_status"),
            )
        with demo_right:
            religion = st.text_input(
                FIELD_LABELS["religion"],
                key=widget_key("religion"),
            )
            educational = st.selectbox(
                FIELD_LABELS["educational_attainment"],
                EDUCATIONAL_ATTAINMENT_OPTIONS,
                index=None,
                accept_new_options=True,
                key=widget_key("educational_attainment_select"),
            )
        work_experience = st.text_area(
            FIELD_LABELS["work_experience"],
            key=widget_key("work_experience"),
        )

    with st.container(border=True, key="encode-intake-section-relatives"):
        st.markdown(f"#### {SECTION_TITLES['relatives']}")
        guardian_name = st.text_input(
            "Name",
            key=widget_key("guardian_name"),
        )
        g_first_name = guardian_name
        g_middle_name = ""
        g_last_name = ""
        st.markdown(f"**{FIELD_LABELS['address']}**")
        guardian_address = _render_address_dropdowns(
            "guardian_address",
            widget_key,
            address_hierarchy,
        )
        guardian_address_columns = st.columns(2)
        with guardian_address_columns[0]:
            g_street = st.text_input(
                "Street / Zone",
                placeholder="Zone 1",
                key=widget_key("guardian_street_address"),
                disabled=not guardian_address["province"],
            )
        with guardian_address_columns[1]:
            g_contact_person = st.text_input(
                FIELD_LABELS["contact_person"],
                placeholder="Same as Nearest Relative (or enter alternate contact)",
                key=widget_key("guardian_contact_person"),
            )
        g_barangay = guardian_address["barangay"]
        g_city = guardian_address["city_municipality"]
        g_province = guardian_address["province"]
        g_contact_number = st.text_input(
            FIELD_LABELS["contact_number"],
            key=widget_key("g_contact_number"),
        )

    with st.container(border=True, key="encode-intake-section-family"):
        st.markdown(f"#### {SECTION_TITLES['family']}")
        edited_family_df = st.data_editor(
            st.session_state.family_table_v2,
            num_rows="dynamic",
            width="stretch",
            key=widget_key("family_table"),
            column_config=family_column_config(st.session_state.family_table_v2),
            alt="Family composition of the patient",
        )

    with st.container(border=True, key="encode-intake-section-classification"):
        st.markdown(f"#### {SECTION_TITLES['classification']}")
        classification_left, classification_right = st.columns(2)
        with classification_left:
            household_member_count = st.number_input(
                FIELD_LABELS["household_member_count"],
                min_value=0,
                value=None,
                step=1,
                key=widget_key("household_member_count"),
            )
            annual_income = st.number_input(
                FIELD_LABELS["total_annual_income"],
                min_value=0.0,
                value=None,
                step=1000.0,
                format="%.2f",
                key=widget_key("annual_income"),
            )
            poverty_threshold = st.number_input(
                FIELD_LABELS["poverty_threshold_per_year"],
                min_value=0.0,
                value=None,
                step=1000.0,
                format="%.2f",
                key=widget_key("poverty_threshold"),
            )
        with classification_right:
            poverty_rating = st.text_input(
                FIELD_LABELS["poverty_rating"],
                key=widget_key("poverty_rating"),
            )
            class_after_interview = st.text_input(
                FIELD_LABELS["classification_after_interview"],
                key=widget_key("classification_after_interview"),
            )
            class_after_home_visit = st.text_input(
                FIELD_LABELS["classification_after_home_visit"],
                key=widget_key("classification_after_home_visit"),
            )

    with st.container(border=True, key="encode-intake-section-complaint"):
        st.markdown(f"#### {SECTION_TITLES['complaint']}")
        chief_complaint_patient = st.text_area(
            FIELD_LABELS["chief_complaint_patient"],
            key=widget_key("chief_complaint_patient"),
        )
        chief_complaint_relatives = st.text_area(
            FIELD_LABELS["chief_complaint_relatives"],
            key=widget_key("chief_complaint_relatives"),
        )
        complaint_left, complaint_right = st.columns(2)
        with complaint_left:
            complaint_duration = st.text_input(
                FIELD_LABELS["complaint_duration"],
                key=widget_key("complaint_duration"),
            )
            complaint_onset = st.text_input(
                FIELD_LABELS["complaint_onset"],
                key=widget_key("complaint_onset"),
            )
        with complaint_right:
            complaint_recent = st.text_input(
                FIELD_LABELS["complaint_recent"],
                key=widget_key("complaint_recent"),
            )
            complaint_previous_hospitalization = st.text_input(
                FIELD_LABELS["complaint_previous_hospitalization"],
                key=widget_key("complaint_previous_hospitalization"),
            )

    with st.container(border=True, key="encode-intake-section-impression"):
        st.markdown(f"#### {SECTION_TITLES['impression']}")
        interviewers_initial_impression = st.text_area(
            FIELD_LABELS["interviewers_initial_impression"],
            key=widget_key("interviewers_initial_impression"),
            label_visibility="collapsed",
        )

    with st.container(
        border=True,
        key="encode-intake-section-history-of-illness",
    ):
        st.markdown(f"#### {SECTION_TITLES['history_of_illness']}")
        history_of_illness = st.text_area(
            FIELD_LABELS["history_of_illness"],
            key=widget_key("history_of_illness"),
            label_visibility="collapsed",
        )

    with st.container(
        border=True,
        key="encode-intake-section-mental-status",
    ):
        st.markdown(f"#### {SECTION_TITLES['mental_status_examination']}")
        mse = st.text_area(
            FIELD_LABELS["mental_status_examination"],
            key=widget_key("mental_status_examination"),
            label_visibility="collapsed",
        )

    with st.container(
        border=True,
        key="encode-intake-section-nurses-observation",
    ):
        st.markdown(f"#### {SECTION_TITLES['nurses_observation']}")
        nurses_observation = st.text_area(
            FIELD_LABELS["nurses_observation"],
            key=widget_key("nurses_observation"),
            label_visibility="collapsed",
        )

    with st.container(border=True, key="encode-intake-section-diagnosis"):
        st.markdown(f"#### {SECTION_TITLES['diagnosis']}")
        diagnosis = st.text_area(
            FIELD_LABELS["diagnosis"],
            key=widget_key("diagnosis"),
            label_visibility="collapsed",
        )

    with st.container(border=True, key="encode-intake-section-treatment"):
        st.markdown(f"#### {SECTION_TITLES['treatment']}")
        treatment = st.text_area(
            FIELD_LABELS["treatment"],
            key=widget_key("treatment"),
            label_visibility="collapsed",
        )

    with st.container(border=True, key="encode-intake-section-medications"):
        st.markdown(f"#### {SECTION_TITLES['medications']}")
        edited_med_df = st.data_editor(
            st.session_state.med_table,
            num_rows="dynamic",
            width="stretch",
            key=widget_key("med_table"),
            column_config={
                column: (
                    st.column_config.DateColumn(
                        MEDICATION_COLUMN_LABELS[column],
                        format=DATE_DISPLAY_FORMAT,
                    )
                    if column in MEDICATION_COLUMNS[::2]
                    else st.column_config.TextColumn(
                        MEDICATION_COLUMN_LABELS[column]
                    )
                )
                for column in MEDICATION_COLUMNS
            },
            alt="Patient parenteral medication log",
        )

    st.divider()
    record_added_pending = st.session_state.get("record_added_pending", False)
    submit_button = st.button(
        "Save Record",
        type="primary",
        disabled=record_added_pending,
        key=widget_key("save_record"),
    )

    save_succeeded = False
    if submit_button:
        if not _is_four_digit_value(patient_year) or not _is_four_digit_value(
            patient_sequence
        ):
            st.error(
                "⚠️ Validation Error: Year and unique number must each contain "
                "exactly four digits."
            )
        elif not last_name or not first_name:
            st.error("⚠️ Validation Error: Last Name and First Name fields must be filled.")
        else:
            try:
                # Convert active UI tabular frames to strings safely
                family_text_summary = dataframe_to_storage(edited_family_df)
                med_text_summary = dataframe_to_storage(edited_med_df)

                raw_payload = {
                    "patient_case_number": patient_case_number,
                    "referral_noted_by": referral_noted_by,
                    "referring_person_or_instance": referring_person_or_instance,
                    "date_of_referral": (
                        date_of_referral.isoformat() if date_of_referral else None
                    ),
                    "means_of_referral": means_of_referral,
                    "referral_request": referral_request,
                    "agreements_made_for_further_interviewing": (
                        agreements_made_for_further_interviewing
                    ),
                    "interview_date": (
                        interview_date.isoformat() if interview_date else None
                    ),
                    "interview_place": interview_place,
                    "interview_persons_present": interview_persons_present,
                    "primary_source_of_information": primary_source_info,
                    "last_name": last_name, "first_name": first_name, "middle_name": middle_name, "extension_name": ext_name,
                    "calculated_age": calculated_age if calculated_age is not None else 0,
                    "street_address": street_address,
                    "purok": purok, "barangay": barangay,
                    "city_municipality": city_municipality, "province": province,
                    "date_of_birth": dob.isoformat() if dob else None,
                    "sex": sex, "civil_status": civil_status, "religion": religion, "educational_attainment": educational,
                    "status": status, "work_experience": work_experience, "guardian_last_name": g_last_name,
                    "guardian_first_name": g_first_name, "guardian_middle_name": g_middle_name, "guardian_street_address": g_street,
                    "g_barangay": g_barangay, "g_city": g_city, "g_province": g_province,
                    "guardian_contact_person": g_contact_person, "g_contact_number": g_contact_number,
                    "family_composition": family_text_summary,
                    "household_member_count": household_member_count,
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

                try:
                    new_patient_id = patient_case_number
                    _save_patient_record(
                        cleaned_payload,
                        first_name,
                        last_name,
                    )
                except ValueError as e:
                    st.error(f"⚠️ Validation Error: {str(e)}")
                else:
                    st.session_state.pop("show_encode_dialog", None)
                    st.session_state["encode_success_toast"] = (
                        f"Patient record {new_patient_id} saved."
                    )
                    _reset_encode_form(scroll_to_top=False)
                    save_succeeded = True
            except Exception as e:
                st.error(f"❌ Storage Execution Error: {str(e)}")

    if save_succeeded:
        st.rerun()

    if st.session_state.get("record_added_pending"):
        case_number = st.session_state.pop("record_added_case_number", None)
        if case_number is not None:
            st.success(
                f"Patient ID {case_number} was saved and verified in the local archive."
            )
        st.button(
            "✅ Record added — click here to clear the form",
            on_click=_reset_encode_form,
            type="primary",
        )


def _dismiss_encode_dialog():
    st.session_state.pop("show_encode_dialog", None)
    if st.session_state.get("record_added_pending"):
        _reset_encode_form()


@st.dialog(
    "Encode Patient Information",
    width="large",
    on_dismiss=_dismiss_encode_dialog,
)
def show_encode_dialog():
    with st.container(key="encode-modal-content"):
        show_encode_page()


if __name__ == "__main__":
    show_encode_page()
