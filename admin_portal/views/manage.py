import datetime
import html
import json
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st
from database import get_local_connection
from views.encode import show_encode_dialog
from views.record_tables import (
    FAMILY_COLUMNS,
    MEDICATION_COLUMNS,
    dataframe_from_storage,
    dataframe_to_storage,
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


PATIENT_DETAIL_SECTIONS = (
    (
        "Registration and Interview",
        (
            "referral_noted_by",
            "means_of_referral",
            "interview_date",
            "interview_place",
            "interview_persons_present",
            "primary_source_of_information",
        ),
    ),
    (
        "Patient Profile",
        (
            "first_name",
            "middle_name",
            "last_name",
            "extension_name",
            "date_of_birth",
            "calculated_age",
            "sex",
            "civil_status",
            "religion",
            "educational_attainment",
            "status",
            "work_experience",
        ),
    ),
    (
        "Residential Address",
        (
            "street_address",
            "purok",
            "barangay",
            "city_municipality",
            "province",
        ),
    ),
    (
        "Guardian and Nearest Relative",
        (
            "guardian_first_name",
            "guardian_middle_name",
            "guardian_last_name",
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
        ),
    ),
    (
        "Household and Socioeconomic Information",
        (
            "family_composition",
            "total_annual_income",
            "poverty_threshold_per_year",
            "poverty_rating",
            "classification_after_interview",
            "classification_after_home_visit",
        ),
    ),
    (
        "Complaints and History",
        (
            "chief_complaint_patient",
            "chief_complaint_relatives",
            "complaint_duration",
            "complaint_recent",
            "complaint_onset",
            "complaint_previous_hospitalization",
        ),
    ),
    (
        "Clinical Notes and Treatment",
        (
            "interviewers_initial_impression",
            "history_of_illness",
            "mental_status_examination",
            "nurses_observation",
            "diagnosis",
            "treatment",
            "parenteral_medication_records",
        ),
    ),
)


def _detail_label(field_name):
    return field_name.replace("_", " ").strip().title()


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


def _render_patient_details(patient):
    patient_field_order = list(patient.keys())
    patient_fields = set(patient_field_order)
    displayed_fields = {
        "patient_id",
        "patient_case_number",
        "date_registered",
    }

    for section_title, field_names in PATIENT_DETAIL_SECTIONS:
        fields = [field for field in field_names if field in patient_fields]
        if not fields:
            continue
        displayed_fields.update(fields)
        with st.container(border=True):
            st.markdown(f"#### {section_title}")
            value_columns = st.columns(2)
            for index, field in enumerate(fields):
                value = patient[field]
                with value_columns[index % 2]:
                    _render_patient_detail_label(_detail_label(field))
                    if field == "family_composition":
                        st.dataframe(
                            dataframe_from_storage(value, FAMILY_COLUMNS),
                            hide_index=True,
                            width="stretch",
                        )
                    elif field == "parenteral_medication_records":
                        st.dataframe(
                            dataframe_from_storage(value, MEDICATION_COLUMNS),
                            hide_index=True,
                            width="stretch",
                        )
                    else:
                        _render_patient_detail_value(value)

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
            st.session_state["show_encode_dialog"] = True

    with st.container(key="patient-results-table-hint"):
        st.caption("Click View on any patient row to open their full record.")

    column_widths = [1.2, 2.2, 0.9, 0.6, 0.75]
    headers = ("Patient ID", "Address", "Gender", "Age", "Action")
    with st.container(border=True, key="patient-results-table"):
        with st.container(key="patient-results-table-header"):
            header_columns = st.columns(
                column_widths, vertical_alignment="center"
            )
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
                row_columns = st.columns(
                    column_widths, vertical_alignment="center"
                )
                with row_columns[0]:
                    st.write(record.get("patient_case_number") or "Not assigned")
                with row_columns[1]:
                    st.write(address)
                with row_columns[2]:
                    st.write(record.get("sex") or "—")
                with row_columns[3]:
                    st.write(age)
                with row_columns[4]:
                    if st.button(
                        "👁 View",
                        key=f"view_patient_record_{index}",
                        type="secondary",
                        help="Open the full patient record",
                        width="stretch",
                    ):
                        st.session_state["manage_selected_patient_id"] = record[
                            "patient_id"
                        ]
                        st.session_state.pop("manage_edit_patient_id", None)
                        st.session_state.pop("manage_delete_patient_id", None)
                        st.session_state.pop(
                            "manage_return_session_patient_id", None
                        )
                        st.session_state.pop(
                            "manage_edit_return_session_id", None
                        )
                        st.session_state.pop(
                            "manage_delete_return_session_id", None
                        )
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
    editing = st.session_state.get("manage_edit_patient_id") == selected_id
    logging_return_session = (
        st.session_state.get("manage_return_session_patient_id") == selected_id
    )
    with st.container(key="selected-patient-details"):
        case_column, edit_column, delete_column = st.columns(
            [8, 0.45, 0.45],
            vertical_alignment="center",
            gap="small",
        )
        with case_column:
            st.caption("Patient ID / Case Number")
            st.title(case_number)
        if not logging_return_session:
            with edit_column:
                if st.button(
                    "",
                    key=f"toggle_patient_edit_{selected_id}",
                    icon=(
                        ":material/edit:"
                        if not editing
                        else ":material/close:"
                    ),
                    help="Edit record" if not editing else "Cancel editing",
                    width="content",
                ):
                    if editing:
                        st.session_state.pop("manage_edit_patient_id", None)
                    else:
                        st.session_state["manage_edit_patient_id"] = selected_id
                    st.session_state.pop("manage_delete_patient_id", None)
                    st.session_state.pop("manage_edit_return_session_id", None)
                    st.session_state.pop("manage_delete_return_session_id", None)
                    st.rerun()
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
            if st.button(
                "Back to Patient Details",
                key=f"return-session-back-{selected_id}",
            ):
                st.session_state.pop("manage_return_session_patient_id", None)
                st.rerun()
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
            elif editing:
                _render_patient_editor(selected_id, patient)
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


def _close_patient_detail_dialog():
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
            "noted-by",
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
        session_date_value = datetime.date.fromisoformat(
            str(session["Session date"])
        )
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
            information_noted_by = st.text_input(
                "Information Noted By",
                value=session["Information Noted By"] or "",
                key=f"{prefix}-noted-by",
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
                column: st.column_config.DateColumn(
                    column,
                    format="YYYY-MM-DD",
                )
                for column in MEDICATION_COLUMNS[::2]
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
            information_noted_by = st.text_input(
                "Information Noted By",
                key=f"return-session-noted-by-{patient_id}",
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
                column: st.column_config.DateColumn(
                    column,
                    format="YYYY-MM-DD",
                )
                for column in MEDICATION_COLUMNS[::2]
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
            alt="Parenteral medication entries for this return session",
        )
    _render_return_session_value(
        "Notes / Remarks", session["Notes / remarks"]
    )


def _format_return_session_date(value: str | None) -> str:
    try:
        return datetime.date.fromisoformat(str(value)).strftime("%B %d, %Y")
    except (TypeError, ValueError):
        return str(value or "—")


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
        st.write(
            "Expand the panels below to edit the corresponding patient record sections."
        )

        with st.expander("Referral Context & Interview Logistics"):
            ref_by = st.text_input(
                "Information Noted By", value=p["referral_noted_by"] or ""
            )
            means_ref = st.text_input(
                "Means of Referral", value=p["means_of_referral"] or ""
            )
            int_date = st.text_input(
                "Date of Interview (YYYY-MM-DD)", value=p["interview_date"] or ""
            )
            int_place = st.text_input(
                "Place of Interview", value=p["interview_place"] or ""
            )
            int_present = st.text_area(
                "Persons Present During Interview",
                value=p["interview_persons_present"] or "",
            )
            primary_src = st.text_input(
                "Primary Source of Information",
                value=p["primary_source_of_information"] or "",
            )

        with st.expander(
            "Core Patient Identifying Profile",
            expanded=True,
        ):
            c_n1, c_n2, c_n3 = st.columns(3)
            with c_n1:
                f_name = st.text_input("First Name", value=p["first_name"])
            with c_n2:
                m_name = st.text_input(
                    "Middle Name", value=p["middle_name"] or ""
                )
            with c_n3:
                l_name = st.text_input("Last Name", value=p["last_name"])
            ext_name = st.text_input(
                "Suffix / Extension Name", value=p["extension_name"] or ""
            )

            c_d1, c_d2 = st.columns(2)
            with c_d1:
                calc_age = st.number_input(
                    "Calculated Age",
                    min_value=0,
                    step=1,
                    value=int(p["calculated_age"] or 0),
                )
            with c_d2:
                sex_options = ["", "Male", "Female"]
                sex = st.selectbox(
                    "Sex",
                    sex_options,
                    index=sex_options.index(p["sex"])
                    if p["sex"] in sex_options
                    else 0,
                )

            dob_str = st.text_input(
                "Date of Birth (YYYY-MM-DD)", value=p["date_of_birth"] or ""
            )
            civ_status = st.text_input(
                "Civil Status", value=p["civil_status"] or ""
            )
            religion = st.text_input("Religion", value=p["religion"] or "")
            edu = st.text_input(
                "Educational Attainment",
                value=p["educational_attainment"] or "",
            )
            status_options = ["Alive", "Deceased"]
            adm_status = st.selectbox(
                "Current Administrative Status",
                status_options,
                index=status_options.index(p["status"])
                if p["status"] in status_options
                else 0,
            )
            work_exp = st.text_area(
                "Work Experience", value=p["work_experience"] or ""
            )

        with st.expander("Residential Address Demographics"):
            street = st.text_input(
                "Street / House Number", value=p["street_address"] or ""
            )
            purok = st.text_input("Purok", value=p["purok"] or "")
            brgy = st.text_input("Barangay", value=p["barangay"] or "")
            city = st.text_input(
                "City / Municipality", value=p["city_municipality"] or ""
            )
            prov = st.text_input("Province", value=p["province"] or "")

        with st.expander("Nearest Relatives / Guardian Profiles"):
            g_first = st.text_input(
                "Guardian First Name", value=p["guardian_first_name"] or ""
            )
            g_mid = st.text_input(
                "Guardian Middle Name", value=p["guardian_middle_name"] or ""
            )
            g_last = st.text_input(
                "Guardian Last Name", value=p["guardian_last_name"] or ""
            )
            g_street = st.text_input(
                "Guardian Street Address",
                value=p["guardian_street_address"] or "",
            )
            g_brgy = st.text_input(
                "Guardian Barangay", value=p["g_barangay"] or ""
            )
            g_city = st.text_input(
                "Guardian City/Municipality", value=p["g_city"] or ""
            )
            g_prov = st.text_input(
                "Guardian Province", value=p["g_province"] or ""
            )
            g_contact = st.text_input(
                "Guardian Contact Person Name",
                value=p["guardian_contact_person"] or "",
            )
            g_contact_number = st.text_input(
                "Guardian Contact Number",
                value=p["g_contact_number"] or "",
            )

        with st.expander("Household & Socio-Economic Classifications"):
            family_table = dataframe_from_storage(
                p["family_composition"],
                FAMILY_COLUMNS,
            )
            edited_family_table = st.data_editor(
                family_table,
                num_rows="dynamic",
                width="stretch",
                key=f"family_table_{target_id}",
            )
            ann_inc = st.number_input(
                "Total Annual Income (PHP)",
                min_value=0.0,
                step=500.0,
                value=float(p["total_annual_income"] or 0.0),
            )
            pov_thresh = st.number_input(
                "Poverty Threshold Per Year (PHP)",
                min_value=0.0,
                step=500.0,
                value=float(p["poverty_threshold_per_year"] or 0.0),
            )
            pov_rate = st.text_input(
                "Poverty Rating", value=p["poverty_rating"] or ""
            )
            class_int = st.text_input(
                "Classification After Interview",
                value=p["classification_after_interview"] or "",
            )
            class_visit = st.text_input(
                "Classification After Home Visit",
                value=p["classification_after_home_visit"] or "",
            )

        with st.expander("Chief Complaint Metrics & Onset"):
            cc_pat = st.text_area(
                "Chief Complaint (Patient)",
                value=p["chief_complaint_patient"] or "",
            )
            cc_rel = st.text_area(
                "Chief Complaint (Relatives)",
                value=p["chief_complaint_relatives"] or "",
            )
            c_dur = st.text_input(
                "Complaint Duration", value=p["complaint_duration"] or ""
            )
            c_rec = st.text_input(
                "Recent Manifestations", value=p["complaint_recent"] or ""
            )
            c_onset = st.text_input(
                "Complaint Onset", value=p["complaint_onset"] or ""
            )
            c_hosp = st.text_input(
                "Previous Hospitalization Records",
                value=p["complaint_previous_hospitalization"] or "",
            )

        with st.expander(
            "Clinical Impressions, Examinations & Treatment Matrix"
        ):
            initial_imp = st.text_area(
                "Interviewers Initial Impression",
                value=p["interviewers_initial_impression"] or "",
            )
            hist_illness = st.text_area(
                "History of Present Illness",
                value=p["history_of_illness"] or "",
            )
            mse_notes = st.text_area(
                "Mental Status Examination (MSE)",
                value=p["mental_status_examination"] or "",
            )
            nurse_obs = st.text_area(
                "Nurses Observation",
                value=p["nurses_observation"] or "",
            )
            diag_notes = st.text_area(
                "Diagnosis Statement", value=p["diagnosis"] or ""
            )
            treat_plan = st.text_area(
                "Treatment Plan Summary", value=p["treatment"] or ""
            )
            medication_table = dataframe_from_storage(
                p["parenteral_medication_records"],
                MEDICATION_COLUMNS,
            )
            edited_medication_table = st.data_editor(
                medication_table,
                num_rows="dynamic",
                width="stretch",
                key=f"medication_table_{target_id}",
            )

        st.divider()
        if st.button(
            "💾 Apply Data Modifications Securely",
            type="primary",
            key=f"save_patient_changes_{target_id}",
        ):
            if not f_name.strip() or not l_name.strip():
                st.error("First name and last name are required to save this record.")
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
                            referral_noted_by = ?, means_of_referral = ?, interview_date = ?, interview_place = ?, interview_persons_present = ?, primary_source_of_information = ?,
                            first_name = ?, middle_name = ?, last_name = ?, extension_name = ?, calculated_age = ?, sex = ?, date_of_birth = ?, civil_status = ?, religion = ?, educational_attainment = ?, status = ?, work_experience = ?,
                            street_address = ?, purok = ?, barangay = ?, city_municipality = ?, province = ?,
                            guardian_last_name = ?, guardian_first_name = ?, guardian_middle_name = ?, guardian_street_address = ?, g_barangay = ?, g_city = ?, g_province = ?, guardian_contact_person = ?, g_contact_number = ?,
                            family_composition = ?, total_annual_income = ?, poverty_threshold_per_year = ?, poverty_rating = ?, classification_after_interview = ?, classification_after_home_visit = ?,
                            chief_complaint_patient = ?, chief_complaint_relatives = ?, complaint_duration = ?, complaint_recent = ?, complaint_onset = ?, complaint_previous_hospitalization = ?,
                            interviewers_initial_impression = ?, history_of_illness = ?, mental_status_examination = ?, nurses_observation = ?, diagnosis = ?, treatment = ?, parenteral_medication_records = ?
                        WHERE patient_id = ?
                        """,
                        (
                            ref_by,
                            means_ref,
                            int_date,
                            int_place,
                            int_present,
                            primary_src,
                            f_name,
                            m_name,
                            l_name,
                            ext_name,
                            int(calc_age),
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


def show_manage_page():
    selected_id = st.session_state.get("manage_selected_patient_id")
    success_message = st.session_state.pop("manage_success_message", None)
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
        with name_lookup_column:
            st.session_state.setdefault("patient_name_lookup_query", "")
            name_search_term = st.text_input(
                "Restricted Name Lookup",
                key="patient_name_lookup_query",
                placeholder="Enter a patient name",
                type="password",
                autocomplete="off",
                label_visibility="collapsed",
                width="stretch",
            ).strip()
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
