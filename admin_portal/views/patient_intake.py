import datetime


SECTION_TITLES = {
    "referral": "Referral Sheet",
    "interview": "Interview",
    "identifying": "Identifying Information",
    "client": "A. INFORMATION ABOUT THE CLIENT",
    "relatives": "Name and Address of the Nearest Relatives / Guardians",
    "family": "B. FAMILY COMPOSITION",
    "classification": "C. PATIENT'S CLASSIFICATION",
    "complaint": "Chief complaint:",
    "impression": "Interviewers Initial Impression",
    "history_of_illness": "History of the Patient's Illness:",
    "mental_status_examination": "Mental Status Examination / Progress Notes:",
    "nurses_observation": "Nurses Observation during Consultation:",
    "diagnosis": "Diagnosis:",
    "treatment": "Treatment:",
    "administration": "Record Administration",
    "medications": "Parenteral Medication Sheet",
}

MIN_BIRTH_DATE = datetime.date(1900, 1, 1)

FIELD_LABELS = {
    "referral_noted_by": "Information Noted By:",
    "referring_person_or_instance": "Referring Person or Instance:",
    "date_of_referral": "Date of Referral:",
    "means_of_referral": "Means of Referral:",
    "referral_request": "Request:",
    "agreements_made_for_further_interviewing": (
        "Agreements Made re: Further Interviewing:"
    ),
    "interview_date": "Date:",
    "interview_place": "Place:",
    "interview_persons_present": "Persons Present During the Interview:",
    "primary_source_of_information": "Primary Source of Information:",
    "client_name": "Name of Client:",
    "age": "Age:",
    "address": "Address:",
    "date_of_birth": "Date of Birth:",
    "sex": "Sex:",
    "civil_status": "Civil Status:",
    "religion": "Religion:",
    "educational_attainment": "Educational Attainment:",
    "work_experience": "Work Experience:",
    "contact_person": "Contact Person:",
    "contact_number": "Contact Number:",
    "household_member_count": "No. of Household Members:",
    "total_annual_income": "Total annual income:",
    "poverty_threshold_per_year": "Poverty threshold/year:",
    "poverty_rating": "Ratings:",
    "classification_after_interview": "Classification after Interview",
    "classification_after_home_visit": "Classification after Home Visit",
    "chief_complaint_patient": "According to the Client / Patient:",
    "chief_complaint_relatives": "According to the Reference / Relatives:",
    "complaint_duration": "Duration:",
    "complaint_onset": "Onset:",
    "complaint_recent": "Recent:",
    "complaint_previous_hospitalization": "Previous Hospitalization:",
    "interviewers_initial_impression": "Interviewers Initial Impression:",
    "history_of_illness": "History of the Patient's Illness:",
    "mental_status_examination": "Mental Status Examination / Progress Notes:",
    "nurses_observation": "Nurses Observation during Consultation:",
    "diagnosis": "Diagnosis:",
    "treatment": "Treatment:",
    "status": "Current Administrative Status:",
    "patient_case_number": "Patient ID / Case Number:",
    "date_registered": "Date Registered:",
}

SEX_OPTIONS = ("Male", "Female", "Others")
CIVIL_STATUS_OPTIONS = ("", "Single", "Married", "Widowed", "Separated")
INFORMATION_NOTED_BY_OPTIONS = ("Admin 1", "Admin 2")
EDUCATIONAL_ATTAINMENT_OPTIONS = (
    "No Formal Education",
    "Elementary Level",
    "Elementary Graduate",
    "High School Level",
    "High School Graduate",
    "Vocational / Technical",
    "College Level",
    "College Graduate",
    "Postgraduate",
)
ADMINISTRATIVE_STATUS_OPTIONS = ("Alive", "Deceased")
