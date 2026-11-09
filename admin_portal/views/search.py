import streamlit as st
from database import get_local_connection
from views.record_tables import (
    FAMILY_COLUMNS,
    MEDICATION_COLUMNS,
    dataframe_from_storage,
)

def show_search_page():
    st.title("Search Patient Records")
    st.write("Find archived folders by a patient's first, middle, or last name.")

    search_query = st.text_input("Search by patient name")

    if search_query:
        try:
            conn = get_local_connection()
            cursor = conn.cursor()
            
            # Wildcard query targeting first, middle, or last name structures concurrently
            sql_query = """
                SELECT * FROM patients 
                WHERE last_name LIKE ? 
                OR first_name LIKE ? 
                OR middle_name LIKE ?
            """
            like_param = f"%{search_query}%"
            cursor.execute(sql_query, (like_param, like_param, like_param))
            records = cursor.fetchall()
            conn.close()

            if not records:
                st.warning(f"No patient records found for **{search_query}**.")
            else:
                st.success(f"Found {len(records)} matching patient record(s).")
                
                for row in records:
                    # Resolve names and state classifications smoothly
                    vital_status = row["status"] if row["status"] else "Alive"
                    status_color = "🔴 Deceased" if vital_status == "Deceased" else "🟢 Alive"
                    
                    m_initial = f" {row['middle_name']}" if row["middle_name"] else ""
                    suffix = f" {row['extension_name']}" if row["extension_name"] else ""
                    display_name = f"{row['last_name']}, {row['first_name']}{m_initial}{suffix}"
                    
                    with st.container(border=True):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.subheader(f"📁 Folder: {display_name}")
                        with col2:
                            st.write(f"**Administrative Status:** {status_color}")
                        
                        # 10-Page structure display tabs
                        t1, t2, t3, t4, t5 = st.tabs([
                            "📋 General Profile", 
                            "👨‍👩‍👦 Family & Intake", 
                            "🧠 Clinical Complaints", 
                            "📝 Notes & MSE", 
                            "🩺 Medical Records"
                        ])
                        
                        with t1:
                            c1, c2 = st.columns(2)
                            with c1:
                                st.write(f"**Date of Birth:** {row['date_of_birth'] if row['date_of_birth'] else 'N/A'}")
                                st.write(f"**Calculated Age:** {row['calculated_age'] if row['calculated_age'] else '0'} years old")
                                st.write(f"**Sex:** {row['sex'] if row['sex'] else 'Not specified'}")
                                st.write(f"**Civil Status:** {row['civil_status'] if row['civil_status'] else 'N/A'}")
                            with c2:
                                address = f"{row['street_address'] or ''}, {row['barangay'] or ''}, {row['city_municipality'] or ''}, {row['province'] or ''}".strip(", ")
                                st.write(f"**Complete Address:** {address if address else 'N/A'}")
                                st.write(f"**Religion:** {row['religion'] if row['religion'] else 'N/A'}")
                                st.write(f"**Educational Attainment:** {row['educational_attainment'] if row['educational_attainment'] else 'N/A'}")
                            st.write("**Work Experience History:**")
                            st.caption(row["work_experience"] if row["work_experience"] else "No prior work history recorded.")

                        with t2:
                            st.write("**Emergency Guardian Context:**")
                            g_name = f"{row['guardian_first_name'] or ''} {row['guardian_last_name'] or ''}".strip()
                            st.write(f"- **Contact Person:** {g_name if g_name else (row['guardian_contact_person'] or 'N/A')}")
                            st.write(f"- **Phone Number:** {row['g_contact_number'] if 'g_contact_number' in row.keys() and row['g_contact_number'] else 'No number listed'}")
                            
                            st.divider()
                            st.write("**Family Composition Data:**")
                            family_table = dataframe_from_storage(
                                row["family_composition"],
                                FAMILY_COLUMNS,
                            )
                            if family_table.empty:
                                st.info("No household composition table submitted.")
                            else:
                                st.dataframe(
                                    family_table,
                                    hide_index=True,
                                    width="stretch",
                                    alt="Patient family composition",
                                )
                            
                            st.divider()
                            st.write(f"**Socio-Economic Classification:** {row['classification_after_interview'] if row['classification_after_interview'] else 'Unclassified'}")

                        with t3:
                            st.write("**Chief Complaint (According to Patient):**")
                            st.caption(row["chief_complaint_patient"] if row["chief_complaint_patient"] else "No statements provided.")
                            st.write("**Chief Complaint (According to Relatives):**")
                            st.caption(row["chief_complaint_relatives"] if row["chief_complaint_relatives"] else "No statements provided.")
                            st.divider()
                            st.write(f"**Onset:** {row['complaint_onset'] if row['complaint_onset'] else 'N/A'}")
                            st.write(f"**Recent Manifestations:** {row['complaint_recent'] if row['complaint_recent'] else 'None documented'}")

                        with t4:
                            st.write("**Interviewers Initial Impression Evaluation:**")
                            st.caption(row["interviewers_initial_impression"] if row["interviewers_initial_impression"] else "Empty entries.")
                            st.write("**History of Present Illness Narrative:**")
                            st.caption(row["history_of_illness"] if row["history_of_illness"] else "Empty entries.")
                            st.write("**Mental Status Examination / Progress Notes:**")
                            st.caption(row["mental_status_examination"] if row["mental_status_examination"] else "Empty entries.")
                            st.write("**Nurses Consultation Observation Logs:**")
                            st.caption(row["nurses_observation"] if row["nurses_observation"] else "Empty entries.")

                        with t5:
                            st.markdown(f"**Official Diagnostic Assessment Evaluation:**\n\n> {row['diagnosis'] if row['diagnosis'] else 'Pending Final Evaluation'}")
                            st.markdown(f"**Active Treatment & Medical Rehabilitation Strategy:**\n\n> {row['treatment'] if row['treatment'] else 'No medical strategies assigned yet.'}")
                            st.divider()
                            st.write("**Parenteral Medication Sheet Matrix Entries:**")
                            medication_table = dataframe_from_storage(
                                row["parenteral_medication_records"],
                                MEDICATION_COLUMNS,
                            )
                            if medication_table.empty:
                                st.info("No localized injection sheet data attached.")
                            else:
                                st.dataframe(
                                    medication_table,
                                    hide_index=True,
                                    width="stretch",
                                    alt="Parenteral medication records",
                                )

        except Exception as e:
            st.error(f"Local Retrieval Failure: {str(e)}")
    else:
        st.info("Input a patient's name to open their offline digital folder archive.")

if __name__ == "__main__":
    show_search_page()