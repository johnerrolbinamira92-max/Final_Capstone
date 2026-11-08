import streamlit as st
from database import authenticate_admin
from views.appointments import show_appointments_page
from views.audit import show_audit_page
from views.dashboard import show_dashboard_page
from views.encode import show_encode_page
from views.helpline import show_helpline_page
from views.manage import show_manage_page
from views.search import show_search_page

st.set_page_config(
    page_title="Brothers of Charity - HFRC Records",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --hfrc-page: #102321;
        --hfrc-page-deep: #0c1d1b;
        --hfrc-surface: #183330;
        --hfrc-surface-raised: #21423e;
        --hfrc-line: #31534f;
        --hfrc-text: #f5f1e7;
        --hfrc-muted: #a9c7c1;
        --hfrc-teal: #367a75;
        --hfrc-teal-bright: #83b9b0;
    }

    [data-testid="stAppViewContainer"] {
        background: var(--hfrc-page);
    }

    [data-testid="stHeader"] {
        background: color-mix(in srgb, var(--hfrc-page-deep) 94%, transparent);
        border-bottom: 1px solid var(--hfrc-line);
    }

    [data-testid="stMainBlockContainer"] {
        max-width: 1440px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    [data-testid="stMainBlockContainer"]:has(.st-key-admin-login-page) {
        min-height: calc(100vh - 3.5rem);
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }

    [data-testid="stMainBlockContainer"]:has(.st-key-admin-login-page) > [data-testid="stVerticalBlock"] {
        justify-content: safe center;
    }

    .st-key-admin-login-page {
        width: 100%;
        align-items: center;
    }

    .st-key-admin-login-card {
        width: 100%;
        max-width: 560px;
        height: auto;
        margin-inline: auto;
        padding: 2.5rem 2.75rem;
        border-color: var(--hfrc-line);
        border-radius: 24px;
        background: var(--hfrc-surface);
    }

    .st-key-admin-login-card [data-testid="stHeading"],
    .st-key-admin-login-card [data-testid="stMarkdownContainer"] {
        text-align: center;
    }

    .st-key-admin-login-card [data-testid="stTextInput"] [data-testid="InputInstructions"] {
        display: none;
    }

    .st-key-admin-login-card [data-testid="stTextInput"] input {
        min-height: 3rem;
        border-radius: 999px;
        background: var(--hfrc-surface-raised);
    }

    .st-key-admin-login-card [data-testid="stFormSubmitButton"] {
        width: 100%;
    }

    .st-key-admin-login-card [data-testid="stFormSubmitButton"] button {
        width: 100%;
        min-height: 3rem;
        margin-top: 0.75rem;
    }

    @media (max-width: 640px) {
        .st-key-admin-login-card {
            padding: 1.75rem 1.25rem;
        }
    }

    h1, h2, h3, [data-testid="stHeading"] {
        font-family: "Playfair Display", Georgia, serif;
        letter-spacing: -0.025em;
    }

    h1, h2, h3 {
        color: var(--hfrc-text);
        font-weight: 500;
    }

    [data-testid="stCaptionContainer"],
    [data-testid="stMarkdownContainer"] small {
        color: var(--hfrc-muted);
    }

    [data-testid="stSidebar"] {
        background: var(--hfrc-page-deep);
        border-right: 1px solid var(--hfrc-line);
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
        color: var(--hfrc-text);
    }

    [data-testid="stSidebar"] button[kind="secondary"] {
        border-color: var(--hfrc-line);
        background: var(--hfrc-surface);
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: var(--hfrc-line);
        border-radius: 20px;
        background: var(--hfrc-surface);
    }

    [data-testid="stBaseButton-primary"],
    button[kind="primary"] {
        min-height: 2.75rem;
        border: 1px solid var(--hfrc-teal);
        border-radius: 999px;
        background: var(--hfrc-teal);
        color: #fff;
        font-family: "DM Sans", sans-serif;
        font-weight: 700;
        transition: filter 140ms ease, transform 140ms ease;
    }

    [data-testid="stBaseButton-primary"]:hover,
    button[kind="primary"]:hover {
        border-color: var(--hfrc-teal-bright);
        background: var(--hfrc-teal);
        filter: brightness(1.1);
        transform: translateY(-1px);
    }

    [data-testid="stBaseButton-secondary"],
    button[kind="secondary"] {
        min-height: 2.65rem;
        border: 1px solid var(--hfrc-line);
        border-radius: 999px;
        background: transparent;
        color: var(--hfrc-text);
        font-family: "DM Sans", sans-serif;
        font-weight: 600;
    }

    [data-testid="stBaseButton-secondary"]:hover,
    button[kind="secondary"]:hover {
        border-color: var(--hfrc-teal-bright);
        color: var(--hfrc-text);
    }

    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stDateInput"] input,
    [data-testid="stTimeInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
        border-color: var(--hfrc-line);
        border-radius: 12px;
        background: var(--hfrc-surface-raised);
    }

    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus {
        border-color: var(--hfrc-teal-bright);
        box-shadow: 0 0 0 1px var(--hfrc-teal-bright);
    }

    [data-testid="stTabs"] [role="tab"] {
        font-family: "DM Sans", sans-serif;
        font-weight: 600;
    }

    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        color: var(--hfrc-teal-bright);
    }

    [data-testid="stDataFrame"] {
        overflow: hidden;
        border: 1px solid var(--hfrc-line);
        border-radius: 16px;
    }

    [data-testid="stAlert"] {
        border-radius: 14px;
    }

    [data-testid="stExpander"] {
        border-color: var(--hfrc-line);
        border-radius: 14px;
    }

    button:focus-visible,
    input:focus-visible,
    textarea:focus-visible,
    [role="tab"]:focus-visible {
        outline: 2px solid var(--hfrc-teal-bright);
        outline-offset: 2px;
    }

    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            scroll-behavior: auto !important;
            transition-duration: 0.01ms !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def show_login_page():
    with st.container(key="admin-login-page"):
        with st.container(border=True, key="admin-login-card"):
            st.title("Admin Login")
            st.markdown("Welcome back! Please enter your account.")

            with st.form("admin_login_form", border=False):
                email = st.text_input(
                    "Email",
                    placeholder="Email",
                    icon=":material/person:",
                    autocomplete="username",
                    label_visibility="collapsed",
                )
                password = st.text_input(
                    "Password",
                    type="password",
                    placeholder="Password",
                    icon=":material/lock:",
                    autocomplete="current-password",
                    label_visibility="collapsed",
                )
                submitted = st.form_submit_button(
                    "Log in",
                    type="primary",
                    width="stretch",
                )

            if submitted:
                try:
                    admin = authenticate_admin(email, password)
                except PermissionError as error:
                    st.error(str(error))
                except Exception as error:
                    st.error(f"Unable to authenticate with Supabase: {error}")
                else:
                    st.session_state["admin_authenticated"] = True
                    st.session_state["admin_profile"] = admin
                    st.rerun()


if not st.session_state.get("admin_authenticated", False):
    login_page = st.Page(show_login_page, title="Login")
    st.navigation([login_page], position="hidden").run()
    st.stop()

with st.sidebar:
    profile = st.session_state.get("admin_profile", {})
    if profile.get("display_name"):
        st.caption(f"Signed in as {profile['display_name']}")
    if st.button("Log out"):
        st.session_state["admin_authenticated"] = False
        st.session_state.pop("admin_profile", None)
        st.rerun()

dashboard_page = st.Page(
    show_dashboard_page,
    title="Dashboard & Stats",
    icon=":material/analytics:",
)

encode_page = st.Page(
    show_encode_page,
    title="Encode New Folder",
    icon=":material/person_add:",
)

search_page = st.Page(
    show_search_page,
    title="Search Records",
    icon=":material/search:",
)

manage_page = st.Page(
    show_manage_page,
    title="Manage Folders",
    icon=":material/folder_managed:",
)

appointments_page = st.Page(
    show_appointments_page,
    title="Appointments",
    icon=":material/calendar_month:",
)

helpline_page = st.Page(
    show_helpline_page,
    title="Helpline Requests",
    icon=":material/volunteer_activism:",
)

audit_page = st.Page(
    show_audit_page,
    title="Audit Ledger",
    icon=":material/history:",
)

pg = st.navigation(
    {
        "Analytical Overview": [dashboard_page],
        "Administrative Archiving": [
            encode_page,
            search_page,
            manage_page,
            appointments_page,
            helpline_page,
        ],
        "Administrative Audit": [audit_page],
    }
)

pg.run()
