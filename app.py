import streamlit as st
import hmac
import os
from views.dashboard import show_dashboard_page
from views.encode import show_encode_page
from views.search import show_search_page
from views.manage import show_manage_page
from views.audit import show_audit_page
from views.appointments import show_appointments_page

# --- GLOBAL APPLICATION WINDOW INTERFACE LAYOUT CONFIGURATION ---
st.set_page_config(
    page_title="Brothers of Charity - HFRC Records",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234")


def show_login_page():
    _, login_col, _ = st.columns([1, 2, 1])
    with login_col:
        with st.container(border=True):
            st.title("HFRC Admin Login")
            st.write("Sign in to access the Brothers of Charity record archive.")

            st.html(
                """
                <style>
                [data-testid="stTextInput"] [data-testid="InputInstructions"] {
                    display: none;
                }
                button[aria-label="Show password"],
                button[aria-label="Hide password"] {
                    display: none;
                }
                </style>
                """
            )
            username = st.text_input("Username", autocomplete="username")
            password = st.text_input(
                "Password",
                type="password",
                autocomplete="current-password",
            )

            if st.button("Log in", type="primary"):
                valid_username = hmac.compare_digest(username, ADMIN_USERNAME)
                valid_password = hmac.compare_digest(password, ADMIN_PASSWORD)
                if valid_username and valid_password:
                    st.session_state["admin_authenticated"] = True
                    st.rerun()
                st.error("Invalid username or password.")


if not st.session_state.get("admin_authenticated", False):
    login_page = st.Page(show_login_page, title="Login")
    st.navigation([login_page], position="hidden").run()
    st.stop()

with st.sidebar:
    if st.button("Log out"):
        st.session_state["admin_authenticated"] = False
        st.rerun()

# --- INSTANTIATE LOGICAL RUNTIME ROUTING ENDPOINTS ---
dashboard_page = st.Page(
    show_dashboard_page, 
    title="Dashboard & Stats", 
    icon=":material/analytics:"
)

encode_page = st.Page(
    show_encode_page, 
    title="Encode New Folder", 
    icon=":material/person_add:"
)

search_page = st.Page(
    show_search_page, 
    title="Search Records", 
    icon=":material/search:"
)

manage_page = st.Page(
    show_manage_page, 
    title="Manage Folders", 
    icon=":material/folder_managed:"
)

appointments_page = st.Page(
    show_appointments_page,
    title="Appointments",
    icon=":material/calendar_month:"
)

audit_page = st.Page(
    show_audit_page,
    title="Audit Ledger",
    icon=":material/history:"
)

# --- GENERATE COMPREHENSIVE ADMIN NAVIGATION SCHEMA LAYOUT ---
pg = st.navigation({
    "Analytical Overview": [
        dashboard_page
    ],
    "Administrative Archiving": [
        encode_page, 
        search_page, 
        manage_page,
        appointments_page
    ],
    "Administrative Audit": [
        audit_page
    ]
})

# Execute current viewport view thread automatically
pg.run()
