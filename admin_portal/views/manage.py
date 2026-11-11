import json
from pathlib import Path

import streamlit as st
from database import get_local_connection
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


PATIENT_DETAIL_SECTIONS = (
    (
        "Registration and interview",
        (
            "patient_id",
            "date_registered",
            "referral_noted_by",
            "means_of_referral",
            "interview_date",
            "interview_place",
            "interview_persons_present",
            "primary_source_of_information",
        ),
    ),
    (
        "Patient profile",
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
        "Residential address",
        (
            "street_address",
            "purok",
            "barangay",
            "city_municipality",
            "province",
        ),
    ),
    (
        "Guardian and nearest relative",
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
        "Household and socioeconomic information",
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
        "Complaints and history",
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
        "Clinical notes and treatment",
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


def _render_patient_details(patient):
    patient_field_order = list(patient.keys())
    patient_fields = set(patient_field_order)
    displayed_fields = set()

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
                display_value = (
                    "Not recorded"
                    if value is None or value == ""
                    else str(value)
                )
                with value_columns[index % 2]:
                    st.markdown(f"**{_detail_label(field)}**")
                    st.text(display_value)

    remaining_fields = [
        field for field in patient_field_order if field not in displayed_fields
    ]
    if remaining_fields:
        with st.container(border=True):
            st.markdown("#### Other record fields")
            value_columns = st.columns(2)
            for index, field in enumerate(remaining_fields):
                value = patient[field]
                display_value = (
                    "Not recorded"
                    if value is None or value == ""
                    else str(value)
                )
                with value_columns[index % 2]:
                    st.markdown(f"**{_detail_label(field)}**")
                    st.text(display_value)


def _patient_full_name(record):
    return " ".join(
        str(record.get(field) or "").strip()
        for field in ("first_name", "middle_name", "last_name", "extension_name")
        if record.get(field) and str(record[field]).strip()
    )


def _render_patient_results(records, filters_applied):
    st.markdown(
        f"### {len(records):,} "
        f"{'matching' if filters_applied else 'archived'} patient record(s)"
    )
    for record in records:
        patient_id = record["patient_id"]
        full_name = _patient_full_name(record) or "Unnamed patient"
        with st.container(border=True, key=f"patient-result-{patient_id}"):
            if st.button(
                full_name,
                icon=":material/description:",
                key=f"select_patient_{patient_id}",
                width="stretch",
            ):
                st.session_state["manage_selected_patient_id"] = patient_id
                st.session_state.pop("manage_edit_patient_id", None)
                st.session_state.pop("manage_delete_patient_id", None)
                st.rerun()
            summary_columns = st.columns(4)
            summary_columns[0].markdown(
                f"**Age**  \n{record['calculated_age'] if record['calculated_age'] is not None else 'Not specified'}"
            )
            summary_columns[1].markdown(
                f"**Gender**  \n{record['sex'] or 'Not specified'}"
            )
            summary_columns[2].markdown(
                f"**Status**  \n{record['status'] or 'Alive'}"
            )
            summary_columns[3].markdown(f"**Patient ID**  \n{patient_id}")
            location = ", ".join(
                str(value).strip()
                for value in (
                    record["barangay"],
                    record["city_municipality"],
                    record["province"],
                )
                if value and str(value).strip()
            )
            st.caption(location or "Location not specified")


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
        st.session_state.pop("manage_selected_patient_id", None)
        return

    patient = dict(selected_patient)
    selected_name = _patient_full_name(patient) or "Unnamed patient"
    with st.container(border=True, key="selected-patient-details"):
        back_column, title_column, edit_column, delete_column = st.columns(
            [1, 4, 1, 1], vertical_alignment="center"
        )
        with back_column:
            if st.button(
                "Back",
                icon=":material/arrow_back:",
                key="back_to_patient_results",
                width="stretch",
            ):
                st.session_state.pop("manage_selected_patient_id", None)
                st.session_state.pop("manage_edit_patient_id", None)
                st.session_state.pop("manage_delete_patient_id", None)
                st.rerun()
        with title_column:
            st.markdown(f"### {selected_name}")
            st.caption(f"Complete patient record · ID {selected_id}")
        with edit_column:
            if st.button(
                "Edit",
                icon=":material/edit:",
                key=f"edit_patient_{selected_id}",
                width="stretch",
            ):
                st.session_state["manage_edit_patient_id"] = selected_id
                st.session_state.pop("manage_delete_patient_id", None)
                st.rerun()
        with delete_column:
            if st.button(
                "Delete",
                icon=":material/delete:",
                key=f"delete_patient_{selected_id}",
                width="stretch",
            ):
                st.session_state["manage_delete_patient_id"] = selected_id
                st.session_state.pop("manage_edit_patient_id", None)
                st.rerun()
        _render_patient_details(patient)


def show_manage_page():
    with st.container(key="admin-search-page"):
        st.markdown(
            '<div class="search-eyebrow">Patient records</div>',
            unsafe_allow_html=True,
        )
        st.markdown("# Search records")
        st.write(
            "Search the local archive, review patient summaries, and securely "
            "manage complete records."
        )
        st.session_state.setdefault("patient_search_query", "")
        search_term = st.text_input(
            "Search by patient name, ID, or location",
            key="patient_search_query",
            placeholder="Search patient name, ID, or location...",
            icon=":material/search:",
        ).strip()

    try:
        conn = get_local_connection()
    except Exception as error:
        st.error(f"Unable to open the local patient archive: {error}")
        return
    try:
        all_records = conn.execute(
            """
            SELECT patient_id, first_name, middle_name, last_name, extension_name,
                   calculated_age, sex, status, street_address, barangay,
                   city_municipality, province
            FROM patients
            ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE, patient_id
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

    with st.container(border=True, key="record-search-filters"):
        st.markdown("### Filter records")
        province_column, city_column, barangay_column, gender_column = st.columns(4)
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

    if minimum_age > maximum_age:
        st.error("Minimum age cannot be greater than maximum age.")
        return

    filtered_records = []
    for record in record_dicts:
        if search_term:
            searchable_values = (
                record["patient_id"],
                record["first_name"],
                record["middle_name"],
                record["last_name"],
                record["extension_name"],
                record["street_address"],
                record["barangay"],
                record["city_municipality"],
                record["province"],
            )
            search_text = " ".join(
                str(value or "") for value in searchable_values
            ).casefold()
            if search_term.casefold() not in search_text:
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
        search_term
        or selected_province is not None
        or selected_city is not None
        or selected_barangay is not None
        or selected_gender != "All genders"
        or minimum_age > 0
        or maximum_age < 120
    )
    st.markdown("---")
    selected_id = st.session_state.get("manage_selected_patient_id")
    if selected_id is not None:
        _render_selected_patient_detail(selected_id)
    else:
        if not record_dicts:
            st.info("There are no patient records in the local archive yet.")
        elif not filtered_records:
            st.info("No patient records match the search and selected filters.")
        else:
            _render_patient_results(filtered_records, filters_applied)

    delete_id = st.session_state.get("manage_delete_patient_id")
    if delete_id is not None:
        pending_record = next(
            (record for record in record_dicts if record["patient_id"] == delete_id),
            None,
        )
        if pending_record is None:
            st.error("The selected patient record is no longer available.")
            st.session_state.pop("manage_delete_patient_id", None)
        else:
            delete_name = " ".join(
                part
                for part in (
                    pending_record["first_name"],
                    pending_record["last_name"],
                )
                if part
            )
            with st.container(border=True, key="patient-delete-confirmation"):
                st.warning(
                    f"Delete the complete local patient record for **{delete_name}** "
                    f"(ID {delete_id})? This cannot be undone."
                )
                cancel_column, confirm_column = st.columns(2)
                with cancel_column:
                    if st.button(
                        "Cancel",
                        key="cancel_patient_delete",
                        width="stretch",
                    ):
                        st.session_state.pop("manage_delete_patient_id", None)
                        st.rerun()
                with confirm_column:
                    if st.button(
                        "Yes, permanently delete",
                        type="primary",
                        key="confirm_patient_delete",
                        width="stretch",
                    ):
                        conn = get_local_connection()
                        try:
                            with conn:
                                result = conn.execute(
                                    "DELETE FROM patients WHERE patient_id = ?",
                                    (delete_id,),
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
                                        "DELETE",
                                        f"Deleted patient record {delete_id} "
                                        f"({delete_name})",
                                    ),
                                )
                        except Exception as error:
                            st.error(f"Unable to delete the patient record: {error}")
                        else:
                            st.session_state.pop("manage_delete_patient_id", None)
                            st.session_state.pop("manage_edit_patient_id", None)
                            st.session_state.pop("manage_selected_patient_id", None)
                            st.success("The patient record was permanently deleted.")
                            st.rerun()
                        finally:
                            conn.close()

    target_id = st.session_state.get("manage_edit_patient_id")
    if target_id is None:
        return

    # Pull complete row data for target item
    try:
        conn = get_local_connection()
    except Exception as error:
        st.error(f"Unable to open the local patient archive: {error}")
        return
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM patients WHERE patient_id = ?", (target_id,))
        p = cursor.fetchone()
    except Exception as error:
        st.error(f"Unable to read the selected patient record: {error}")
        return
    finally:
        conn.close()

    if p is None:
        st.error("The selected patient record is no longer available.")
        st.session_state.pop("manage_edit_patient_id", None)
        return

    st.divider()
    if st.button("Close editor", key="close_patient_editor"):
        st.session_state.pop("manage_edit_patient_id", None)
        st.rerun()

    with st.expander("Edit complete patient record", expanded=True):
        st.subheader(f"Edit patient record · {p['first_name']} {p['last_name']}")
        st.write("Expand the dropdown panels below to edit specific pages of the folder architecture cleanly.")

        # --- DROP DOWN 1: LOGISTICS ---
        with st.expander("🏢 Page 1: Referral Context & Interview Logistics"):
            ref_by = st.text_input("Information Noted By", value=p["referral_noted_by"] or "")
            means_ref = st.text_input("Means of Referral", value=p["means_of_referral"] or "")
            int_date = st.text_input("Date of Interview (YYYY-MM-DD)", value=p["interview_date"] or "")
            int_place = st.text_input("Place of Interview", value=p["interview_place"] or "")
            int_present = st.text_area("Persons Present During Interview", value=p["interview_persons_present"] or "")
            primary_src = st.text_input("Primary Source of Information", value=p["primary_source_of_information"] or "")

        # --- DROP DOWN 2: PROFILE ---
        with st.expander(
            "👤 Page 2: Core Patient Identifying Profile",
            expanded=True,
        ):
            c_n1, c_n2, c_n3 = st.columns(3)
            with c_n1: f_name = st.text_input("First Name", value=p["first_name"])
            with c_n2: m_name = st.text_input("Middle Name", value=p["middle_name"] or "")
            with c_n3: l_name = st.text_input("Last Name", value=p["last_name"])
            ext_name = st.text_input("Suffix / Extension Name", value=p["extension_name"] or "")
            
            c_d1, c_d2 = st.columns(2)
            with c_d1: calc_age = st.number_input("Calculated Age", min_value=0, step=1, value=int(p["calculated_age"] or 0))
            with c_d2:
                sex_options = ["", "Male", "Female"]
                sex = st.selectbox(
                    "Sex",
                    sex_options,
                    index=sex_options.index(p["sex"]) if p["sex"] in sex_options else 0,
                )
            
            dob_str = st.text_input("Date of Birth (YYYY-MM-DD)", value=p["date_of_birth"] or "")
            civ_status = st.text_input("Civil Status", value=p["civil_status"] or "")
            religion = st.text_input("Religion", value=p["religion"] or "")
            edu = st.text_input("Educational Attainment", value=p["educational_attainment"] or "")
            status_options = ["Alive", "Deceased"]
            adm_status = st.selectbox(
                "Current Administrative Status",
                status_options,
                index=status_options.index(p["status"])
                if p["status"] in status_options else 0,
            )
            work_exp = st.text_area("Work Experience", value=p["work_experience"] or "")

        # --- DROP DOWN 3: RESIDENTIAL RESIDENCE ---
        with st.expander("📍 Page 3: Residential Address Demographics"):
            street = st.text_input("Street / House Number", value=p["street_address"] or "")
            purok = st.text_input("Purok", value=p["purok"] or "")
            brgy = st.text_input("Barangay", value=p["barangay"] or "")
            city = st.text_input("City / Municipality", value=p["city_municipality"] or "")
            prov = st.text_input("Province", value=p["province"] or "")

        # --- DROP DOWN 4: GUARDIANS ---
        with st.expander("👨‍👩‍👧 Page 4: Nearest Relatives / Guardian Profiles"):
            g_first = st.text_input("Guardian First Name", value=p["guardian_first_name"] or "")
            g_mid = st.text_input("Guardian Middle Name", value=p["guardian_middle_name"] or "")
            g_last = st.text_input("Guardian Last Name", value=p["guardian_last_name"] or "")
            g_street = st.text_input("Guardian Street Address", value=p["guardian_street_address"] or "")
            g_brgy = st.text_input("Guardian Barangay", value=p["g_barangay"] or "")
            g_city = st.text_input("Guardian City/Municipality", value=p["g_city"] or "")
            g_prov = st.text_input("Guardian Province", value=p["g_province"] or "")
            g_contact = st.text_input("Guardian Contact Person Name", value=p["guardian_contact_person"] or "")
            g_contact_number = st.text_input(
                "Guardian Contact Number",
                value=p["g_contact_number"] or "",
            )

        # --- DROP DOWN 5: SOCIO ECONOMIC ---
        with st.expander("📊 Page 5: Household & Socio-Economic Classifications"):
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
            ann_inc = st.number_input("Total Annual Income (PHP)", min_value=0.0, step=500.0, value=float(p["total_annual_income"] or 0.0))
            pov_thresh = st.number_input("Poverty Threshold Per Year (PHP)", min_value=0.0, step=500.0, value=float(p["poverty_threshold_per_year"] or 0.0))
            pov_rate = st.text_input("Poverty Rating", value=p["poverty_rating"] or "")
            class_int = st.text_input("Classification After Interview", value=p["classification_after_interview"] or "")
            class_visit = st.text_input("Classification After Home Visit", value=p["classification_after_home_visit"] or "")

        # --- DROP DOWN 6: COMPLAINTS ---
        with st.expander("🧠 Page 6 & 7: Chief Complaint Metrics & Onset"):
            cc_pat = st.text_area("Chief Complaint (Patient)", value=p["chief_complaint_patient"] or "")
            cc_rel = st.text_area("Chief Complaint (Relatives)", value=p["chief_complaint_relatives"] or "")
            c_dur = st.text_input("Complaint Duration", value=p["complaint_duration"] or "")
            c_rec = st.text_input("Recent Manifestations", value=p["complaint_recent"] or "")
            c_onset = st.text_input("Complaint Onset", value=p["complaint_onset"] or "")
            c_hosp = st.text_input("Previous Hospitalization Records", value=p["complaint_previous_hospitalization"] or "")

        # --- DROP DOWN 7: CLINICAL PROGRESSION ---
        with st.expander("📋 Page 8, 9 & 10: Clinical Impressions, Examinations & Treatment Matrix"):
            initial_imp = st.text_area("Interviewers Initial Impression", value=p["interviewers_initial_impression"] or "")
            hist_illness = st.text_area("History of Present Illness", value=p["history_of_illness"] or "")
            mse_notes = st.text_area("Mental Status Examination (MSE)", value=p["mental_status_examination"] or "")
            nurse_obs = st.text_area("Nurses Observation", value=p["nurses_observation"] or "")
            diag_notes = st.text_area("Diagnosis Statement", value=p["diagnosis"] or "")
            treat_plan = st.text_area("Treatment Plan Summary", value=p["treatment"] or "")
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

        if st.button("💾 Apply Data Modifications Securely", type="primary"):
            if not f_name.strip() or not l_name.strip():
                st.error("First name and last name are required to save this record.")
                return
            conn = get_local_connection()
            try:
                with conn:
                    conn.execute("""
                        UPDATE patients SET 
                            referral_noted_by = ?, means_of_referral = ?, interview_date = ?, interview_place = ?, interview_persons_present = ?, primary_source_of_information = ?,
                            first_name = ?, middle_name = ?, last_name = ?, extension_name = ?, calculated_age = ?, sex = ?, date_of_birth = ?, civil_status = ?, religion = ?, educational_attainment = ?, status = ?, work_experience = ?,
                            street_address = ?, purok = ?, barangay = ?, city_municipality = ?, province = ?,
                            guardian_last_name = ?, guardian_first_name = ?, guardian_middle_name = ?, guardian_street_address = ?, g_barangay = ?, g_city = ?, g_province = ?, guardian_contact_person = ?, g_contact_number = ?,
                            family_composition = ?, total_annual_income = ?, poverty_threshold_per_year = ?, poverty_rating = ?, classification_after_interview = ?, classification_after_home_visit = ?,
                            chief_complaint_patient = ?, chief_complaint_relatives = ?, complaint_duration = ?, complaint_recent = ?, complaint_onset = ?, complaint_previous_hospitalization = ?,
                            interviewers_initial_impression = ?, history_of_illness = ?, mental_status_examination = ?, nurses_observation = ?, diagnosis = ?, treatment = ?, parenteral_medication_records = ?
                        WHERE patient_id = ?
                    """, (
                        ref_by, means_ref, int_date, int_place, int_present, primary_src,
                        f_name, m_name, l_name, ext_name, int(calc_age), sex, dob_str, civ_status, religion, edu, adm_status, work_exp,
                        street, purok, brgy, city, prov,
                        g_last, g_first, g_mid, g_street, g_brgy, g_city, g_prov, g_contact, g_contact_number,
                        dataframe_to_storage(edited_family_table), float(ann_inc), float(pov_thresh), pov_rate, class_int, class_visit,
                        cc_pat, cc_rel, c_dur, c_rec, c_onset, c_hosp,
                        initial_imp, hist_illness, mse_notes, nurse_obs, diag_notes, treat_plan,
                        dataframe_to_storage(edited_medication_table),
                        target_id
                    ))
                    # Log the successful modification into the audit trail ledger securely
                    conn.execute(
                        "INSERT INTO admin_logs (action_type, details) VALUES (?, ?)",
                        ("UPDATE", f"Modified archived folder properties for Patient ID: {target_id} ({f_name} {l_name})")
                    )
                st.success("📋 Complete 10-page folder properties have been cleanly updated.")
                st.session_state.pop("manage_edit_patient_id", None)
                st.rerun()
            except Exception as e:
                st.error(f"Failed to complete transaction adjustments: {e}")
            finally:
                conn.close()

if __name__ == "__main__":
    show_manage_page()
