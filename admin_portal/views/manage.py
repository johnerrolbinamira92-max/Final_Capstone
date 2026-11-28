import datetime
import html
import json
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st
from database import get_local_connection, get_registered_admin_names
from views.encode import (
    CONTACT_NUMBER_INPUT_VALIDATION,
    _calculate_age,
    _is_valid_contact_number,
    _is_valid_nonnegative_number,
    _load_bicol_address_hierarchy,
    _open_encode_dialog,
    _render_address_dropdowns,
    _render_birth_date,
    show_encode_dialog,
)
from views.record_tables import (
    DATE_DISPLAY_FORMAT,
    FAMILY_COLUMNS,
    MEDICATION_COLUMN_LABELS,
    MEDICATION_COLUMNS,
    PERSON_NAME_INPUT_VALIDATION,
    dataframe_from_storage,
    dataframe_to_storage,
    family_column_config,
    is_valid_person_name,
    format_date_for_display,
    parse_stored_date,
    validate_person_names,
    validate_family_composition,
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

BICOL_ADDRESS_FILE = (
    Path(__file__).resolve().parents[1] / "data" / "bicol_address_hierarchy.json"
)


@st.cache_data
def _load_bicol_address_hierarchy():
    with BICOL_ADDRESS_FILE.open(encoding="utf-8") as address_file:
        provinces = json.load(address_file)["provinces"]
    return {province["name"]: province for province in provinces}


def _clear_record_barangay():
    st.session_state.pop("record_filter_barangay", None)


def _clear_record_city_and_barangay():
    st.session_state.pop("record_filter_city", None)
    st.session_state.pop("record_filter_barangay", None)


def _location_key(value):
    normalized = " ".join(str(value or "").strip().casefold().split())
    if normalized.startswith("city of "):
        normalized = normalized[len("city of ") :]
    for suffix in (" city", " province"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
    return normalized


def _is_four_digit_value(value):
    return (
        len(value) == 4
        and value.isascii()
        and value.isdigit()
        and int(value) > 0
    )


def _matches_patient_case_number(record, case_number):
    stored_case_number = str(record.get("patient_case_number") or "")
    return stored_case_number.casefold() == case_number.casefold()


def _detail_label(field_name):
    return field_name.replace("_", " ").strip().title()


def _admin_name_options(current_value=None):
    options = get_registered_admin_names()
    if current_value and current_value not in options:
        options.append(current_value)
    return options


def _information_noted_by_options(current_value=None):
    options = list(INFORMATION_NOTED_BY_OPTIONS)
    if current_value and current_value not in options:
        options.append(current_value)
    return options


def _render_patient_detail_label(label):
    st.markdown(
        f'<div class="patient-field-label">{html.escape(label)}</div>',
        unsafe_allow_html=True,
    )


def _render_patient_detail_value(value):
    if value is None or value == "":
        st.markdown(
            '<span class="patient-empty-value">—</span>',
            unsafe_allow_html=True,
        )
        return
    st.markdown(
        f'<div class="patient-field-value">{html.escape(str(value))}</div>',
        unsafe_allow_html=True,
    )


def _render_patient_detail_fields(fields):
    value_columns = st.columns(2)
    for index, (label, value) in enumerate(fields):
        with value_columns[index % 2]:
            _render_patient_detail_label(label)
            _render_patient_detail_value(value)


VIEW_SECTION_COLUMNS = {
    "administration": {"status"},
    "referral": {
        "referral_noted_by",
        "referring_person_or_instance",
        "date_of_referral",
        "means_of_referral",
        "referral_request",
        "agreements_made_for_further_interviewing",
    },
    "interview": {
        "interview_date",
        "interview_place",
        "interview_persons_present",
        "primary_source_of_information",
    },
    "identifying": {
        "first_name",
        "middle_name",
        "last_name",
        "extension_name",
        "calculated_age",
        "street_address",
        "purok",
        "barangay",
        "city_municipality",
        "province",
        "date_of_birth",
        "sex",
        "civil_status",
        "religion",
        "educational_attainment",
        "work_experience",
    },
    "relatives": {
        "guardian_first_name",
        "guardian_middle_name",
        "guardian_last_name",
        "guardian_street_address",
        "g_barangay",
        "g_city",
        "g_province",
        "guardian_contact_person",
        "g_contact_number",
    },
    "family": {"family_composition"},
    "classification": {
        "household_member_count",
        "total_annual_income",
        "poverty_threshold_per_year",
        "poverty_rating",
        "classification_after_interview",
        "classification_after_home_visit",
    },
    "complaint": {
        "chief_complaint_patient",
        "chief_complaint_relatives",
        "complaint_duration",
        "complaint_onset",
        "complaint_recent",
        "complaint_previous_hospitalization",
    },
    "impression": {"interviewers_initial_impression"},
    "history_of_illness": {"history_of_illness"},
    "mental_status_examination": {"mental_status_examination"},
    "nurses_observation": {"nurses_observation"},
    "diagnosis": {"diagnosis"},
    "treatment": {"treatment"},
    "medications": {"parenteral_medication_records"},
}

VIEW_SECTION_TITLES = {
    "administration": SECTION_TITLES["administration"],
    "referral": SECTION_TITLES["referral"],
    "interview": "Interview Logistics",
    "identifying": "Patient Profile",
    "relatives": SECTION_TITLES["relatives"],
    "family": SECTION_TITLES["family"],
    "classification": SECTION_TITLES["classification"],
    "complaint": SECTION_TITLES["complaint"],
    "impression": SECTION_TITLES["impression"],
    "history_of_illness": SECTION_TITLES["history_of_illness"],
    "mental_status_examination": SECTION_TITLES[
        "mental_status_examination"
    ],
    "nurses_observation": SECTION_TITLES["nurses_observation"],
    "diagnosis": SECTION_TITLES["diagnosis"],
    "treatment": SECTION_TITLES["treatment"],
    "medications": SECTION_TITLES["medications"],
}


def _view_edit_widget_prefix(patient_id, section_key):
    return f"view-record-edit:{patient_id}:{section_key}:"


def _clear_view_edit_widgets(prefix):
    for key in list(st.session_state.keys()):
        if key.startswith(prefix):
            st.session_state.pop(key, None)


def _apply_pending_view_edit_cleanup():
    prefix = st.session_state.pop("view_edit_cleanup_prefix", None)
    if prefix:
        _clear_view_edit_widgets(prefix)


def _save_view_record_section(patient_id, patient, section_key, updates):
    allowed_columns = VIEW_SECTION_COLUMNS.get(section_key)
    if not allowed_columns or not updates or not set(updates) <= allowed_columns:
        raise ValueError("The section contains unsupported patient fields.")

    column_names = list(updates)
    assignments = ", ".join(f"{column} = ?" for column in column_names)
    values = [updates[column] for column in column_names]
    section_title = VIEW_SECTION_TITLES[section_key]
    patient_name = _patient_full_name(patient) or "Unnamed patient"
    case_number = patient.get("patient_case_number") or "not assigned"

    conn = get_local_connection()
    try:
        with conn:
            result = conn.execute(
                f"UPDATE patients SET {assignments} WHERE patient_id = ?",
                (*values, patient_id),
            )
            if result.rowcount != 1:
                raise RuntimeError(
                    "The patient record was not updated; it may have been removed."
                )
            conn.execute(
                "INSERT INTO admin_logs (action_type, details) VALUES (?, ?)",
                (
                    "PATIENT RECORD EDITED",
                    f"Edited the {section_title} section for {patient_name} "
                    f"(case {case_number}, record {patient_id}).",
                ),
            )
    finally:
        conn.close()


def _render_editable_patient_section(
    patient_id,
    patient,
    section_key,
    title,
    display_renderer,
    edit_renderer,
):
    active_section = st.session_state.get("view_editing_section")
    is_editing = (
        active_section == section_key
        and st.session_state.get("view_editing_patient_id") == patient_id
    )
    with st.container(
        border=True,
        key=f"view-intake-section-{section_key}",
    ):
        with st.container(
            horizontal=True,
            wrap=False,
            vertical_alignment="center",
            key=f"view-intake-section-header-{section_key}",
        ):
            st.markdown(
                f'<div class="view-record-section-title">'
                f"{html.escape(title)}</div>",
                unsafe_allow_html=True,
            )
            if st.button(
                "Edit",
                key=f"view-record-edit-open-{patient_id}-{section_key}",
                icon=":material/edit:",
                type="tertiary",
                width="content",
                disabled=is_editing,
                help=f"Edit {title}",
            ):
                if active_section:
                    old_patient_id = st.session_state.get(
                        "view_editing_patient_id",
                        patient_id,
                    )
                    st.session_state["view_edit_cleanup_prefix"] = (
                        _view_edit_widget_prefix(
                            old_patient_id,
                            active_section,
                        )
                    )
                st.session_state["view_editing_section"] = section_key
                st.session_state["view_editing_patient_id"] = patient_id
                st.rerun()

        if is_editing:
            updates = edit_renderer()
            with st.container(
                horizontal=True,
                horizontal_alignment="right",
                gap="small",
                key=f"view-intake-section-actions-{section_key}",
            ):
                cancel_clicked = st.button(
                    "Cancel",
                    key=f"view-record-edit-cancel-{patient_id}-{section_key}",
                    type="tertiary",
                    width="content",
                )
                save_clicked = st.button(
                    "Save",
                    key=f"view-record-edit-save-{patient_id}-{section_key}",
                    type="primary",
                    width="content",
                )

            if cancel_clicked:
                st.session_state["view_edit_cleanup_prefix"] = (
                    _view_edit_widget_prefix(patient_id, section_key)
                )
                st.session_state["view_editing_section"] = None
                st.session_state.pop("view_editing_patient_id", None)
                st.rerun()
            if save_clicked:
                if section_key == "identifying" and (
                    not str(updates.get("first_name") or "").strip()
                    or not str(updates.get("last_name") or "").strip()
                ):
                    st.error("First name and last name are required.")
                    return
                validation_errors = _view_section_validation_errors(
                    section_key,
                    updates,
                )
                if validation_errors:
                    for validation_error in validation_errors:
                        st.error(validation_error)
                    return
                try:
                    _save_view_record_section(
                        patient_id,
                        patient,
                        section_key,
                        updates,
                    )
                except Exception as error:
                    st.error(f"Unable to save {title}: {error}")
                else:
                    st.session_state["view_edit_cleanup_prefix"] = (
                        _view_edit_widget_prefix(patient_id, section_key)
                    )
                    st.session_state["view_editing_section"] = None
                    st.session_state.pop("view_editing_patient_id", None)
                    st.session_state["manage_success_message"] = (
                        f"{title} updated successfully."
                    )
                    st.rerun()
        else:
            display_renderer()


def _render_patient_detail_section(
    patient_id,
    patient,
    section_key,
    title,
    fields,
    edit_renderer,
):
    _render_editable_patient_section(
        patient_id,
        patient,
        section_key,
        title,
        lambda: _render_patient_detail_fields(fields),
        edit_renderer,
    )


def _render_patient_note_section(
    patient_id,
    patient,
    section_key,
    title,
    value,
    edit_renderer,
):
    _render_editable_patient_section(
        patient_id,
        patient,
        section_key,
        title,
        lambda: _render_patient_detail_value(value),
        edit_renderer,
    )


def _view_edit_key(patient_id, section_key, field):
    return f"{_view_edit_widget_prefix(patient_id, section_key)}{field}"


def _view_text_input(patient_id, patient, section_key, field, label):
    return st.text_input(
        label,
        value=str(patient.get(field) or ""),
        key=_view_edit_key(patient_id, section_key, field),
    )


def _view_name_input(patient_id, patient, section_key, field, label):
    return st.text_input(
        label,
        value=str(patient.get(field) or ""),
        validate=PERSON_NAME_INPUT_VALIDATION,
        key=_view_edit_key(patient_id, section_key, field),
    )


def _view_contact_input(patient_id, patient, section_key, field, label):
    return st.text_input(
        label,
        value=str(patient.get(field) or ""),
        max_chars=11,
        type="phone",
        placeholder="09XXXXXXXXX",
        validate=CONTACT_NUMBER_INPUT_VALIDATION,
        help="If provided, enter 11 digits starting with 09.",
        key=_view_edit_key(patient_id, section_key, field),
    )


def _view_text_area(patient_id, patient, section_key, field, label):
    return st.text_area(
        label,
        value=str(patient.get(field) or ""),
        key=_view_edit_key(patient_id, section_key, field),
    )


def _view_date_input(patient_id, patient, section_key, field, label):
    raw_value = patient.get(field)
    parsed_value = parse_stored_date(raw_value)
    today = datetime.date.today()
    valid_date = (
        isinstance(parsed_value, datetime.date)
        and MIN_BIRTH_DATE <= parsed_value <= today
    )
    if parsed_value is not None and not valid_date and isinstance(
        parsed_value, (datetime.date, str)
    ):
        st.caption(
            f"{label} is stored in an unrecognized or out-of-range format. "
            "Choose a valid date to replace it; leaving it blank preserves it."
        )
    selected_date = st.date_input(
        label,
        value=parsed_value if valid_date else None,
        min_value=MIN_BIRTH_DATE,
        max_value=today,
        format=DATE_DISPLAY_FORMAT,
        key=_view_edit_key(patient_id, section_key, field),
    )
    if selected_date is not None:
        return selected_date.isoformat()
    if parsed_value is not None and not valid_date:
        return raw_value
    return None


def _view_numeric_value(value, *, integer=False):
    try:
        return int(float(value or 0)) if integer else float(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0 if integer else 0.0


def _view_section_validation_errors(section_key, updates):
    errors = []
    if section_key == "referral":
        errors.extend(
            validate_person_names(
                {"Worker Name": updates.get("referral_noted_by")}
            )
        )
    elif section_key == "interview":
        errors.extend(
            validate_person_names(
                {"Informant Name": updates.get("primary_source_of_information")}
            )
        )
    elif section_key == "identifying":
        errors.extend(
            validate_person_names(
                {
                    "First Name": updates.get("first_name"),
                    "Middle Name": updates.get("middle_name"),
                    "Last Name": updates.get("last_name"),
                    "Extension Name": updates.get("extension_name"),
                }
            )
        )
        if not _is_valid_nonnegative_number(
            updates.get("calculated_age"),
            integer=True,
            max_value=120,
        ):
            errors.append("Age must be a whole number from 0 to 120.")
    elif section_key == "relatives":
        contact_number = updates.get("g_contact_number")
        if contact_number and not _is_valid_contact_number(contact_number):
            errors.append(
                "Contact Number must contain 11 digits starting with 09."
            )
        errors.extend(
            validate_person_names(
                {
                    "Guardian Name": updates.get("guardian_first_name"),
                    "Guardian Middle Name": updates.get("guardian_middle_name"),
                    "Guardian Last Name": updates.get("guardian_last_name"),
                    "Contact Person": updates.get("guardian_contact_person"),
                }
            )
        )
    elif section_key == "family":
        family_table = dataframe_from_storage(
            updates.get("family_composition"),
            FAMILY_COLUMNS,
        )
        errors.extend(validate_family_composition(family_table))
    elif section_key == "classification":
        if not _is_valid_nonnegative_number(
            updates.get("household_member_count"),
            integer=True,
        ):
            errors.append(
                "No. of Household Members must be a non-negative whole number."
            )
        if not _is_valid_nonnegative_number(
            updates.get("total_annual_income")
        ):
            errors.append(
                "Total annual income must be a valid non-negative amount."
            )
        if not _is_valid_nonnegative_number(
            updates.get("poverty_threshold_per_year")
        ):
            errors.append(
                "Poverty threshold/year must be a valid non-negative amount."
            )
    return errors


def _render_view_section_editor(patient_id, patient, section_key):
    if section_key == "administration":
        current_status = patient.get("status") or ""
        status_options = list(ADMINISTRATIVE_STATUS_OPTIONS)
        if current_status and current_status not in status_options:
            status_options.append(current_status)
        return {
            "status": st.selectbox(
                FIELD_LABELS["status"],
                status_options,
                index=(
                    status_options.index(current_status)
                    if current_status
                    else None
                ),
                key=_view_edit_key(
                    patient_id,
                    section_key,
                    "status",
                ),
            )
        }

    if section_key == "referral":
        noted_by = patient.get("referral_noted_by") or ""
        noted_by_options = _information_noted_by_options(noted_by)
        referral_left, referral_right = st.columns(2)
        with referral_left:
            referral_noted_by = st.selectbox(
                FIELD_LABELS["referral_noted_by"],
                noted_by_options,
                index=(
                    noted_by_options.index(noted_by)
                    if noted_by
                    else None
                ),
                accept_new_options=True,
                key=_view_edit_key(
                    patient_id,
                    section_key,
                    "referral_noted_by",
                ),
            )
            referring_person = _view_text_input(
                patient_id,
                patient,
                section_key,
                "referring_person_or_instance",
                FIELD_LABELS["referring_person_or_instance"],
            )
            date_of_referral = _view_date_input(
                patient_id,
                patient,
                section_key,
                "date_of_referral",
                FIELD_LABELS["date_of_referral"],
            )
        with referral_right:
            means_of_referral = _view_text_input(
                patient_id,
                patient,
                section_key,
                "means_of_referral",
                FIELD_LABELS["means_of_referral"],
            )
            referral_request = _view_text_area(
                patient_id,
                patient,
                section_key,
                "referral_request",
                FIELD_LABELS["referral_request"],
            )
        agreements = _view_text_area(
            patient_id,
            patient,
            section_key,
            "agreements_made_for_further_interviewing",
            FIELD_LABELS["agreements_made_for_further_interviewing"],
        )
        return {
            "referral_noted_by": referral_noted_by or "",
            "referring_person_or_instance": referring_person,
            "date_of_referral": date_of_referral,
            "means_of_referral": means_of_referral,
            "referral_request": referral_request,
            "agreements_made_for_further_interviewing": agreements,
        }

    if section_key == "interview":
        left_column, right_column = st.columns(2)
        with left_column:
            interview_date = _view_date_input(
                patient_id,
                patient,
                section_key,
                "interview_date",
                FIELD_LABELS["interview_date"],
            )
            interview_place = _view_text_input(
                patient_id,
                patient,
                section_key,
                "interview_place",
                FIELD_LABELS["interview_place"],
            )
        with right_column:
            persons_present = _view_text_area(
                patient_id,
                patient,
                section_key,
                "interview_persons_present",
                FIELD_LABELS["interview_persons_present"],
            )
            primary_source = _view_name_input(
                patient_id,
                patient,
                section_key,
                "primary_source_of_information",
                FIELD_LABELS["primary_source_of_information"],
            )
        return {
            "interview_date": interview_date,
            "interview_place": interview_place,
            "interview_persons_present": persons_present,
            "primary_source_of_information": primary_source,
        }

    if section_key == "identifying":
        st.markdown(f"##### {FIELD_LABELS['client_name']}")
        name_columns = st.columns(4)
        with name_columns[0]:
            first_name = _view_name_input(
                patient_id, patient, section_key, "first_name", "First Name"
            )
        with name_columns[1]:
            middle_name = _view_name_input(
                patient_id, patient, section_key, "middle_name", "Middle Name"
            )
        with name_columns[2]:
            last_name = _view_name_input(
                patient_id, patient, section_key, "last_name", "Last Name"
            )
        with name_columns[3]:
            extension_name = _view_name_input(
                patient_id,
                patient,
                section_key,
                "extension_name",
                "Extension Name",
            )

        date_of_birth = _view_date_input(
            patient_id,
            patient,
            section_key,
            "date_of_birth",
            FIELD_LABELS["date_of_birth"],
        )
        parsed_birth_date = parse_stored_date(date_of_birth)
        calculated_age = (
            _calculate_age(parsed_birth_date)
            if isinstance(parsed_birth_date, datetime.date)
            else (
                patient.get("calculated_age")
                if date_of_birth
                else 0
            )
        )
        age_is_valid = _is_valid_nonnegative_number(
            calculated_age,
            integer=True,
            max_value=120,
        )
        age_key = _view_edit_key(
            patient_id,
            section_key,
            "calculated_age_numeric",
        )
        st.session_state[age_key] = (
            int(float(calculated_age))
            if age_is_valid and calculated_age is not None
            else None
        )
        st.number_input(
            FIELD_LABELS["age"],
            min_value=0,
            max_value=120,
            step=1,
            disabled=True,
            key=age_key,
        )
        if not age_is_valid:
            st.error("Age must be a whole number from 0 to 120.")

        st.markdown(f"**{FIELD_LABELS['address']}**")
        patient_address = _render_address_dropdowns(
            "patient_address",
            lambda field: _view_edit_key(patient_id, section_key, field),
            _load_bicol_address_hierarchy(),
            initial_values={
                "province": patient.get("province"),
                "city_municipality": patient.get("city_municipality"),
                "barangay": patient.get("barangay"),
            },
        )
        address_columns = st.columns(2)
        with address_columns[0]:
            street_address = _view_text_input(
                patient_id,
                patient,
                section_key,
                "street_address",
                "Street / House Number",
            )
        with address_columns[1]:
            purok = _view_text_input(
                patient_id,
                patient,
                section_key,
                "purok",
                "Purok",
            )
        sex_value = str(patient.get("sex") or "").strip()
        sex_key = _view_edit_key(patient_id, section_key, "sex")
        sex_options = list(SEX_OPTIONS)
        if sex_value and sex_key not in st.session_state:
            st.session_state[sex_key] = sex_value

        civil_status_value = str(patient.get("civil_status") or "").strip()
        civil_status_key = _view_edit_key(
            patient_id,
            section_key,
            "civil_status",
        )
        civil_status_options = list(CIVIL_STATUS_OPTIONS)
        if (
            civil_status_value
            and civil_status_value not in civil_status_options
            and civil_status_key not in st.session_state
        ):
            st.session_state[civil_status_key] = civil_status_value

        education_value = str(
            patient.get("educational_attainment") or ""
        ).strip()
        education_key = _view_edit_key(
            patient_id,
            section_key,
            "educational_attainment",
        )
        education_options = list(EDUCATIONAL_ATTAINMENT_OPTIONS)
        if (
            education_value
            and education_value not in education_options
            and education_key not in st.session_state
        ):
            st.session_state[education_key] = education_value

        demographic_left, demographic_right = st.columns(2)
        with demographic_left:
            sex = st.selectbox(
                FIELD_LABELS["sex"],
                sex_options,
                index=(
                    sex_options.index(sex_value)
                    if sex_value in sex_options
                    else None
                ),
                accept_new_options=True,
                key=sex_key,
            )
            civil_status = st.selectbox(
                FIELD_LABELS["civil_status"],
                civil_status_options,
                index=(
                    civil_status_options.index(civil_status_value)
                    if civil_status_value in civil_status_options
                    else None
                ),
                accept_new_options=True,
                key=civil_status_key,
            )
        with demographic_right:
            religion = _view_text_input(
                patient_id,
                patient,
                section_key,
                "religion",
                FIELD_LABELS["religion"],
            )
            education = st.selectbox(
                FIELD_LABELS["educational_attainment"],
                education_options,
                index=(
                    education_options.index(education_value)
                    if education_value in education_options
                    else None
                ),
                accept_new_options=True,
                key=education_key,
            )

        work_experience = _view_text_area(
            patient_id,
            patient,
            section_key,
            "work_experience",
            FIELD_LABELS["work_experience"],
        )
        return {
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,
            "extension_name": extension_name,
            "calculated_age": calculated_age if calculated_age is not None else 0,
            "street_address": street_address,
            "purok": purok,
            "barangay": patient_address["barangay"],
            "city_municipality": patient_address["city_municipality"],
            "province": patient_address["province"],
            "date_of_birth": date_of_birth,
            "sex": sex or "",
            "civil_status": civil_status or "",
            "religion": religion,
            "educational_attainment": education or "",
            "work_experience": work_experience,
        }

    if section_key == "relatives":
        initial_guardian_name = _patient_full_name(
            {
                "first_name": patient.get("guardian_first_name"),
                "middle_name": patient.get("guardian_middle_name"),
                "last_name": patient.get("guardian_last_name"),
            }
        )
        guardian_name = st.text_input(
            "Name",
            value=initial_guardian_name,
            validate=PERSON_NAME_INPUT_VALIDATION,
            key=_view_edit_key(
                patient_id,
                section_key,
                "guardian_name",
            ),
        )
        st.markdown(f"**{FIELD_LABELS['address']}**")
        guardian_address = _render_address_dropdowns(
            "guardian_address",
            lambda field: _view_edit_key(patient_id, section_key, field),
            _load_bicol_address_hierarchy(),
            initial_values={
                "province": patient.get("g_province"),
                "city_municipality": patient.get("g_city"),
                "barangay": patient.get("g_barangay"),
            },
        )
        address_columns = st.columns(2)
        with address_columns[0]:
            guardian_street = st.text_input(
                "Street / Zone",
                value=str(patient.get("guardian_street_address") or ""),
                disabled=not guardian_address["province"],
                key=_view_edit_key(
                    patient_id,
                    section_key,
                    "guardian_street_address",
                ),
            )
        with address_columns[1]:
            contact_person = st.text_input(
                FIELD_LABELS["contact_person"],
                value=str(patient.get("guardian_contact_person") or ""),
                placeholder=(
                    "Same as Nearest Relative (or enter alternate contact)"
                ),
                validate=PERSON_NAME_INPUT_VALIDATION,
                key=_view_edit_key(
                    patient_id,
                    section_key,
                    "guardian_contact_person",
                ),
            )
        contact_number = _view_contact_input(
            patient_id,
            patient,
            section_key,
            "g_contact_number",
            FIELD_LABELS["contact_number"],
        )
        if guardian_name == initial_guardian_name:
            guardian_name_updates = {
                "guardian_first_name": patient.get("guardian_first_name") or "",
                "guardian_middle_name": patient.get("guardian_middle_name") or "",
                "guardian_last_name": patient.get("guardian_last_name") or "",
            }
        else:
            guardian_name_updates = {
                "guardian_first_name": guardian_name,
                "guardian_middle_name": "",
                "guardian_last_name": "",
            }
        return {
            **guardian_name_updates,
            "guardian_street_address": guardian_street,
            "g_barangay": guardian_address["barangay"],
            "g_city": guardian_address["city_municipality"],
            "g_province": guardian_address["province"],
            "guardian_contact_person": contact_person,
            "g_contact_number": contact_number,
        }

    if section_key == "family":
        family_table = dataframe_from_storage(
            patient.get("family_composition"),
            FAMILY_COLUMNS,
        )
        edited_family_table = st.data_editor(
            family_table,
            num_rows="dynamic",
            width="stretch",
            key=_view_edit_key(patient_id, section_key, "family_table"),
            column_config=family_column_config(family_table),
            alt="Family composition of the patient",
        )
        return {
            "family_composition": dataframe_to_storage(edited_family_table)
        }

    if section_key == "classification":
        classification_left, classification_right = st.columns(2)
        with classification_left:
            household_count = st.number_input(
                FIELD_LABELS["household_member_count"],
                min_value=0,
                step=1,
                value=_view_numeric_value(
                    patient.get("household_member_count"),
                    integer=True,
                ),
                key=_view_edit_key(
                    patient_id,
                    section_key,
                    "household_member_count",
                ),
            )
            annual_income = st.number_input(
                FIELD_LABELS["total_annual_income"],
                min_value=0.0,
                step=500.0,
                format="%.2f",
                value=_view_numeric_value(
                    patient.get("total_annual_income")
                ),
                key=_view_edit_key(
                    patient_id,
                    section_key,
                    "total_annual_income",
                ),
            )
            poverty_threshold = st.number_input(
                FIELD_LABELS["poverty_threshold_per_year"],
                min_value=0.0,
                step=500.0,
                format="%.2f",
                value=_view_numeric_value(
                    patient.get("poverty_threshold_per_year")
                ),
                key=_view_edit_key(
                    patient_id,
                    section_key,
                    "poverty_threshold_per_year",
                ),
            )
        with classification_right:
            poverty_rating = _view_text_input(
                patient_id,
                patient,
                section_key,
                "poverty_rating",
                FIELD_LABELS["poverty_rating"],
            )
            after_interview = _view_text_input(
                patient_id,
                patient,
                section_key,
                "classification_after_interview",
                FIELD_LABELS["classification_after_interview"],
            )
            after_home_visit = _view_text_input(
                patient_id,
                patient,
                section_key,
                "classification_after_home_visit",
                FIELD_LABELS["classification_after_home_visit"],
            )
        return {
            "household_member_count": household_count,
            "total_annual_income": annual_income,
            "poverty_threshold_per_year": poverty_threshold,
            "poverty_rating": poverty_rating,
            "classification_after_interview": after_interview,
            "classification_after_home_visit": after_home_visit,
        }

    if section_key == "complaint":
        complaint_patient = _view_text_area(
            patient_id,
            patient,
            section_key,
            "chief_complaint_patient",
            FIELD_LABELS["chief_complaint_patient"],
        )
        complaint_relatives = _view_text_area(
            patient_id,
            patient,
            section_key,
            "chief_complaint_relatives",
            FIELD_LABELS["chief_complaint_relatives"],
        )
        complaint_left, complaint_right = st.columns(2)
        with complaint_left:
            duration = _view_text_input(
                patient_id,
                patient,
                section_key,
                "complaint_duration",
                FIELD_LABELS["complaint_duration"],
            )
            onset = _view_text_input(
                patient_id,
                patient,
                section_key,
                "complaint_onset",
                FIELD_LABELS["complaint_onset"],
            )
        with complaint_right:
            recent = _view_text_input(
                patient_id,
                patient,
                section_key,
                "complaint_recent",
                FIELD_LABELS["complaint_recent"],
            )
            previous_hospitalization = _view_text_input(
                patient_id,
                patient,
                section_key,
                "complaint_previous_hospitalization",
                FIELD_LABELS["complaint_previous_hospitalization"],
            )
        return {
            "chief_complaint_patient": complaint_patient,
            "chief_complaint_relatives": complaint_relatives,
            "complaint_duration": duration,
            "complaint_onset": onset,
            "complaint_recent": recent,
            "complaint_previous_hospitalization": previous_hospitalization,
        }

    note_fields = {
        "impression": (
            "interviewers_initial_impression",
            FIELD_LABELS["interviewers_initial_impression"],
        ),
        "history_of_illness": (
            "history_of_illness",
            FIELD_LABELS["history_of_illness"],
        ),
        "mental_status_examination": (
            "mental_status_examination",
            FIELD_LABELS["mental_status_examination"],
        ),
        "nurses_observation": (
            "nurses_observation",
            FIELD_LABELS["nurses_observation"],
        ),
        "diagnosis": ("diagnosis", FIELD_LABELS["diagnosis"]),
        "treatment": ("treatment", FIELD_LABELS["treatment"]),
    }
    if section_key in note_fields:
        field, label = note_fields[section_key]
        return {
            field: _view_text_area(
                patient_id,
                patient,
                section_key,
                field,
                label,
            )
        }

    if section_key == "medications":
        medication_table = dataframe_from_storage(
            patient.get("parenteral_medication_records"),
            MEDICATION_COLUMNS,
        )
        edited_medication_table = st.data_editor(
            medication_table,
            num_rows="dynamic",
            width="stretch",
            key=_view_edit_key(patient_id, section_key, "medication_table"),
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
            alt="Parenteral medication sheet",
        )
        return {
            "parenteral_medication_records": dataframe_to_storage(
                edited_medication_table
            )
        }

    raise ValueError(f"No editor is defined for the {section_key} section.")


def _format_address(patient, prefix=""):
    fields = (
        (
            "guardian_street_address",
            "g_barangay",
            "g_city",
            "g_province",
        )
        if prefix
        else ("street_address", "purok", "barangay", "city_municipality", "province")
    )
    return ", ".join(
        str(patient.get(field)).strip()
        for field in fields
        if field and patient.get(field) and str(patient[field]).strip()
    )


def _render_patient_details(patient):
    patient_id = patient["patient_id"]
    st.session_state.setdefault("view_editing_section", None)
    _apply_pending_view_edit_cleanup()
    active_section = st.session_state.get("view_editing_section")
    active_patient_id = st.session_state.get("view_editing_patient_id")
    if active_section and active_patient_id != patient_id:
        _clear_view_edit_widgets(
            _view_edit_widget_prefix(active_patient_id, active_section)
        )
        st.session_state["view_editing_section"] = None
        st.session_state.pop("view_editing_patient_id", None)

    def render_fields(section_key, title, fields):
        _render_patient_detail_section(
            patient_id,
            patient,
            section_key,
            title,
            fields,
            lambda: _render_view_section_editor(
                patient_id,
                patient,
                section_key,
            ),
        )

    def render_note(section_key, title, value):
        _render_patient_note_section(
            patient_id,
            patient,
            section_key,
            title,
            value,
            lambda: _render_view_section_editor(
                patient_id,
                patient,
                section_key,
            ),
        )

    name = _patient_full_name(patient)
    address = _format_address(patient)
    guardian_name = _patient_full_name(
        {
            "first_name": patient.get("guardian_first_name"),
            "middle_name": patient.get("guardian_middle_name"),
            "last_name": patient.get("guardian_last_name"),
        }
    )
    guardian_address = _format_address(patient, prefix="guardian_")
    displayed_fields = {
        "patient_id",
        "patient_case_number",
        "date_registered",
        "referral_noted_by",
        "referring_person_or_instance",
        "date_of_referral",
        "means_of_referral",
        "referral_request",
        "agreements_made_for_further_interviewing",
        "interview_date",
        "interview_place",
        "interview_persons_present",
        "primary_source_of_information",
        "first_name",
        "middle_name",
        "last_name",
        "extension_name",
        "calculated_age",
        "street_address",
        "purok",
        "barangay",
        "city_municipality",
        "province",
        "date_of_birth",
        "sex",
        "civil_status",
        "religion",
        "educational_attainment",
        "work_experience",
        "guardian_last_name",
        "guardian_first_name",
        "guardian_middle_name",
        "guardian_street_address",
        "g_barangay",
        "g_city",
        "g_province",
        "guardian_contact_person",
        "g_contact_number",
        "guardian_barangay",
        "guardian_city_municipality",
        "guardian_province",
        "guardian_contact_number",
        "family_composition",
        "household_member_count",
        "total_annual_income",
        "poverty_threshold_per_year",
        "poverty_rating",
        "classification_after_interview",
        "classification_after_home_visit",
        "chief_complaint_patient",
        "chief_complaint_relatives",
        "complaint_duration",
        "complaint_onset",
        "complaint_recent",
        "complaint_previous_hospitalization",
        "interviewers_initial_impression",
        "history_of_illness",
        "mental_status_examination",
        "nurses_observation",
        "diagnosis",
        "treatment",
        "parenteral_medication_records",
        "status",
    }

    render_fields(
        "administration",
        SECTION_TITLES["administration"],
        [
            (
                FIELD_LABELS["patient_case_number"],
                patient.get("patient_case_number"),
            ),
            (FIELD_LABELS["status"], patient.get("status")),
            (
                FIELD_LABELS["date_registered"],
                format_date_for_display(patient.get("date_registered")),
            ),
        ],
    )
    render_fields(
        "referral",
        SECTION_TITLES["referral"],
        [
            (FIELD_LABELS["referral_noted_by"], patient.get("referral_noted_by")),
            (
                FIELD_LABELS["referring_person_or_instance"],
                patient.get("referring_person_or_instance"),
            ),
            (
                FIELD_LABELS["date_of_referral"],
                format_date_for_display(patient.get("date_of_referral")),
            ),
            (FIELD_LABELS["means_of_referral"], patient.get("means_of_referral")),
            (FIELD_LABELS["referral_request"], patient.get("referral_request")),
            (
                FIELD_LABELS["agreements_made_for_further_interviewing"],
                patient.get("agreements_made_for_further_interviewing"),
            ),
        ],
    )
    render_fields(
        "interview",
        VIEW_SECTION_TITLES["interview"],
        [
            (
                FIELD_LABELS["interview_date"],
                format_date_for_display(patient.get("interview_date")),
            ),
            (FIELD_LABELS["interview_place"], patient.get("interview_place")),
            (
                FIELD_LABELS["interview_persons_present"],
                patient.get("interview_persons_present"),
            ),
            (
                FIELD_LABELS["primary_source_of_information"],
                patient.get("primary_source_of_information"),
            ),
        ],
    )
    render_fields(
        "identifying",
        VIEW_SECTION_TITLES["identifying"],
        [
            (FIELD_LABELS["client_name"], name),
            (
                FIELD_LABELS["date_of_birth"],
                format_date_for_display(patient.get("date_of_birth")),
            ),
            (FIELD_LABELS["age"], patient.get("calculated_age")),
            (FIELD_LABELS["address"], address),
            (FIELD_LABELS["sex"], patient.get("sex")),
            (FIELD_LABELS["civil_status"], patient.get("civil_status")),
            (FIELD_LABELS["religion"], patient.get("religion")),
            (
                FIELD_LABELS["educational_attainment"],
                patient.get("educational_attainment"),
            ),
            (FIELD_LABELS["work_experience"], patient.get("work_experience")),
        ],
    )
    render_fields(
        "relatives",
        SECTION_TITLES["relatives"],
        [
            ("Name", guardian_name),
            (FIELD_LABELS["address"], guardian_address),
            (
                FIELD_LABELS["contact_person"],
                patient.get("guardian_contact_person"),
            ),
            (FIELD_LABELS["contact_number"], patient.get("g_contact_number")),
        ],
    )
    _render_editable_patient_section(
        patient_id,
        patient,
        "family",
        SECTION_TITLES["family"],
        lambda: st.dataframe(
            dataframe_from_storage(
                patient.get("family_composition"),
                FAMILY_COLUMNS,
            ),
            hide_index=True,
            width="stretch",
            alt="Family composition of the patient",
        ),
        lambda: _render_view_section_editor(
            patient_id,
            patient,
            "family",
        ),
    )
    render_fields(
        "classification",
        SECTION_TITLES["classification"],
        [
            (
                FIELD_LABELS["household_member_count"],
                patient.get("household_member_count"),
            ),
            (
                FIELD_LABELS["total_annual_income"],
                patient.get("total_annual_income"),
            ),
            (
                FIELD_LABELS["poverty_threshold_per_year"],
                patient.get("poverty_threshold_per_year"),
            ),
            (FIELD_LABELS["poverty_rating"], patient.get("poverty_rating")),
            (
                FIELD_LABELS["classification_after_interview"],
                patient.get("classification_after_interview"),
            ),
            (
                FIELD_LABELS["classification_after_home_visit"],
                patient.get("classification_after_home_visit"),
            ),
        ],
    )
    render_fields(
        "complaint",
        SECTION_TITLES["complaint"],
        [
            (
                FIELD_LABELS["chief_complaint_patient"],
                patient.get("chief_complaint_patient"),
            ),
            (
                FIELD_LABELS["chief_complaint_relatives"],
                patient.get("chief_complaint_relatives"),
            ),
            (FIELD_LABELS["complaint_duration"], patient.get("complaint_duration")),
            (FIELD_LABELS["complaint_onset"], patient.get("complaint_onset")),
            (FIELD_LABELS["complaint_recent"], patient.get("complaint_recent")),
            (
                FIELD_LABELS["complaint_previous_hospitalization"],
                patient.get("complaint_previous_hospitalization"),
            ),
        ],
    )
    render_note(
        "impression",
        SECTION_TITLES["impression"],
        patient.get("interviewers_initial_impression"),
    )
    for section_key in (
        "history_of_illness",
        "mental_status_examination",
        "nurses_observation",
    ):
        render_note(
            section_key,
            SECTION_TITLES[section_key],
            patient.get(section_key),
        )
    render_note(
        "diagnosis",
        SECTION_TITLES["diagnosis"],
        patient.get("diagnosis"),
    )
    render_note(
        "treatment",
        SECTION_TITLES["treatment"],
        patient.get("treatment"),
    )

    _render_editable_patient_section(
        patient_id,
        patient,
        "medications",
        SECTION_TITLES["medications"],
        lambda: st.dataframe(
            dataframe_from_storage(
                patient.get("parenteral_medication_records"),
                MEDICATION_COLUMNS,
            ),
            hide_index=True,
            width="stretch",
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
            alt="Parenteral medication sheet",
        ),
        lambda: _render_view_section_editor(
            patient_id,
            patient,
            "medications",
        ),
    )

    patient_field_order = list(patient.keys())
    remaining_fields = [
        field for field in patient_field_order if field not in displayed_fields
    ]
    if remaining_fields:
        with st.container(border=True):
            st.markdown("#### Other Record Fields")
            value_columns = st.columns(2)
            for index, field in enumerate(remaining_fields):
                value = patient[field]
                with value_columns[index % 2]:
                    _render_patient_detail_label(_detail_label(field))
                    _render_patient_detail_value(value)

def _patient_full_name(record):
    return " ".join(
        str(record.get(field) or "").strip()
        for field in ("first_name", "middle_name", "last_name", "extension_name")
        if record.get(field) and str(record[field]).strip()
    )


def _render_patient_results_table(
    records, column_widths=None, column_gap=None
):
    if column_widths is None:
        column_widths = [1.2, 2.2, 0.9, 0.6, 0.75]
    headers = ("Patient ID", "Address", "Gender", "Age", "Action")
    selected_patient_id = None

    def _render_columns():
        if column_gap is None:
            return st.columns(column_widths, vertical_alignment="center")
        return st.columns(
            column_widths,
            vertical_alignment="center",
            gap=column_gap,
        )

    with st.container(border=True, key="patient-results-table"):
        with st.container(key="patient-results-table-header"):
            header_columns = _render_columns()
            for column, header in zip(header_columns, headers):
                with column:
                    st.markdown(
                        f'<div class="patient-results-table-header-label">'
                        f"<strong>{header}</strong></div>",
                        unsafe_allow_html=True,
                    )

        for index, record in enumerate(records):
            address = ", ".join(
                part
                for part in (
                    str(record.get("city_municipality") or "").strip(),
                    str(record.get("province") or "").strip(),
                )
                if part
            ) or "—"
            age = (
                record["calculated_age"]
                if record.get("calculated_age") is not None
                else "—"
            )
            with st.container(key=f"patient-result-row-{index}"):
                row_columns = _render_columns()
                with row_columns[0]:
                    st.write(record.get("patient_case_number") or "Not assigned")
                with row_columns[1]:
                    st.write(address)
                with row_columns[2]:
                    st.write(record.get("sex") or "—")
                with row_columns[3]:
                    st.write(str(age))
                with row_columns[4]:
                    if st.button(
                        "👁 View",
                        key=f"view_patient_record_{index}",
                        type="secondary",
                        help="Open the full patient record",
                        width="stretch",
                    ):
                        selected_patient_id = record["patient_id"]

    return selected_patient_id


def _render_patient_results(records, filters_applied):
    st.markdown(
        f"### {len(records):,} "
        f"{'Matching' if filters_applied else 'Archived'} Patient Record(s)"
    )
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button(
            "+ Encode New Record",
            type="primary",
            key="open_encode_dialog",
            width="content",
        ):
            _open_encode_dialog()

    with st.container(key="patient-results-table-hint"):
        st.caption("Click View on any patient row to open their full record.")

    selected_patient_id = _render_patient_results_table(records)
    if selected_patient_id is not None:
        st.session_state["manage_selected_patient_id"] = selected_patient_id
        st.session_state.pop("manage_edit_patient_id", None)
        st.session_state.pop("manage_delete_patient_id", None)
        st.session_state.pop("manage_return_session_patient_id", None)
        st.session_state.pop("manage_edit_return_session_id", None)
        st.session_state.pop("manage_delete_return_session_id", None)
        st.rerun()


def _render_selected_patient_detail(selected_id):
    try:
        conn = get_local_connection()
    except Exception as error:
        st.error(f"Unable to open the local patient archive: {error}")
        return
    try:
        selected_patient = conn.execute(
            "SELECT * FROM patients WHERE patient_id = ?", (selected_id,)
        ).fetchone()
    except Exception as error:
        st.error(f"Unable to read the selected patient record: {error}")
        return
    finally:
        conn.close()

    if selected_patient is None:
        st.error("The selected patient record is no longer available.")
        _close_patient_detail_dialog()
        st.rerun()
        return

    patient = dict(selected_patient)
    selected_name = _patient_full_name(patient) or "Unnamed patient"
    case_number = patient.get("patient_case_number") or "Not assigned"
    logging_return_session = (
        st.session_state.get("manage_return_session_patient_id") == selected_id
    )
    with st.container(key="selected-patient-details"):
        _render_view_record_scroll_preserver(selected_id)
        case_column, delete_column = st.columns(
            [8, 0.45],
            vertical_alignment="center",
            gap="small",
        )
        with case_column:
            st.caption("Patient ID / Case Number")
            st.title(case_number)
        if not logging_return_session:
            with delete_column:
                if st.button(
                    "",
                    key=f"delete_selected_patient_{selected_id}",
                    icon=":material/delete:",
                    help="Delete record",
                    width="content",
                ):
                    st.session_state["manage_delete_patient_id"] = selected_id
                    st.session_state.pop("manage_edit_patient_id", None)
                    st.session_state.pop("manage_edit_return_session_id", None)
                    st.session_state.pop("manage_delete_return_session_id", None)
                    st.rerun()
        if logging_return_session:
            st.subheader("Log Return Session")
            _render_return_session_form(selected_id, case_number)
            return

        profile_tab, return_sessions_tab = st.tabs(
            ["Patient Profile", "Return Sessions"],
            key=f"patient-detail-sections-{selected_id}",
            on_change="rerun",
        )
        with profile_tab:
            delete_id = st.session_state.get("manage_delete_patient_id")
            if delete_id == selected_id:
                _render_patient_delete_confirmation(selected_id, patient)
            else:
                st.markdown(f"### {selected_name}")
                _render_patient_details(patient)

        with return_sessions_tab:
            heading_column, action_column = st.columns(
                [5, 2],
                vertical_alignment="center",
            )
            with heading_column:
                st.markdown("#### Return Sessions")
            with action_column:
                if st.button(
                    "+ Log Return Session",
                    icon=":material/event_note:",
                    key=f"log_return_session_{selected_id}",
                    width="stretch",
                ):
                    st.session_state["manage_return_session_patient_id"] = (
                        selected_id
                    )
                    st.session_state.pop("manage_edit_patient_id", None)
                    st.session_state.pop("manage_delete_patient_id", None)
                    st.session_state.pop("manage_edit_return_session_id", None)
                    st.session_state.pop("manage_delete_return_session_id", None)
                    st.rerun()
            _render_return_session_history(selected_id, case_number)


def _reset_return_session_substate(session_state, patient_id):
    if session_state.get("manage_return_session_patient_id") != patient_id:
        return False

    session_state.pop("manage_return_session_patient_id", None)
    for field in (
        "form",
        "date",
        "time",
        "place",
        "noted-by-select",
        "persons-present",
        "complaint-patient",
        "complaint-relatives",
        "manifestations",
        "hospitalization",
        "mse",
        "nurses-observation",
        "diagnosis",
        "treatment",
        "medications",
    ):
        session_state.pop(f"return-session-{field}-{patient_id}", None)
    return True


def _close_patient_detail_dialog():
    selected_patient_id = st.session_state.get("manage_selected_patient_id")
    if _reset_return_session_substate(
        st.session_state,
        selected_patient_id,
    ):
        return

    for key in (
        "manage_selected_patient_id",
        "manage_edit_patient_id",
        "manage_delete_patient_id",
        "manage_return_session_patient_id",
        "manage_edit_return_session_id",
        "manage_delete_return_session_id",
        "record_results_table",
    ):
        st.session_state.pop(key, None)
    section_key = st.session_state.pop("view_editing_section", None)
    patient_id = st.session_state.pop("view_editing_patient_id", None)
    if section_key and patient_id is not None:
        _clear_view_edit_widgets(
            _view_edit_widget_prefix(patient_id, section_key)
        )
    pending_prefix = st.session_state.pop("view_edit_cleanup_prefix", None)
    if pending_prefix:
        _clear_view_edit_widgets(pending_prefix)


def _render_view_record_scroll_preserver(patient_id):
    is_new_patient = (
        st.session_state.get("view_record_scroll_patient_id") != patient_id
    )
    if is_new_patient:
        st.session_state["view_record_scroll_patient_id"] = patient_id

    script = """
    <script>
    (() => {
      const storageKey = "boc_view_record_scroll";
      const parentWindow = window.parent;
      const parentDocument = parentWindow.document;
      const storage = parentWindow.sessionStorage;
      const resetScroll = __RESET_SCROLL__;

      if (resetScroll) {
        storage.setItem(storageKey, "0");
      }

      const findScrollTarget = () => {
        const dialog = Array.from(
          parentDocument.querySelectorAll('[role="dialog"]'),
        ).find((element) =>
          element.querySelector(".st-key-selected-patient-details"),
        );
        if (!dialog) return null;

        const isScrollable = (element) => {
          const style = parentWindow.getComputedStyle(element);
          return (
            /(auto|scroll)/.test(style.overflowY) &&
            element.scrollHeight > element.clientHeight + 1
          );
        };
        const insideDialog = [dialog, ...dialog.querySelectorAll("*")]
          .filter(isScrollable)
          .sort((left, right) => right.clientHeight - left.clientHeight);
        if (insideDialog.length) return insideDialog[0];

        for (
          let ancestor = dialog.parentElement;
          ancestor && ancestor !== parentDocument.body;
          ancestor = ancestor.parentElement
        ) {
          if (isScrollable(ancestor)) return ancestor;
        }
        return dialog;
      };

      let scrollTarget = null;
      let scrollHandler = null;

      const attachScrollListener = (element) => {
        if (scrollTarget === element) return;
        if (scrollTarget && scrollHandler) {
          scrollTarget.removeEventListener("scroll", scrollHandler);
        }

        const previousHandler = element.__bocViewRecordScrollHandler;
        if (previousHandler) {
          element.removeEventListener("scroll", previousHandler);
        }
        scrollTarget = element;
        scrollHandler = () => {
          savedScroll = element.scrollTop;
          storage.setItem(storageKey, String(savedScroll));
        };
        element.__bocViewRecordScrollHandler = scrollHandler;
        element.addEventListener("scroll", scrollHandler, { passive: true });
      };

      let savedScroll = Number.parseInt(
        storage.getItem(storageKey) || "0",
        10,
      );
      const restoreStartedAt = Date.now();
      const restoreScroll = () => {
        const element = findScrollTarget();
        if (element) {
          attachScrollListener(element);
          if (Number.isFinite(savedScroll)) {
            const maxScroll = element.scrollHeight - element.clientHeight;
            if (savedScroll <= maxScroll + 1) {
              element.scrollTop = savedScroll;
            }
          }
        }

        if (Date.now() - restoreStartedAt < 1500) {
          requestAnimationFrame(restoreScroll);
        }
      };

      restoreScroll();
    })();
    </script>
    """
    script = script.replace(
        "__RESET_SCROLL__",
        json.dumps(is_new_patient),
    )
    st.html(script, unsafe_allow_javascript=True)


def _save_return_session(
    patient_id: int,
    session_date: datetime.date,
    session_time: datetime.time,
    *,
    interview_place: str,
    information_noted_by: str,
    interview_persons_present: str,
    chief_complaint_patient: str,
    chief_complaint_relatives: str,
    recent_manifestations: str,
    new_hospitalization_since_last_visit: str,
    mental_status_examination: str,
    nurses_observation: str,
    diagnosis_statement: str,
    treatment_plan: str,
    parenteral_medication_records: str,
) -> None:
    attendance_status = "Completed"
    conn = get_local_connection()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            patient = conn.execute(
                "SELECT patient_case_number FROM patients WHERE patient_id = ?",
                (patient_id,),
            ).fetchone()
            if patient is None:
                raise ValueError("The patient record is no longer available.")
            conn.execute(
                """
                INSERT INTO patient_return_sessions (
                    patient_id, session_date, session_time, attendance_status,
                    interview_place, information_noted_by,
                    interview_persons_present, chief_complaint_patient,
                    chief_complaint_relatives, recent_manifestations,
                    new_hospitalization_since_last_visit,
                    mental_status_examination, nurses_observation,
                    diagnosis_statement, treatment_plan,
                    parenteral_medication_records
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    patient_id,
                    session_date.isoformat(),
                    session_time.strftime("%H:%M"),
                    attendance_status,
                    _clean_return_session_text(interview_place),
                    _clean_return_session_text(information_noted_by),
                    _clean_return_session_text(interview_persons_present),
                    _clean_return_session_text(chief_complaint_patient),
                    _clean_return_session_text(chief_complaint_relatives),
                    _clean_return_session_text(recent_manifestations),
                    _clean_return_session_text(
                        new_hospitalization_since_last_visit
                    ),
                    _clean_return_session_text(mental_status_examination),
                    _clean_return_session_text(nurses_observation),
                    _clean_return_session_text(diagnosis_statement),
                    _clean_return_session_text(treatment_plan),
                    parenteral_medication_records,
                ),
            )
            conn.execute(
                "INSERT INTO admin_logs (action_type, details) VALUES (?, ?)",
                (
                    "PATIENT RETURN SESSION LOGGED",
                    f"Logged a return session for patient case "
                    f"{patient['patient_case_number'] or 'not assigned'} on "
                    f"{session_date.isoformat()} ({attendance_status}).",
                ),
            )
    finally:
        conn.close()


def _clean_return_session_text(value: str | None) -> str | None:
    cleaned_value = str(value or "").strip()
    return cleaned_value or None


def _serialize_return_session_medication_log(
    dataframe: pd.DataFrame,
) -> str:
    records = []
    for row in dataframe.to_dict(orient="records"):
        cleaned_row = {}
        for column in MEDICATION_COLUMNS:
            value = row.get(column)
            if value is None or pd.isna(value):
                cleaned_row[column] = None
            elif isinstance(value, str) and not value.strip():
                cleaned_row[column] = None
            else:
                cleaned_row[column] = value
        if any(value is not None for value in cleaned_row.values()):
            records.append(cleaned_row)
    return dataframe_to_storage(
        pd.DataFrame(records, columns=MEDICATION_COLUMNS)
    )


def _return_session_edit_widget_keys(
    patient_id: int,
    session_id: int,
) -> tuple[str, ...]:
    prefix = f"return-session-edit-{patient_id}-{session_id}"
    return tuple(
        f"{prefix}-{field}"
        for field in (
            "date",
            "time",
            "status",
            "place",
            "noted-by-select",
            "persons-present",
            "complaint-patient",
            "complaint-relatives",
            "manifestations",
            "hospitalization",
            "mse",
            "nurses-observation",
            "diagnosis",
            "treatment",
            "notes",
            "medications",
        )
    )


def _clear_return_session_edit_form_state(
    patient_id: int, session_id: int
) -> None:
    for key in _return_session_edit_widget_keys(patient_id, session_id):
        st.session_state.pop(key, None)


def _update_return_session(
    patient_id: int,
    session_id: int,
    *,
    session_date: datetime.date,
    session_time: datetime.time,
    attendance_status: str,
    interview_place: str,
    information_noted_by: str,
    interview_persons_present: str,
    chief_complaint_patient: str,
    chief_complaint_relatives: str,
    recent_manifestations: str,
    new_hospitalization_since_last_visit: str,
    mental_status_examination: str,
    nurses_observation: str,
    diagnosis_statement: str,
    treatment_plan: str,
    notes: str,
    parenteral_medication_records: str,
) -> None:
    cleaned_status = _clean_return_session_text(attendance_status)
    if cleaned_status is None:
        raise ValueError("Attendance / Status is required.")

    conn = get_local_connection()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            patient = conn.execute(
                "SELECT patient_case_number FROM patients WHERE patient_id = ?",
                (patient_id,),
            ).fetchone()
            if patient is None:
                raise ValueError("The patient record is no longer available.")
            existing_session = conn.execute(
                """
                SELECT return_session_id
                FROM patient_return_sessions
                WHERE return_session_id = ? AND patient_id = ?
                """,
                (session_id, patient_id),
            ).fetchone()
            if existing_session is None:
                raise ValueError("The return session is no longer available.")

            result = conn.execute(
                """
                UPDATE patient_return_sessions
                SET session_date = ?, session_time = ?, attendance_status = ?,
                    interview_place = ?, information_noted_by = ?,
                    interview_persons_present = ?, chief_complaint_patient = ?,
                    chief_complaint_relatives = ?, recent_manifestations = ?,
                    new_hospitalization_since_last_visit = ?,
                    mental_status_examination = ?, nurses_observation = ?,
                    diagnosis_statement = ?, treatment_plan = ?, notes = ?,
                    parenteral_medication_records = ?
                WHERE return_session_id = ? AND patient_id = ?
                """,
                (
                    session_date.isoformat(),
                    session_time.strftime("%H:%M"),
                    cleaned_status,
                    _clean_return_session_text(interview_place),
                    _clean_return_session_text(information_noted_by),
                    _clean_return_session_text(interview_persons_present),
                    _clean_return_session_text(chief_complaint_patient),
                    _clean_return_session_text(chief_complaint_relatives),
                    _clean_return_session_text(recent_manifestations),
                    _clean_return_session_text(
                        new_hospitalization_since_last_visit
                    ),
                    _clean_return_session_text(mental_status_examination),
                    _clean_return_session_text(nurses_observation),
                    _clean_return_session_text(diagnosis_statement),
                    _clean_return_session_text(treatment_plan),
                    _clean_return_session_text(notes),
                    parenteral_medication_records,
                    session_id,
                    patient_id,
                ),
            )
            if result.rowcount != 1:
                raise RuntimeError("The return session was not updated.")
            conn.execute(
                "INSERT INTO admin_logs (action_type, details) VALUES (?, ?)",
                (
                    "PATIENT RETURN SESSION UPDATED",
                    f"Updated return session {session_id} for patient case "
                    f"{patient['patient_case_number'] or 'not assigned'} on "
                    f"{session_date.isoformat()} ({cleaned_status}).",
                ),
            )
    finally:
        conn.close()


def _delete_return_session(patient_id: int, session_id: int) -> None:
    conn = get_local_connection()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            session = conn.execute(
                """
                SELECT p.patient_case_number, s.session_date
                FROM patient_return_sessions AS s
                JOIN patients AS p ON p.patient_id = s.patient_id
                WHERE s.return_session_id = ? AND s.patient_id = ?
                """,
                (session_id, patient_id),
            ).fetchone()
            if session is None:
                raise ValueError("The return session is no longer available.")
            result = conn.execute(
                """
                DELETE FROM patient_return_sessions
                WHERE return_session_id = ? AND patient_id = ?
                """,
                (session_id, patient_id),
            )
            if result.rowcount != 1:
                raise RuntimeError("The return session was not deleted.")
            conn.execute(
                "INSERT INTO admin_logs (action_type, details) VALUES (?, ?)",
                (
                    "PATIENT RETURN SESSION DELETED",
                    f"Deleted return session {session_id} for patient case "
                    f"{session['patient_case_number'] or 'not assigned'} on "
                    f"{session['session_date']}.",
                ),
            )
    finally:
        conn.close()


def _render_return_session_edit_form(
    patient_id: int,
    case_number: str,
    session: dict,
) -> None:
    session_id = session["Return Session ID"]
    try:
        session_date_value = parse_stored_date(session["Session date"])
        if not isinstance(session_date_value, datetime.date):
            raise ValueError("The stored session date is invalid.")
        stored_time = str(session["Session time"])
        session_time_value = None
        for time_format in ("%H:%M", "%H:%M:%S"):
            try:
                session_time_value = datetime.datetime.strptime(
                    stored_time, time_format
                ).time()
                break
            except ValueError:
                continue
        if session_time_value is None:
            raise ValueError("The stored session time is invalid.")
        medication_table = dataframe_from_storage(
            session["Parenteral Medication Log"],
            MEDICATION_COLUMNS,
        )
    except (TypeError, ValueError) as error:
        st.error(f"Unable to edit this return session: {error}")
        return

    if medication_table.empty:
        medication_table = pd.DataFrame(
            [
                {
                    column: None if column.startswith("Date") else ""
                    for column in MEDICATION_COLUMNS
                }
            ],
            columns=MEDICATION_COLUMNS,
        )

    prefix = f"return-session-edit-{patient_id}-{session_id}"
    with st.form(key=f"{prefix}-form"):
        st.markdown("#### Edit Return Session")
        date_column, time_column = st.columns(2)
        with date_column:
            session_date = st.date_input(
                "Session Date",
                value=session_date_value,
                format=DATE_DISPLAY_FORMAT,
                key=f"{prefix}-date",
            )
        with time_column:
            session_time = st.time_input(
                "Session Time",
                value=session_time_value,
                key=f"{prefix}-time",
            )
        st.caption(f"Patient Case Number: {case_number}")
        attendance_status = st.text_input(
            "Attendance / Status",
            value=session["Attendance / status"] or "",
            key=f"{prefix}-status",
        )
        place_column, noted_by_column = st.columns(2)
        with place_column:
            interview_place = st.text_input(
                "Place of Interview",
                value=session["Place of Interview"] or "",
                key=f"{prefix}-place",
            )
        with noted_by_column:
            noted_by_value = session["Information Noted By"] or ""
            noted_by_options = _admin_name_options(noted_by_value)
            information_noted_by = st.selectbox(
                "Information Noted By",
                noted_by_options,
                index=(
                    noted_by_options.index(noted_by_value)
                    if noted_by_value
                    else None
                ),
                accept_new_options=True,
                key=f"{prefix}-noted-by-select",
            )
        interview_persons_present = st.text_area(
            "Persons Present During Interview",
            value=session["Persons Present During Interview"] or "",
            key=f"{prefix}-persons-present",
        )
        st.markdown("#### Follow-Up Chief Complaint & Manifestations")
        complaint_column, relative_column = st.columns(2)
        with complaint_column:
            chief_complaint_patient = st.text_area(
                "Chief Complaint (Patient)",
                value=session["Chief Complaint (Patient)"] or "",
                key=f"{prefix}-complaint-patient",
            )
        with relative_column:
            chief_complaint_relatives = st.text_area(
                "Chief Complaint (Relatives)",
                value=session["Chief Complaint (Relatives)"] or "",
                key=f"{prefix}-complaint-relatives",
            )
        manifestation_column, hospitalization_column = st.columns(2)
        with manifestation_column:
            recent_manifestations = st.text_area(
                "Recent Manifestations",
                value=session["Recent Manifestations"] or "",
                key=f"{prefix}-manifestations",
            )
        with hospitalization_column:
            new_hospitalization_since_last_visit = st.text_area(
                "Any New Hospitalization Since Last Visit",
                value=session["Any New Hospitalization Since Last Visit"] or "",
                key=f"{prefix}-hospitalization",
            )
        st.markdown("#### Clinical Examination, Treatment & Progress")
        examination_column, observation_column = st.columns(2)
        with examination_column:
            mental_status_examination = st.text_area(
                "Mental Status Examination (MSE)",
                value=session["Mental Status Examination (MSE)"] or "",
                key=f"{prefix}-mse",
            )
        with observation_column:
            nurses_observation = st.text_area(
                "Nurses Observation",
                value=session["Nurses Observation"] or "",
                key=f"{prefix}-nurses-observation",
            )
        diagnosis_column, treatment_column = st.columns(2)
        with diagnosis_column:
            diagnosis_statement = st.text_area(
                "Updated Diagnosis Statement",
                value=session["Updated Diagnosis Statement"] or "",
                key=f"{prefix}-diagnosis",
            )
        with treatment_column:
            treatment_plan = st.text_area(
                "Treatment Plan / Progress Notes",
                value=session["Treatment Plan / Progress Notes"] or "",
                key=f"{prefix}-treatment",
            )
        notes = st.text_area(
            "Notes / Remarks",
            value=session["Notes / remarks"] or "",
            key=f"{prefix}-notes",
        )
        st.markdown("##### Parenteral Medication Log Sheet")
        edited_medication_table = st.data_editor(
            medication_table,
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
            num_rows="dynamic",
            width="stretch",
            alt="Parenteral medication entries for this return session",
            key=f"{prefix}-medications",
        )
        submitted = st.form_submit_button(
            "Save Session",
            key=f"{prefix}-save",
            type="primary",
        )

    if st.button(
        "Cancel Edit",
        key=f"{prefix}-cancel",
    ):
        st.session_state.pop("manage_edit_return_session_id", None)
        st.rerun()

    if submitted:
        if not attendance_status.strip():
            st.error("Attendance / Status is required.")
            return
        if not is_valid_person_name(information_noted_by):
            st.error(
                "Worker Name: Names must contain letters only and cannot "
                "include numbers."
            )
            return
        try:
            _update_return_session(
                patient_id,
                session_id,
                session_date=session_date,
                session_time=session_time,
                attendance_status=attendance_status,
                interview_place=interview_place,
                information_noted_by=information_noted_by,
                interview_persons_present=interview_persons_present,
                chief_complaint_patient=chief_complaint_patient,
                chief_complaint_relatives=chief_complaint_relatives,
                recent_manifestations=recent_manifestations,
                new_hospitalization_since_last_visit=(
                    new_hospitalization_since_last_visit
                ),
                mental_status_examination=mental_status_examination,
                nurses_observation=nurses_observation,
                diagnosis_statement=diagnosis_statement,
                treatment_plan=treatment_plan,
                notes=notes,
                parenteral_medication_records=(
                    _serialize_return_session_medication_log(
                        edited_medication_table
                    )
                ),
            )
        except (sqlite3.Error, TypeError, ValueError, RuntimeError) as error:
            st.error(f"Unable to update the return session: {error}")
        else:
            st.session_state.pop("manage_edit_return_session_id", None)
            st.session_state["manage_success_message"] = (
                "Return session updated successfully."
            )
            st.rerun()


def _render_return_session_form(patient_id: int, case_number: str) -> None:
    with st.form(key=f"return-session-form-{patient_id}"):
        st.markdown("#### Visit & Interview Logistics")
        date_column, time_column = st.columns(2)
        with date_column:
            session_date = st.date_input(
                "Session Date",
                value=datetime.date.today(),
                format=DATE_DISPLAY_FORMAT,
                key=f"return-session-date-{patient_id}",
            )
        with time_column:
            session_time = st.time_input(
                "Session Time",
                value=datetime.datetime.now().time().replace(
                    second=0,
                    microsecond=0,
                ),
                key=f"return-session-time-{patient_id}",
            )
        st.caption(f"Patient Case Number: {case_number}")
        place_column, noted_by_column = st.columns(2)
        with place_column:
            interview_place = st.text_input(
                "Place of Interview",
                key=f"return-session-place-{patient_id}",
            )
        with noted_by_column:
            information_noted_by = st.selectbox(
                "Information Noted By",
                _admin_name_options(),
                index=None,
                accept_new_options=True,
                key=f"return-session-noted-by-select-{patient_id}",
            )
        interview_persons_present = st.text_area(
            "Persons Present During Interview",
            key=f"return-session-persons-present-{patient_id}",
        )
        st.markdown("#### Follow-Up Chief Complaint & Manifestations")
        complaint_column, relative_column = st.columns(2)
        with complaint_column:
            chief_complaint_patient = st.text_area(
                "Chief Complaint (Patient)",
                key=f"return-session-complaint-patient-{patient_id}",
            )
        with relative_column:
            chief_complaint_relatives = st.text_area(
                "Chief Complaint (Relatives)",
                key=f"return-session-complaint-relatives-{patient_id}",
            )
        manifestation_column, hospitalization_column = st.columns(2)
        with manifestation_column:
            recent_manifestations = st.text_area(
                "Recent Manifestations",
                key=f"return-session-manifestations-{patient_id}",
            )
        with hospitalization_column:
            new_hospitalization_since_last_visit = st.text_area(
                "Any New Hospitalization Since Last Visit",
                key=f"return-session-hospitalization-{patient_id}",
            )

        st.markdown(
            "#### Clinical Examination, Treatment & Parenteral Medication"
        )
        examination_column, observation_column = st.columns(2)
        with examination_column:
            mental_status_examination = st.text_area(
                "Mental Status Examination (MSE)",
                key=f"return-session-mse-{patient_id}",
            )
        with observation_column:
            nurses_observation = st.text_area(
                "Nurses Observation",
                key=f"return-session-nurses-observation-{patient_id}",
            )
        diagnosis_column, treatment_column = st.columns(2)
        with diagnosis_column:
            diagnosis_statement = st.text_area(
                "Updated Diagnosis Statement",
                key=f"return-session-diagnosis-{patient_id}",
            )
        with treatment_column:
            treatment_plan = st.text_area(
                "Treatment Plan / Progress Notes",
                key=f"return-session-treatment-{patient_id}",
            )
        st.markdown("##### Parenteral Medication Log Sheet")
        medication_table = pd.DataFrame(
            [
                {
                    column: None if column.startswith("Date") else ""
                    for column in MEDICATION_COLUMNS
                }
            ],
            columns=MEDICATION_COLUMNS,
        )
        edited_medication_table = st.data_editor(
            medication_table,
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
            num_rows="dynamic",
            width="stretch",
            alt="Parenteral medication entries for this return session",
            key=f"return-session-medications-{patient_id}",
        )
        submitted = st.form_submit_button(
            "Save Return Session",
            type="primary",
        )

    if submitted:
        if not is_valid_person_name(information_noted_by):
            st.error(
                "Worker Name: Names must contain letters only and cannot "
                "include numbers."
            )
            return
        try:
            _save_return_session(
                patient_id,
                session_date,
                session_time,
                interview_place=interview_place,
                information_noted_by=information_noted_by,
                interview_persons_present=interview_persons_present,
                chief_complaint_patient=chief_complaint_patient,
                chief_complaint_relatives=chief_complaint_relatives,
                recent_manifestations=recent_manifestations,
                new_hospitalization_since_last_visit=(
                    new_hospitalization_since_last_visit
                ),
                mental_status_examination=mental_status_examination,
                nurses_observation=nurses_observation,
                diagnosis_statement=diagnosis_statement,
                treatment_plan=treatment_plan,
                parenteral_medication_records=(
                    _serialize_return_session_medication_log(
                        edited_medication_table
                    )
                ),
            )
        except (sqlite3.Error, TypeError, ValueError) as error:
            st.error(f"Unable to save the return session: {error}")
        else:
            st.session_state.pop("manage_return_session_patient_id", None)
            st.session_state["manage_success_message"] = (
                "Return session logged successfully."
            )
            st.rerun()


def _render_return_session_history(
    patient_id: int,
    case_number: str,
) -> None:
    try:
        conn = get_local_connection()
    except Exception as error:
        st.error(f"Unable to open the local patient archive: {error}")
        return
    try:
        sessions = conn.execute(
            """
            SELECT session_date AS "Session date",
                   session_time AS "Session time",
                   attendance_status AS "Attendance / status",
                   interview_place AS "Place of Interview",
                   information_noted_by AS "Information Noted By",
                   interview_persons_present AS "Persons Present During Interview",
                   chief_complaint_patient AS "Chief Complaint (Patient)",
                   chief_complaint_relatives AS "Chief Complaint (Relatives)",
                   recent_manifestations AS "Recent Manifestations",
                   new_hospitalization_since_last_visit AS
                       "Any New Hospitalization Since Last Visit",
                   mental_status_examination AS
                       "Mental Status Examination (MSE)",
                   nurses_observation AS "Nurses Observation",
                   diagnosis_statement AS "Updated Diagnosis Statement",
                   treatment_plan AS "Treatment Plan / Progress Notes",
                   parenteral_medication_records AS
                       "Parenteral Medication Log",
                   notes AS "Notes / remarks",
                   return_session_id AS "Return Session ID"
            FROM patient_return_sessions
            WHERE patient_id = ?
            ORDER BY session_date DESC, session_time DESC, return_session_id DESC
            """,
            (patient_id,),
        ).fetchall()
    except Exception as error:
        st.error(f"Unable to read return-session history: {error}")
        return
    finally:
        conn.close()

    with st.container(border=True, key="patient-return-session-history"):
        st.markdown("#### Return Session History")
        if not sessions:
            st.session_state.pop("manage_edit_return_session_id", None)
            st.session_state.pop("manage_delete_return_session_id", None)
            st.info("No return sessions have been logged for this patient.")
            return
        session_rows = [dict(session) for session in sessions]
        session_ids = {
            session["Return Session ID"] for session in session_rows
        }
        for state_key in (
            "manage_edit_return_session_id",
            "manage_delete_return_session_id",
        ):
            if st.session_state.get(state_key) not in session_ids:
                st.session_state.pop(state_key, None)

        base_labels = [
            f"{_format_return_session_date(session['Session date'])} · "
            f"{_format_return_session_time(session['Session time'])}"
            for session in session_rows
        ]
        label_counts = {}
        for label in base_labels:
            label_counts[label] = label_counts.get(label, 0) + 1
        session_labels = [
            (
                f"{label} · #{session['Return Session ID']}"
                if label_counts[label] > 1
                else label
            )
            for session, label in zip(session_rows, base_labels)
        ]
        session_tabs_key = f"patient-return-session-tabs-{patient_id}"
        selected_session_tab = st.session_state.get(session_tabs_key)
        if selected_session_tab not in session_labels:
            st.session_state.pop(session_tabs_key, None)
            selected_session_tab = None
        session_tabs = st.tabs(
            session_labels,
            default=selected_session_tab,
            key=session_tabs_key,
            on_change="rerun",
        )

        for session, session_label, session_tab in zip(
            session_rows, session_labels, session_tabs
        ):
            session_id = session["Return Session ID"]
            with session_tab:
                with st.container(
                    border=True,
                    key=f"return-session-card-{patient_id}-{session_id}",
                ):
                    if (
                        st.session_state.get("manage_edit_return_session_id")
                        == session_id
                    ):
                        _render_return_session_edit_form(
                            patient_id,
                            case_number,
                            session,
                        )
                        continue

                    delete_confirmed = (
                        st.session_state.get("manage_delete_return_session_id")
                        == session_id
                    )
                    if delete_confirmed:
                        st.warning(
                            "Delete this return session? This action cannot be undone."
                        )
                        cancel_column, confirm_column = st.columns(2)
                        with cancel_column:
                            if st.button(
                                "Keep Session",
                                key=f"cancel-return-session-delete-{session_id}",
                                width="stretch",
                            ):
                                st.session_state.pop(
                                    "manage_delete_return_session_id", None
                                )
                                st.rerun()
                        with confirm_column:
                            if st.button(
                                "Delete Session",
                                type="primary",
                                key=f"confirm-return-session-delete-{session_id}",
                                width="stretch",
                            ):
                                try:
                                    _delete_return_session(
                                        patient_id,
                                        session_id,
                                    )
                                except (
                                    sqlite3.Error,
                                    RuntimeError,
                                    TypeError,
                                    ValueError,
                                ) as error:
                                    st.error(
                                        f"Unable to delete the return session: {error}"
                                    )
                                else:
                                    st.session_state.pop(
                                        "manage_delete_return_session_id",
                                        None,
                                    )
                                    st.session_state["manage_success_message"] = (
                                        "Return session deleted successfully."
                                    )
                                    st.rerun()
                    else:
                        st.markdown("##### Return Session")
                        st.caption(
                            session["Attendance / status"]
                            or "—"
                        )
                        edit_column, delete_column = st.columns(2)
                        with edit_column:
                            if st.button(
                                "Edit Session",
                                key=f"edit-return-session-{session_id}",
                                icon=":material/edit:",
                                width="stretch",
                            ):
                                _clear_return_session_edit_form_state(
                                    patient_id,
                                    session_id,
                                )
                                st.session_state[
                                    "manage_edit_return_session_id"
                                ] = session_id
                                st.session_state.pop(
                                    "manage_delete_return_session_id", None
                                )
                                st.rerun()
                        with delete_column:
                            if st.button(
                                "Delete Session",
                                key=f"delete-return-session-{session_id}",
                                icon=":material/delete:",
                                width="stretch",
                            ):
                                st.session_state[
                                    "manage_delete_return_session_id"
                                ] = session_id
                                st.session_state.pop(
                                    "manage_edit_return_session_id", None
                                )
                                st.rerun()

                    _render_return_session_details(session)


def _render_return_session_details(session: dict) -> None:
    st.markdown("##### Visit & Interview Logistics")
    logistics_left, logistics_right = st.columns(2)
    with logistics_left:
        _render_return_session_value(
            "Place of Interview", session["Place of Interview"]
        )
        _render_return_session_value(
            "Information Noted By",
            session["Information Noted By"],
        )
    with logistics_right:
        _render_return_session_value(
            "Attendance / Status",
            session["Attendance / status"],
        )
        _render_return_session_value(
            "Persons Present During Interview",
            session["Persons Present During Interview"],
        )

    st.markdown("##### Follow-Up Chief Complaint & Manifestations")
    complaint_left, complaint_right = st.columns(2)
    with complaint_left:
        _render_return_session_value(
            "Chief Complaint (Patient)",
            session["Chief Complaint (Patient)"],
        )
        _render_return_session_value(
            "Recent Manifestations",
            session["Recent Manifestations"],
        )
    with complaint_right:
        _render_return_session_value(
            "Chief Complaint (Relatives)",
            session["Chief Complaint (Relatives)"],
        )
        _render_return_session_value(
            "Any New Hospitalization Since Last Visit",
            session["Any New Hospitalization Since Last Visit"],
        )

    st.markdown("##### Clinical Examination, Treatment & Progress")
    clinical_left, clinical_right = st.columns(2)
    with clinical_left:
        _render_return_session_value(
            "Mental Status Examination (MSE)",
            session["Mental Status Examination (MSE)"],
        )
        _render_return_session_value(
            "Updated Diagnosis Statement",
            session["Updated Diagnosis Statement"],
        )
    with clinical_right:
        _render_return_session_value(
            "Nurses Observation",
            session["Nurses Observation"],
        )
        _render_return_session_value(
            "Treatment Plan / Progress Notes",
            session["Treatment Plan / Progress Notes"],
        )

    st.markdown("##### Parenteral Medication Log")
    medication_table = dataframe_from_storage(
        session["Parenteral Medication Log"],
        MEDICATION_COLUMNS,
    )
    if medication_table.empty:
        st.caption("No parenteral medication entries recorded.")
    else:
        st.dataframe(
            medication_table,
            hide_index=True,
            width="stretch",
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
            alt="Parenteral medication entries for this return session",
        )
    _render_return_session_value(
        "Notes / Remarks", session["Notes / remarks"]
    )


def _format_return_session_date(value: str | None) -> str:
    return format_date_for_display(value) or "—"


def _format_return_session_time(value: str | None) -> str:
    try:
        return (
            datetime.datetime.strptime(str(value), "%H:%M")
            .strftime("%I:%M %p")
            .lstrip("0")
        )
    except (TypeError, ValueError):
        return str(value or "—")


def _render_return_session_value(label: str, value: str | None) -> None:
    _render_patient_detail_label(label)
    _render_patient_detail_value(value)


@st.dialog(
    "Patient Record",
    width="large",
    on_dismiss=_close_patient_detail_dialog,
)
def show_patient_detail_dialog(selected_id, success_message=None):
    if success_message:
        st.success(success_message)
    _render_selected_patient_detail(selected_id)


def _render_patient_delete_confirmation(patient_id, patient):
    delete_name = _patient_full_name(patient) or "Unnamed patient"
    with st.container(border=True, key="patient-delete-confirmation"):
        st.warning(
            f"Delete the complete local patient record for **{delete_name}** "
            f"(Patient ID {patient.get('patient_case_number') or 'not assigned'})? "
            "This cannot be undone."
        )
        cancel_column, confirm_column = st.columns(2)
        with cancel_column:
            if st.button(
                "Cancel",
                key=f"cancel_patient_delete_{patient_id}",
                width="stretch",
            ):
                st.session_state.pop("manage_delete_patient_id", None)
                st.rerun()
        with confirm_column:
            if st.button(
                "Yes, Permanently Delete",
                type="primary",
                key=f"confirm_patient_delete_{patient_id}",
                width="stretch",
            ):
                try:
                    conn = get_local_connection()
                except Exception as error:
                    st.error(f"Unable to open the local patient archive: {error}")
                    return
                try:
                    with conn:
                        conn.execute(
                            "DELETE FROM patient_return_sessions "
                            "WHERE patient_id = ?",
                            (patient_id,),
                        )
                        result = conn.execute(
                            "DELETE FROM patients WHERE patient_id = ?",
                            (patient_id,),
                        )
                        if result.rowcount != 1:
                            raise RuntimeError(
                                "The patient record was not deleted; it may "
                                "have already been removed."
                            )
                        conn.execute(
                            "INSERT INTO admin_logs (action_type, details) "
                            "VALUES (?, ?)",
                            (
                                "PATIENT RECORD DELETED",
                                f"Deleted patient record for {delete_name} "
                                f"(record {patient_id}).",
                            ),
                        )
                except Exception as error:
                    st.error(f"Unable to delete the patient record: {error}")
                else:
                    st.session_state.pop("manage_delete_patient_id", None)
                    st.session_state.pop("manage_edit_patient_id", None)
                    st.session_state.pop("manage_selected_patient_id", None)
                    st.session_state.pop(
                        "manage_return_session_patient_id",
                        None,
                    )
                    st.session_state.pop(
                        "manage_edit_return_session_id",
                        None,
                    )
                    st.session_state.pop(
                        "manage_delete_return_session_id",
                        None,
                    )
                    st.session_state.pop("record_results_table", None)
                    st.session_state["manage_success_message"] = (
                        "The patient record was permanently deleted."
                    )
                    st.rerun()
                finally:
                    conn.close()


def _render_patient_editor(target_id, p):
    with st.container(border=True, key=f"patient-editor-{target_id}"):
        st.subheader(f"Edit Patient Record · {p['first_name']} {p['last_name']}")

        with st.container(
            border=True,
            key=f"edit-intake-section-administration-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['administration']}")
            st.text_input(
                FIELD_LABELS["patient_case_number"],
                value=p.get("patient_case_number") or "",
                disabled=True,
                key=f"edit_{target_id}_patient_case_number",
            )
            st.text_input(
                FIELD_LABELS["date_registered"],
                value=format_date_for_display(p.get("date_registered")),
                disabled=True,
                key=f"edit_{target_id}_date_registered_display",
            )
            status_value = p.get("status") or ADMINISTRATIVE_STATUS_OPTIONS[0]
            status_options = list(ADMINISTRATIVE_STATUS_OPTIONS)
            if status_value not in status_options:
                status_options.append(status_value)
            adm_status = st.selectbox(
                FIELD_LABELS["status"],
                status_options,
                index=status_options.index(status_value),
                key=f"edit_{target_id}_status",
            )

        referral_date_value = parse_stored_date(p.get("date_of_referral"))
        interview_date_value = parse_stored_date(p.get("interview_date"))
        birth_date_value = parse_stored_date(p.get("date_of_birth"))
        if (
            isinstance(birth_date_value, datetime.date)
            and not datetime.date(1900, 1, 1)
            <= birth_date_value
            <= datetime.date.today()
        ):
            birth_date_value = str(p.get("date_of_birth") or "")
        if any(
            isinstance(value, str)
            for value in (
                referral_date_value,
                interview_date_value,
                birth_date_value,
            )
        ):
            st.warning(
                "A stored date is not in a recognized format. Select a valid "
                "date to replace it; unchanged values will be preserved."
            )

        with st.container(
            border=True,
            key=f"edit-intake-section-referral-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['referral']}")
            referral_left, referral_right = st.columns(2)
            with referral_left:
                noted_by_value = p.get("referral_noted_by") or ""
                noted_by_options = _information_noted_by_options(noted_by_value)
                ref_by = st.selectbox(
                    FIELD_LABELS["referral_noted_by"],
                    noted_by_options,
                    index=(
                        noted_by_options.index(noted_by_value)
                        if noted_by_value
                        else None
                    ),
                    accept_new_options=True,
                    key=f"edit_{target_id}_referral_noted_by_select",
                )
                referring_person = st.text_input(
                    FIELD_LABELS["referring_person_or_instance"],
                    value=p.get("referring_person_or_instance") or "",
                    key=f"edit_{target_id}_referring_person",
                )
                date_of_referral = st.date_input(
                    FIELD_LABELS["date_of_referral"],
                    value=(
                        referral_date_value
                        if isinstance(referral_date_value, datetime.date)
                        else None
                    ),
                    format=DATE_DISPLAY_FORMAT,
                    key=f"edit_{target_id}_date_of_referral_input",
                )
            with referral_right:
                means_ref = st.text_input(
                    FIELD_LABELS["means_of_referral"],
                    value=p.get("means_of_referral") or "",
                    key=f"edit_{target_id}_means_of_referral",
                )
                referral_request = st.text_area(
                    FIELD_LABELS["referral_request"],
                    value=p.get("referral_request") or "",
                    key=f"edit_{target_id}_referral_request",
                )
            agreements = st.text_area(
                FIELD_LABELS["agreements_made_for_further_interviewing"],
                value=p.get("agreements_made_for_further_interviewing") or "",
                key=f"edit_{target_id}_agreements",
            )

        with st.container(
            border=True,
            key=f"edit-intake-section-interview-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['interview']}")
            interview_left, interview_right = st.columns(2)
            with interview_left:
                int_date = st.date_input(
                    FIELD_LABELS["interview_date"],
                    value=(
                        interview_date_value
                        if isinstance(interview_date_value, datetime.date)
                        else None
                    ),
                    format=DATE_DISPLAY_FORMAT,
                    key=f"edit_{target_id}_interview_date_input",
                )
                int_place = st.text_input(
                    FIELD_LABELS["interview_place"],
                    value=p.get("interview_place") or "",
                    key=f"edit_{target_id}_interview_place",
                )
            with interview_right:
                int_present = st.text_area(
                    FIELD_LABELS["interview_persons_present"],
                    value=p.get("interview_persons_present") or "",
                    key=f"edit_{target_id}_interview_persons_present",
                )
                primary_src = st.text_input(
                    FIELD_LABELS["primary_source_of_information"],
                    value=p.get("primary_source_of_information") or "",
                    validate=PERSON_NAME_INPUT_VALIDATION,
                    key=f"edit_{target_id}_primary_source",
                )

        with st.container(
            border=True,
            key=f"edit-intake-section-identifying-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['identifying']}")
            st.markdown(f"##### {SECTION_TITLES['client']}")
            st.markdown(f"**{FIELD_LABELS['client_name']}**")
            name_columns = st.columns(4)
            with name_columns[0]:
                f_name = st.text_input(
                    "First Name",
                    value=p.get("first_name") or "",
                    validate=PERSON_NAME_INPUT_VALIDATION,
                    key=f"edit_{target_id}_first_name",
                )
            with name_columns[1]:
                m_name = st.text_input(
                    "Middle Name",
                    value=p.get("middle_name") or "",
                    validate=PERSON_NAME_INPUT_VALIDATION,
                    key=f"edit_{target_id}_middle_name",
                )
            with name_columns[2]:
                l_name = st.text_input(
                    "Last Name",
                    value=p.get("last_name") or "",
                    validate=PERSON_NAME_INPUT_VALIDATION,
                    key=f"edit_{target_id}_last_name",
                )
            with name_columns[3]:
                ext_name = st.text_input(
                    "Extension Name",
                    value=p.get("extension_name") or "",
                    validate=PERSON_NAME_INPUT_VALIDATION,
                    key=f"edit_{target_id}_extension_name",
                )

            dob = _render_birth_date(
                lambda field: f"edit_{target_id}_{field}",
                initial_date=(
                    birth_date_value
                    if isinstance(birth_date_value, datetime.date)
                    else None
                ),
            )
            calculated_age = _calculate_age(dob)
            if calculated_age is None and isinstance(birth_date_value, str):
                calculated_age = p.get("calculated_age")
            age_is_valid = _is_valid_nonnegative_number(
                calculated_age,
                integer=True,
                max_value=120,
            )
            age_display_key = f"edit_{target_id}_calculated_age_numeric"
            st.session_state[age_display_key] = (
                int(float(calculated_age))
                if age_is_valid and calculated_age is not None
                else None
            )
            st.number_input(
                FIELD_LABELS["age"],
                min_value=0,
                max_value=120,
                step=1,
                disabled=True,
                key=age_display_key,
            )
            if not age_is_valid:
                st.error("Age must be a whole number from 0 to 120.")
            dob_str = (
                dob.isoformat()
                if dob
                else (
                    p.get("date_of_birth")
                    if isinstance(birth_date_value, str)
                    else None
                )
            )
            calc_age = calculated_age if calculated_age is not None else 0

            st.markdown(f"**{FIELD_LABELS['address']}**")
            address_left, address_right = st.columns(2)
            with address_left:
                street = st.text_input(
                    "Street / House Number",
                    value=p.get("street_address") or "",
                    key=f"edit_{target_id}_street_address",
                )
                brgy = st.text_input(
                    "Barangay",
                    value=p.get("barangay") or "",
                    key=f"edit_{target_id}_barangay",
                )
                prov = st.text_input(
                    "Province",
                    value=p.get("province") or "",
                    key=f"edit_{target_id}_province",
                )
            with address_right:
                purok = st.text_input(
                    "Purok",
                    value=p.get("purok") or "",
                    key=f"edit_{target_id}_purok",
                )
                city = st.text_input(
                    "City / Municipality",
                    value=p.get("city_municipality") or "",
                    key=f"edit_{target_id}_city",
                )
            sex_value = p.get("sex") or ""
            sex_options = list(SEX_OPTIONS)
            if sex_value and sex_value not in sex_options:
                sex_options.append(sex_value)
            sex = st.selectbox(
                FIELD_LABELS["sex"],
                sex_options,
                index=sex_options.index(sex_value) if sex_value else None,
                key=f"edit_{target_id}_sex_v2",
            )
            civil_status_value = p.get("civil_status") or ""
            civil_status_options = list(CIVIL_STATUS_OPTIONS)
            if (
                civil_status_value
                and civil_status_value not in civil_status_options
            ):
                civil_status_options.append(civil_status_value)
            civ_status = st.selectbox(
                FIELD_LABELS["civil_status"],
                civil_status_options,
                index=civil_status_options.index(civil_status_value),
                key=f"edit_{target_id}_civil_status",
            )
            religion = st.text_input(
                FIELD_LABELS["religion"],
                value=p.get("religion") or "",
                key=f"edit_{target_id}_religion",
            )
            edu_value = p.get("educational_attainment") or ""
            edu_options = list(EDUCATIONAL_ATTAINMENT_OPTIONS)
            if edu_value and edu_value not in edu_options:
                edu_options.append(edu_value)
            edu = st.selectbox(
                FIELD_LABELS["educational_attainment"],
                edu_options,
                index=edu_options.index(edu_value) if edu_value else None,
                accept_new_options=True,
                key=f"edit_{target_id}_educational_attainment_select",
            )
            work_exp = st.text_area(
                FIELD_LABELS["work_experience"],
                value=p.get("work_experience") or "",
                key=f"edit_{target_id}_work_experience",
            )

        with st.container(
            border=True,
            key=f"edit-intake-section-relatives-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['relatives']}")
            guardian_name = _patient_full_name(
                {
                    "first_name": p.get("guardian_first_name"),
                    "middle_name": p.get("guardian_middle_name"),
                    "last_name": p.get("guardian_last_name"),
                }
            )
            g_first = st.text_input(
                "Name",
                value=guardian_name,
                validate=PERSON_NAME_INPUT_VALIDATION,
                key=f"edit_{target_id}_guardian_name",
            )
            g_mid = ""
            g_last = ""
            st.markdown(f"**{FIELD_LABELS['address']}**")
            guardian_address_left, guardian_address_right = st.columns(2)
            with guardian_address_left:
                g_street = st.text_input(
                    "Street / Zone",
                    value=p.get("guardian_street_address") or "",
                    key=f"edit_{target_id}_guardian_street_address",
                )
                g_brgy = st.text_input(
                    "Barangay",
                    value=p.get("g_barangay") or "",
                    key=f"edit_{target_id}_guardian_barangay",
                )
                g_prov = st.text_input(
                    "Province",
                    value=p.get("g_province") or "",
                    key=f"edit_{target_id}_guardian_province",
                )
            with guardian_address_right:
                g_city = st.text_input(
                    "City / Municipality",
                    value=p.get("g_city") or "",
                    key=f"edit_{target_id}_guardian_city",
                )
                g_contact = st.text_input(
                    FIELD_LABELS["contact_person"],
                    value=p.get("guardian_contact_person") or "",
                    placeholder=(
                        "Same as Nearest Relative (or enter alternate contact)"
                    ),
                    validate=PERSON_NAME_INPUT_VALIDATION,
                    key=f"edit_{target_id}_guardian_contact_person",
                )
            g_contact_number = st.text_input(
                FIELD_LABELS["contact_number"],
                value=p.get("g_contact_number") or "",
                max_chars=11,
                type="phone",
                placeholder="09XXXXXXXXX",
                validate=CONTACT_NUMBER_INPUT_VALIDATION,
                key=f"edit_{target_id}_guardian_contact_number",
            )

        with st.container(
            border=True,
            key=f"edit-intake-section-family-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['family']}")
            family_table = dataframe_from_storage(
                p.get("family_composition"),
                FAMILY_COLUMNS,
            )
            edited_family_table = st.data_editor(
                family_table,
                num_rows="dynamic",
                width="stretch",
                key=f"family_table_{target_id}",
                column_config=family_column_config(family_table),
                alt="Family composition of the patient",
            )

        with st.container(
            border=True,
            key=f"edit-intake-section-classification-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['classification']}")
            household_member_count = p.get("household_member_count")
            if household_member_count is not None:
                household_member_count = int(household_member_count)
            classification_left, classification_right = st.columns(2)
            with classification_left:
                household_member_count = st.number_input(
                    FIELD_LABELS["household_member_count"],
                    min_value=0,
                    step=1,
                    value=household_member_count,
                    key=f"edit_{target_id}_household_member_count",
                )
                ann_inc = st.number_input(
                    FIELD_LABELS["total_annual_income"],
                    min_value=0.0,
                    step=500.0,
                    format="%.2f",
                    value=float(p.get("total_annual_income") or 0.0),
                    key=f"edit_{target_id}_total_annual_income",
                )
                pov_thresh = st.number_input(
                    FIELD_LABELS["poverty_threshold_per_year"],
                    min_value=0.0,
                    step=500.0,
                    format="%.2f",
                    value=float(p.get("poverty_threshold_per_year") or 0.0),
                    key=f"edit_{target_id}_poverty_threshold",
                )
            with classification_right:
                pov_rate = st.text_input(
                    FIELD_LABELS["poverty_rating"],
                    value=p.get("poverty_rating") or "",
                    key=f"edit_{target_id}_poverty_rating",
                )
                class_int = st.text_input(
                    FIELD_LABELS["classification_after_interview"],
                    value=p.get("classification_after_interview") or "",
                    key=f"edit_{target_id}_classification_after_interview",
                )
                class_visit = st.text_input(
                    FIELD_LABELS["classification_after_home_visit"],
                    value=p.get("classification_after_home_visit") or "",
                    key=f"edit_{target_id}_classification_after_home_visit",
                )

        with st.container(
            border=True,
            key=f"edit-intake-section-complaint-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['complaint']}")
            cc_pat = st.text_area(
                FIELD_LABELS["chief_complaint_patient"],
                value=p.get("chief_complaint_patient") or "",
                key=f"edit_{target_id}_chief_complaint_patient",
            )
            cc_rel = st.text_area(
                FIELD_LABELS["chief_complaint_relatives"],
                value=p.get("chief_complaint_relatives") or "",
                key=f"edit_{target_id}_chief_complaint_relatives",
            )
            complaint_left, complaint_right = st.columns(2)
            with complaint_left:
                c_dur = st.text_input(
                    FIELD_LABELS["complaint_duration"],
                    value=p.get("complaint_duration") or "",
                    key=f"edit_{target_id}_complaint_duration",
                )
                c_onset = st.text_input(
                    FIELD_LABELS["complaint_onset"],
                    value=p.get("complaint_onset") or "",
                    key=f"edit_{target_id}_complaint_onset",
                )
            with complaint_right:
                c_rec = st.text_input(
                    FIELD_LABELS["complaint_recent"],
                    value=p.get("complaint_recent") or "",
                    key=f"edit_{target_id}_complaint_recent",
                )
                c_hosp = st.text_input(
                    FIELD_LABELS["complaint_previous_hospitalization"],
                    value=p.get("complaint_previous_hospitalization") or "",
                    key=f"edit_{target_id}_complaint_previous_hospitalization",
                )

        with st.container(
            border=True,
            key=f"edit-intake-section-impression-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['impression']}")
            initial_imp = st.text_area(
                FIELD_LABELS["interviewers_initial_impression"],
                value=p.get("interviewers_initial_impression") or "",
                key=f"edit_{target_id}_interviewers_initial_impression",
                label_visibility="collapsed",
            )

        with st.container(
            border=True,
            key=f"edit-intake-section-history-of-illness-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['history_of_illness']}")
            hist_illness = st.text_area(
                FIELD_LABELS["history_of_illness"],
                value=p.get("history_of_illness") or "",
                key=f"edit_{target_id}_history_of_illness",
                label_visibility="collapsed",
            )

        with st.container(
            border=True,
            key=f"edit-intake-section-mental-status-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['mental_status_examination']}")
            mse_notes = st.text_area(
                FIELD_LABELS["mental_status_examination"],
                value=p.get("mental_status_examination") or "",
                key=f"edit_{target_id}_mental_status_examination",
                label_visibility="collapsed",
            )

        with st.container(
            border=True,
            key=f"edit-intake-section-nurses-observation-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['nurses_observation']}")
            nurse_obs = st.text_area(
                FIELD_LABELS["nurses_observation"],
                value=p.get("nurses_observation") or "",
                key=f"edit_{target_id}_nurses_observation",
                label_visibility="collapsed",
            )

        with st.container(
            border=True,
            key=f"edit-intake-section-diagnosis-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['diagnosis']}")
            diag_notes = st.text_area(
                FIELD_LABELS["diagnosis"],
                value=p.get("diagnosis") or "",
                key=f"edit_{target_id}_diagnosis",
                label_visibility="collapsed",
            )

        with st.container(
            border=True,
            key=f"edit-intake-section-treatment-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['treatment']}")
            treat_plan = st.text_area(
                FIELD_LABELS["treatment"],
                value=p.get("treatment") or "",
                key=f"edit_{target_id}_treatment",
                label_visibility="collapsed",
            )

        with st.container(
            border=True,
            key=f"edit-intake-section-medications-{target_id}",
        ):
            st.markdown(f"#### {SECTION_TITLES['medications']}")
            medication_table = dataframe_from_storage(
                p.get("parenteral_medication_records"),
                MEDICATION_COLUMNS,
            )
            edited_medication_table = st.data_editor(
                medication_table,
                num_rows="dynamic",
                width="stretch",
                key=f"medication_table_{target_id}",
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
                alt="Parenteral medication sheet",
            )

        if st.button(
            "Apply Data Modifications",
            type="primary",
            key=f"save_patient_changes_{target_id}",
        ):
            if not f_name.strip() or not l_name.strip():
                st.error("First name and last name are required to save this record.")
                return
            validation_errors = []
            validation_errors.extend(
                validate_person_names(
                    {
                        "First Name": f_name,
                        "Middle Name": m_name,
                        "Last Name": l_name,
                        "Extension Name": ext_name,
                        "Guardian Name": g_first,
                        "Contact Person": g_contact,
                        "Informant Name": primary_src,
                        "Worker Name": ref_by,
                    }
                )
            )
            if g_contact_number and not _is_valid_contact_number(g_contact_number):
                validation_errors.append(
                    "Contact Number must contain 11 digits starting with 09."
                )
            if not _is_valid_nonnegative_number(
                calc_age,
                integer=True,
                max_value=120,
            ):
                validation_errors.append(
                    "Age must be a whole number from 0 to 120."
                )
            if not _is_valid_nonnegative_number(
                household_member_count,
                integer=True,
            ):
                validation_errors.append(
                    "No. of Household Members must be a non-negative whole number."
                )
            if not _is_valid_nonnegative_number(ann_inc):
                validation_errors.append(
                    "Total annual income must be a valid non-negative amount."
                )
            if not _is_valid_nonnegative_number(pov_thresh):
                validation_errors.append(
                    "Poverty threshold/year must be a valid non-negative amount."
                )
            validation_errors.extend(
                validate_family_composition(edited_family_table)
            )
            if validation_errors:
                for validation_error in validation_errors:
                    st.error(validation_error)
                return
            try:
                conn = get_local_connection()
            except Exception as error:
                st.error(f"Unable to open the local patient archive: {error}")
                return
            try:
                with conn:
                    conn.execute(
                        """
                        UPDATE patients SET
                            referral_noted_by = ?, referring_person_or_instance = ?,
                            date_of_referral = ?, means_of_referral = ?,
                            referral_request = ?,
                            agreements_made_for_further_interviewing = ?,
                            interview_date = ?, interview_place = ?,
                            interview_persons_present = ?,
                            primary_source_of_information = ?,
                            first_name = ?, middle_name = ?, last_name = ?,
                            extension_name = ?, calculated_age = ?, sex = ?,
                            date_of_birth = ?, civil_status = ?, religion = ?,
                            educational_attainment = ?, status = ?,
                            work_experience = ?, street_address = ?, purok = ?,
                            barangay = ?, city_municipality = ?, province = ?,
                            guardian_last_name = ?, guardian_first_name = ?,
                            guardian_middle_name = ?, guardian_street_address = ?,
                            g_barangay = ?, g_city = ?, g_province = ?,
                            guardian_contact_person = ?, g_contact_number = ?,
                            family_composition = ?, household_member_count = ?,
                            total_annual_income = ?,
                            poverty_threshold_per_year = ?, poverty_rating = ?,
                            classification_after_interview = ?,
                            classification_after_home_visit = ?,
                            chief_complaint_patient = ?,
                            chief_complaint_relatives = ?,
                            complaint_duration = ?, complaint_recent = ?,
                            complaint_onset = ?,
                            complaint_previous_hospitalization = ?,
                            interviewers_initial_impression = ?,
                            history_of_illness = ?,
                            mental_status_examination = ?,
                            nurses_observation = ?, diagnosis = ?, treatment = ?,
                            parenteral_medication_records = ?
                        WHERE patient_id = ?
                        """,
                        (
                            ref_by,
                            referring_person,
                            (
                                date_of_referral.isoformat()
                                if date_of_referral
                                else (
                                    p.get("date_of_referral")
                                    if isinstance(referral_date_value, str)
                                    else None
                                )
                            ),
                            means_ref,
                            referral_request,
                            agreements,
                            (
                                int_date.isoformat()
                                if int_date
                                else (
                                    p.get("interview_date")
                                    if isinstance(interview_date_value, str)
                                    else None
                                )
                            ),
                            int_place,
                            int_present,
                            primary_src,
                            f_name,
                            m_name,
                            l_name,
                            ext_name,
                            int(float(calc_age)),
                            sex,
                            dob_str,
                            civ_status,
                            religion,
                            edu,
                            adm_status,
                            work_exp,
                            street,
                            purok,
                            brgy,
                            city,
                            prov,
                            g_last,
                            g_first,
                            g_mid,
                            g_street,
                            g_brgy,
                            g_city,
                            g_prov,
                            g_contact,
                            g_contact_number,
                            dataframe_to_storage(edited_family_table),
                            household_member_count,
                            float(ann_inc),
                            float(pov_thresh),
                            pov_rate,
                            class_int,
                            class_visit,
                            cc_pat,
                            cc_rel,
                            c_dur,
                            c_rec,
                            c_onset,
                            c_hosp,
                            initial_imp,
                            hist_illness,
                            mse_notes,
                            nurse_obs,
                            diag_notes,
                            treat_plan,
                            dataframe_to_storage(edited_medication_table),
                            target_id,
                        ),
                    )
                    conn.execute(
                        "INSERT INTO admin_logs (action_type, details) VALUES (?, ?)",
                        (
                            "PATIENT RECORD EDITED",
                            f"Edited patient record for {f_name} {l_name} "
                            f"(record {target_id}).",
                        ),
                    )
                st.session_state.pop("manage_edit_patient_id", None)
                st.session_state["manage_success_message"] = (
                    "Patient record updated successfully."
                )
                st.rerun()
            except Exception as error:
                st.error(f"Failed to complete transaction adjustments: {error}")
            finally:
                conn.close()


def _clear_patient_name_lookup():
    st.session_state["patient_name_lookup_query"] = ""


def show_manage_page():
    selected_id = st.session_state.get("manage_selected_patient_id")
    success_message = st.session_state.pop("manage_success_message", None)
    encode_success_toast = st.session_state.pop("encode_success_toast", None)
    if encode_success_toast:
        st.toast(encode_success_toast)
    search_notice = st.session_state.pop("manage_search_notice", None)
    if selected_id is not None:
        show_patient_detail_dialog(selected_id, success_message)
        return

    st.session_state.pop("manage_edit_patient_id", None)
    st.session_state.pop("manage_delete_patient_id", None)
    st.session_state.pop("manage_return_session_patient_id", None)
    st.session_state.pop("manage_edit_return_session_id", None)
    st.session_state.pop("manage_delete_return_session_id", None)
    with st.container(key="admin-search-page"):
        st.markdown(
            '<div class="search-eyebrow">Patient Records</div>',
            unsafe_allow_html=True,
        )
        st.markdown("# Search Records")
        st.write(
            "Search by Patient ID or use the restricted name lookup to review "
            "and manage records."
        )
        if success_message:
            st.success(success_message)
        if search_notice:
            st.info(search_notice)
        search_controls_placeholder = st.empty()

    try:
        conn = get_local_connection()
    except Exception as error:
        st.error(f"Unable to open the local patient archive: {error}")
        return
    try:
        all_records = conn.execute(
            """
            SELECT patient_id, patient_case_number, first_name, middle_name,
                   last_name, extension_name, calculated_age, sex,
                   city_municipality, province, barangay
            FROM patients
            ORDER BY patient_case_number COLLATE NOCASE, patient_id
            """
        ).fetchall()
    except Exception as error:
        st.error(f"Unable to read local patient records: {error}")
        return
    finally:
        conn.close()

    record_dicts = [dict(record) for record in all_records]
    try:
        address_hierarchy = _load_bicol_address_hierarchy()
    except Exception as error:
        st.error(f"Unable to load the Bicol geographic filters: {error}")
        return
    genders = sorted(
        {record["sex"].strip() for record in record_dicts if record["sex"] and record["sex"].strip()},
        key=str.casefold,
    )

    province_names = list(address_hierarchy)
    selected_province = st.session_state.get("record_filter_province")
    if selected_province not in province_names:
        st.session_state.pop("record_filter_province", None)
        _clear_record_city_and_barangay()
        selected_province = None

    province_record = address_hierarchy.get(selected_province)
    municipality_options = (
        [municipality["name"] for municipality in province_record["municipalities"]]
        if province_record
        else []
    )
    selected_city = st.session_state.get("record_filter_city")
    if selected_city not in municipality_options:
        st.session_state.pop("record_filter_city", None)
        _clear_record_barangay()
        selected_city = None

    municipality_record = next(
        (
            municipality
            for municipality in province_record["municipalities"]
            if municipality["name"] == selected_city
        ),
        None,
    ) if province_record and selected_city else None
    barangay_options = (
        [barangay["name"] for barangay in municipality_record["barangays"]]
        if municipality_record
        else []
    )
    if st.session_state.get("record_filter_barangay") not in barangay_options:
        st.session_state.pop("record_filter_barangay", None)

    with search_controls_placeholder.container():
        st.markdown("**Restricted Name Lookup**")
        name_lookup_column, filter_button_column = st.columns(
            [0.88, 0.12],
            gap="small",
            vertical_alignment="center",
        )
        st.session_state.setdefault("patient_name_lookup_query", "")
        st.session_state.pop("patient_name_lookup_visible", None)
        with name_lookup_column:
            with st.container(
                horizontal=True,
                wrap=False,
                vertical_alignment="center",
                gap="small",
                key="record-name-lookup-controls",
            ):
                with st.container(key="record-name-lookup", width="stretch"):
                    name_search_term = st.text_input(
                        "Restricted Name Lookup",
                        key="patient_name_lookup_query",
                        placeholder="Enter a patient name",
                        type="password",
                        autocomplete="off",
                        label_visibility="collapsed",
                        width="stretch",
                    ).strip()
                st.button(
                    "✕",
                    help="Clear search",
                    key="patient-name-lookup-clear",
                    type="tertiary",
                    disabled=not st.session_state["patient_name_lookup_query"],
                    width="content",
                    on_click=_clear_patient_name_lookup,
                )
        with filter_button_column:
            with st.popover(
                "",
                icon=":material/filter_alt:",
                help="Filter records",
                key="record_filters_popover",
                width="stretch",
            ):
                province_column, city_column, barangay_column, gender_column = (
                    st.columns(4)
                )
                with province_column:
                    selected_province = st.selectbox(
                        "Province",
                        province_names,
                        index=None,
                        placeholder="Choose a Bicol province",
                        key="record_filter_province",
                        on_change=_clear_record_city_and_barangay,
                    )
                with city_column:
                    selected_city = st.selectbox(
                        "Municipality / City",
                        municipality_options,
                        index=None,
                        placeholder=(
                            "Choose a province first"
                            if selected_province is None
                            else "Choose a municipality or city"
                        ),
                        disabled=selected_province is None,
                        key="record_filter_city",
                        on_change=_clear_record_barangay,
                    )
                with barangay_column:
                    selected_barangay = st.selectbox(
                        "Barangay",
                        barangay_options,
                        index=None,
                        placeholder=(
                            "Choose a municipality or city first"
                            if selected_city is None
                            else "Choose a barangay"
                        ),
                        disabled=selected_city is None,
                        key="record_filter_barangay",
                    )
                with gender_column:
                    selected_gender = st.selectbox(
                        "Gender",
                        ["All genders", *genders],
                        key="record_filter_gender",
                    )

                minimum_age_column, maximum_age_column = st.columns(2)
                with minimum_age_column:
                    minimum_age = st.number_input(
                        "Minimum age",
                        min_value=0,
                        max_value=120,
                        value=0,
                        key="record_filter_minimum_age",
                    )
                with maximum_age_column:
                    maximum_age = st.number_input(
                        "Maximum age",
                        min_value=0,
                        max_value=120,
                        value=120,
                        key="record_filter_maximum_age",
                    )

        st.markdown("**Patient ID**")
        st.session_state.setdefault(
            "patient_case_search_year",
            str(datetime.date.today().year),
        )
        with st.container(
            horizontal=True,
            wrap=False,
            vertical_alignment="center",
            gap="xsmall",
            key="patient-case-search-code",
        ):
            st.markdown("**BOC-**", width="content")
            patient_year = st.text_input(
                "Year",
                key="patient_case_search_year",
                max_chars=4,
                placeholder="YYYY",
                label_visibility="collapsed",
                width=68,
            ).strip()
            st.markdown("**-**", width="content")
            patient_number = st.text_input(
                "Unique number",
                key="patient_case_search_number",
                max_chars=4,
                placeholder="0001",
                label_visibility="collapsed",
                width=68,
            ).strip()

    case_number_search_term = ""
    if _is_four_digit_value(patient_year) and _is_four_digit_value(
        patient_number
    ):
        case_number_search_term = f"BOC-{patient_year}-{patient_number}"
    elif patient_number:
        st.caption(
            "Enter a four-digit year and unique number to search by Patient ID."
        )

    if minimum_age > maximum_age:
        st.error("Minimum age cannot be greater than maximum age.")
        return

    filtered_records = []
    for record in record_dicts:
        if case_number_search_term and not _matches_patient_case_number(
            record,
            case_number_search_term,
        ):
            continue
        if name_search_term and (
            name_search_term.casefold()
            not in _patient_full_name(record).casefold()
        ):
            continue
        if selected_province is not None and (
            _location_key(record["province"]) != _location_key(selected_province)
        ):
            continue
        if selected_city is not None and (
            _location_key(record["city_municipality"])
            != _location_key(selected_city)
        ):
            continue
        if selected_barangay is not None and (
            _location_key(record["barangay"]) != _location_key(selected_barangay)
        ):
            continue
        if selected_gender != "All genders" and (
            (record["sex"] or "").casefold() != selected_gender.casefold()
        ):
            continue
        if minimum_age > 0 or maximum_age < 120:
            try:
                age = int(record["calculated_age"])
            except (TypeError, ValueError):
                continue
            if not minimum_age <= age <= maximum_age:
                continue
        filtered_records.append(record)

    filters_applied = bool(
        case_number_search_term
        or name_search_term
        or selected_province is not None
        or selected_city is not None
        or selected_barangay is not None
        or selected_gender != "All genders"
        or minimum_age > 0
        or maximum_age < 120
    )
    with st.container(key="admin-search-results"):
        if not record_dicts:
            st.info("There are no patient records in the local archive yet.")
        elif not filtered_records:
            st.info("No patient records match the search and selected filters.")
        _render_patient_results(filtered_records, filters_applied)
    if st.session_state.get("show_encode_dialog"):
        show_encode_dialog()

if __name__ == "__main__":
    show_manage_page()
