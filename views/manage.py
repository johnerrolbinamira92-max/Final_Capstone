import streamlit as st
from database import get_local_connection
from views.record_tables import (
    FAMILY_COLUMNS,
    MEDICATION_COLUMNS,
    dataframe_from_storage,
    dataframe_to_storage,
)

def show_manage_page():
    st.title("Manage Patient Records")
    st.write("Find an archived patient folder to review, update, or delete it.")

    # 1. Select Patient Section
    st.markdown("### Select a patient")
    search_term = st.text_input("Search by patient name")
    
    if not search_term:
        st.info("Please query a name to initialize modifying processes.")
        return

    conn = get_local_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT patient_id, first_name, last_name, middle_name, extension_name,
                   city_municipality, province
            FROM patients
            WHERE first_name LIKE ? OR last_name LIKE ? OR middle_name LIKE ?
            ORDER BY last_name, first_name, middle_name, patient_id
        """, (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%"))
        matches = cursor.fetchall()
    finally:
        conn.close()

    if not matches:
        st.warning("No records matched your query.")
        return

    # Keep labels descriptive and unique without exposing internal database IDs.
    patient_labels = []
    for row in matches:
        middle = f" {row['middle_name']}" if row["middle_name"] else ""
        extension = f" {row['extension_name']}" if row["extension_name"] else ""
        location_parts = [
            part for part in (row["city_municipality"], row["province"]) if part
        ]
        location = f" — {', '.join(location_parts)}" if location_parts else ""
        patient_labels.append(
            f"{row['last_name']}, {row['first_name']}{middle}{extension}{location}"
        )

    label_counts = {}
    for label in patient_labels:
        label_counts[label] = label_counts.get(label, 0) + 1
    seen_labels = {}
    unique_labels = []
    for label in patient_labels:
        seen_labels[label] = seen_labels.get(label, 0) + 1
        unique_labels.append(
            f"{label} ({seen_labels[label]})" if label_counts[label] > 1 else label
        )

    selected_index = st.selectbox(
        "Choose the profile folder to manage:",
        range(len(matches)),
        format_func=lambda index: unique_labels[index],
    )
    target_id = matches[selected_index]["patient_id"]

    # Pull complete row data for target item
    conn = get_local_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM patients WHERE patient_id = ?", (target_id,))
        p = cursor.fetchone()
    finally:
        conn.close()

    if p is None:
        st.error("The selected patient record is no longer available.")
        return

    st.divider()

    # Create layout view splits
    update_tab, action_tab = st.tabs(["✏️ Edit Complete 10-Page Information", "⚠️ Destructive Actions"])

    with action_tab:
        st.warning("**Danger Zone:** Deleting this file permanently removes the complete patient record.")
        
        if st.button("🗑️ Permanently Delete Record Folder", type="primary"):
            conn = get_local_connection()
            try:
                with conn:
                    conn.execute("DELETE FROM patients WHERE patient_id = ?", (target_id,))
                    conn.execute(
                        "INSERT INTO admin_logs (action_type, details) VALUES (?, ?)",
                        ("DELETE", f"Deleted patient record for {p['first_name']} {p['last_name']}")
                    )
                st.success("The patient record was deleted successfully.")
                st.rerun()
            except Exception as e:
                st.error(f"Execution Failure: {e}")
            finally:
                conn.close()

    with update_tab:
        st.subheader("Edit Patient Folder Archives")
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
        with st.expander("👤 Page 2: Core Patient Identifying Profile"):
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
            conn = get_local_connection()
            try:
                with conn:
                    conn.execute("""
                        UPDATE patients SET 
                            referral_noted_by = ?, means_of_referral = ?, interview_date = ?, interview_place = ?, interview_persons_present = ?, primary_source_of_information = ?,
                            first_name = ?, middle_name = ?, last_name = ?, extension_name = ?, calculated_age = ?, sex = ?, date_of_birth = ?, civil_status = ?, religion = ?, educational_attainment = ?, status = ?, work_experience = ?,
                            street_address = ?, barangay = ?, city_municipality = ?, province = ?,
                            guardian_last_name = ?, guardian_first_name = ?, guardian_middle_name = ?, guardian_street_address = ?, g_barangay = ?, g_city = ?, g_province = ?, guardian_contact_person = ?, g_contact_number = ?,
                            family_composition = ?, total_annual_income = ?, poverty_threshold_per_year = ?, poverty_rating = ?, classification_after_interview = ?, classification_after_home_visit = ?,
                            chief_complaint_patient = ?, chief_complaint_relatives = ?, complaint_duration = ?, complaint_recent = ?, complaint_onset = ?, complaint_previous_hospitalization = ?,
                            interviewers_initial_impression = ?, history_of_illness = ?, mental_status_examination = ?, nurses_observation = ?, diagnosis = ?, treatment = ?, parenteral_medication_records = ?
                        WHERE patient_id = ?
                    """, (
                        ref_by, means_ref, int_date, int_place, int_present, primary_src,
                        f_name, m_name, l_name, ext_name, int(calc_age), sex, dob_str, civ_status, religion, edu, adm_status, work_exp,
                        street, brgy, city, prov,
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
                st.rerun()
            except Exception as e:
                st.error(f"Failed to complete transaction adjustments: {e}")
            finally:
                conn.close()

if __name__ == "__main__":
    show_manage_page()
