import base64
import mimetypes
import os
from pathlib import Path

import streamlit as st
from database import (
    SUPABASE_KEY,
    SUPABASE_URL,
    authenticate_admin,
    get_supabase_client,
)
from views.appointments import show_appointments_page
from views.audit import show_audit_page
from views.dashboard import show_dashboard_page
from views.encode import show_encode_page
from views.home_dashboard import show_home_dashboard_page
from views.notifications import (
    _load_notification_read_ids,
    _load_notifications,
    _mark_notifications_read,
    render_notification_alerts,
    show_notifications_page,
)
from views.search import show_search_page

default_logo_path = Path(__file__).resolve().parent / "assets" / "boc_logo.png"
logo_path_value = os.getenv("BOC_LOGO_PATH")
BOC_LOGO_PATH = (
    Path(logo_path_value).expanduser() if logo_path_value else default_logo_path
)
if not BOC_LOGO_PATH.is_absolute():
    BOC_LOGO_PATH = Path(__file__).resolve().parents[1] / BOC_LOGO_PATH


def _brand_mark_markup(class_name):
    if not BOC_LOGO_PATH.is_file():
        return f'<span class="{class_name}">✚</span>'

    media_type = mimetypes.guess_type(BOC_LOGO_PATH.name)[0]
    if not media_type or not media_type.startswith("image/"):
        st.warning(
            "The configured Brothers of Charity logo is not a supported image. "
            "Use PNG, JPG, SVG, or WebP."
        )
        return f'<span class="{class_name}">✚</span>'

    try:
        image_data = base64.b64encode(BOC_LOGO_PATH.read_bytes()).decode("ascii")
    except OSError as error:
        st.warning(f"Unable to read the configured Brothers of Charity logo: {error}")
        return f'<span class="{class_name}">✚</span>'
    return (
        f'<img class="{class_name}" '
        f'src="data:{media_type};base64,{image_data}" '
        'alt="Brothers of Charity logo">'
    )


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
        --hfrc-page: #f2f7f6;
        --hfrc-page-deep: #003f3b;
        --hfrc-surface: #ffffff;
        --hfrc-surface-raised: #ffffff;
        --hfrc-line: #d7e5e2;
        --hfrc-text: #173632;
        --hfrc-muted: #4f6965;
        --hfrc-teal: #006d65;
        --hfrc-teal-bright: #00a394;
    }

    [data-testid="stAppViewContainer"] {
        background: var(--hfrc-page);
    }

    [data-testid="stHeader"] {
        background: #ffffff;
        border-bottom: 1px solid var(--hfrc-line);
    }

    [data-testid="stMainBlockContainer"] {
        max-width: 1440px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    body:has(.st-key-admin-login-page) [data-testid="stHeader"] {
        display: none;
    }

    body:has(.st-key-admin-login-page) [data-testid="stSidebar"],
    body:has(.st-key-admin-login-page) [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
    }

    [data-testid="stAppViewContainer"]:has(.st-key-admin-login-page),
    [data-testid="stMain"]:has(.st-key-admin-login-page) {
        min-height: 100dvh;
        height: 100dvh;
    }

    [data-testid="stMainBlockContainer"]:has(.st-key-admin-login-page) {
        width: 100%;
        max-width: none;
        min-height: 100dvh;
        height: 100dvh;
        padding: 0 !important;
    }

    [data-testid="stMainBlockContainer"]:has(.st-key-admin-login-page) > [data-testid="stVerticalBlock"] {
        min-height: 100%;
        height: 100%;
        gap: 0;
    }

    .st-key-admin-login-page {
        width: 100%;
        min-height: 100dvh;
        height: 100%;
    }

    .st-key-admin-login-page > [data-testid="stVerticalBlock"] {
        min-height: 100%;
        height: 100%;
        gap: 0;
    }

    .st-key-admin-login-page [data-testid="stHorizontalBlock"] {
        min-height: 100%;
        height: 100%;
        gap: 0;
        align-items: stretch;
    }

    .st-key-admin-login-page [data-testid="stColumn"] {
        min-height: 100%;
        height: 100%;
        padding: 0;
    }

    .st-key-admin-login-page [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) {
        position: relative;
        isolation: isolate;
        min-height: 100dvh;
        height: 100dvh;
        align-self: stretch;
        background: #ffffff;
    }

    .st-key-admin-login-page [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2)::before {
        position: fixed;
        z-index: 0;
        inset: 0 0 0 54.55%;
        background: #ffffff;
        content: "";
        pointer-events: none;
    }

    .st-key-admin-login-hero {
        position: relative;
        display: flex;
        box-sizing: border-box;
        min-height: 100dvh;
        height: 100%;
        flex-direction: column;
        justify-content: space-between;
        overflow: hidden;
        padding: clamp(2rem, 7vw, 6rem);
        background:
            radial-gradient(ellipse at 98% 20%, transparent 0 15rem, rgba(255,255,255,.055) 15.05rem 15.1rem, transparent 15.15rem 17rem, rgba(255,255,255,.04) 17.05rem 17.1rem, transparent 17.15rem),
            linear-gradient(155deg, #064c46, #003a36 76%);
    }

    .st-key-admin-login-hero > [data-testid="stVerticalBlock"] {
        position: relative;
        z-index: 1;
        min-height: calc(100dvh - 4rem);
        height: 100%;
        justify-content: space-between;
    }

    .st-key-admin-login-hero [data-testid="stMarkdownContainer"] {
        display: flex;
        min-height: calc(100dvh - 4rem);
        height: 100%;
        flex-direction: column;
        justify-content: space-between;
        color: #e6f4f1;
    }

    .st-key-admin-login-brand {
        display: flex;
        align-items: center;
        gap: .85rem;
        color: #fff;
        font-size: 1rem;
        font-weight: 700;
        line-height: 1.25;
    }

    .st-key-admin-login-brand-mark {
        display: grid;
        width: 3.2rem;
        height: 3.2rem;
        place-items: center;
        border: 1px solid rgba(255,255,255,.55);
        border-radius: .7rem;
        background: #d7d2a4;
        color: #064c46;
        font-size: 1.65rem;
    }

    img.st-key-admin-login-brand-mark {
        padding: .2rem;
        object-fit: contain;
    }

    .st-key-admin-login-hero-copy {
        max-width: 45rem;
        margin-block: auto;
        padding-block: 4rem;
    }

    .st-key-admin-login-hero-copy .login-eyebrow {
        margin-bottom: 1.6rem;
        color: #f2a477;
        font-size: .78rem;
        font-weight: 800;
        letter-spacing: .14em;
        text-transform: uppercase;
    }

    .st-key-admin-login-hero-copy h1 {
        margin: 0 0 1.35rem;
        color: #fff;
        font-family: "Roboto", "Segoe UI", sans-serif;
        font-size: clamp(2.8rem, 5vw, 4.25rem);
        font-weight: 600;
        letter-spacing: -.055em;
        line-height: 1.04;
    }

    .st-key-admin-login-hero-copy h1 em {
        color: #f2a477;
        font-family: "Roboto", "Segoe UI", sans-serif;
        font-weight: 500;
    }

    .st-key-admin-login-hero-copy .login-description {
        max-width: 38rem;
        color: #d2e7e3;
        font-size: 1.05rem;
        line-height: 1.8;
    }

    .st-key-admin-login-footer {
        color: #d2e7e3;
        font-size: .9rem;
    }

    .st-key-admin-login-panel {
        position: relative;
        z-index: 1;
        display: flex;
        box-sizing: border-box;
        min-height: 100dvh;
        height: 100dvh;
        align-items: center;
        justify-content: center;
        padding: clamp(2rem, 6vw, 5rem);
        background: #ffffff;
        color: #173632;
    }

    .st-key-admin-login-panel > [data-testid="stVerticalBlock"] {
        width: min(100%, 28rem);
        margin-inline: auto;
    }

    .st-key-admin-login-panel [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-admin-login-panel [data-testid="stVerticalBlock"] {
        background-color: #ffffff;
    }

    .st-key-admin-login-panel [data-testid="stMarkdownContainer"] {
        color: #4f6965;
    }

    .st-key-admin-login-panel .login-panel-eyebrow {
        margin-bottom: .85rem;
        color: #006d65;
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .15em;
        text-transform: uppercase;
    }

    .st-key-admin-login-panel h2 {
        margin: 0 0 .45rem;
        color: #173632;
        font-family: "Roboto", "Segoe UI", sans-serif;
        font-size: 2.1rem;
        font-weight: 600;
        letter-spacing: -.04em;
    }

    .st-key-admin-login-panel .login-panel-description {
        margin-bottom: 1.5rem;
        color: #4f6965;
    }

    .st-key-admin-login-panel [data-testid="stTextInput"] label {
        color: #173632;
        font-size: .82rem;
        font-weight: 600;
    }

    .st-key-admin-login-panel [data-testid="stTextInput"] input {
        min-height: 3rem;
        border: 1px solid #d7e5e2;
        border-radius: .65rem;
        background: #ffffff;
        color: #173632;
    }

    .st-key-admin-login-panel [data-testid="stTextInput"] input:focus {
        border-color: #43c4b5;
        box-shadow: 0 0 0 1px #43c4b5;
    }

    .st-key-admin-login-panel [data-testid="stFormSubmitButton"] {
        width: 100%;
        margin-top: .65rem;
    }

    .st-key-admin-login-panel [data-testid="stFormSubmitButton"] button {
        width: 100%;
        min-height: 3.25rem;
        border: 0;
        border-radius: .7rem;
        background: #008f83;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff;
        opacity: 1;
        box-shadow: 0 5px 12px rgba(0, 68, 63, .16);
    }

    .st-key-admin-login-panel [data-testid="stFormSubmitButton"] button:hover {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff;
    }

    .st-key-admin-login-panel .login-security-note {
        margin-top: 1rem;
        color: #4f6965;
        font-size: .72rem;
        line-height: 1.5;
        text-align: center;
    }

    @media (max-width: 640px) {
        [data-testid="stAppViewContainer"]:has(.st-key-admin-login-page),
        [data-testid="stMain"]:has(.st-key-admin-login-page),
        [data-testid="stMainBlockContainer"]:has(.st-key-admin-login-page) {
            height: auto;
            min-height: 100dvh;
        }

        .st-key-admin-login-page [data-testid="stHorizontalBlock"] {
            flex-direction: column;
            height: auto;
        }

        .st-key-admin-login-page [data-testid="stColumn"],
        .st-key-admin-login-hero,
        .st-key-admin-login-hero > [data-testid="stVerticalBlock"] {
            height: auto;
            min-height: 45vh;
        }

        .st-key-admin-login-page [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) {
            min-height: 55vh;
            height: auto;
        }

        .st-key-admin-login-page [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2)::before {
            inset: 45vh 0 0;
        }

        .st-key-admin-login-hero {
            padding: 1.75rem;
        }

        .st-key-admin-login-hero-copy {
            padding-block: 2.5rem;
        }

        .st-key-admin-login-hero-copy h1 {
            font-size: clamp(2.5rem, 11vw, 3.5rem);
        }

        .st-key-admin-login-panel {
            height: auto;
            min-height: 55vh;
            padding: 2.5rem 1.5rem;
        }
    }

    h1, h2, h3, [data-testid="stHeading"] {
        font-family: "Roboto", "Segoe UI", sans-serif;
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

    .hfrc-sidebar-brand {
        display: flex;
        align-items: center;
        gap: .55rem;
        margin: .2rem 0 .65rem;
        padding: .25rem .2rem .8rem;
        border-bottom: 1px solid rgba(220, 244, 238, .16);
        color: #ffffff;
        font-size: .74rem;
        font-weight: 650;
        line-height: 1.25;
    }

    .hfrc-sidebar-brand-mark {
        display: grid;
        width: 2.35rem;
        height: 2.35rem;
        flex: 0 0 2.35rem;
        place-items: center;
        border: 1px solid rgba(255,255,255,.55);
        border-radius: .55rem;
        background: #d7d2a4;
        color: #064c46;
        font-size: 1.25rem;
    }

    img.hfrc-sidebar-brand-mark {
        padding: .2rem;
        object-fit: contain;
    }

    .hfrc-sidebar-brand small {
        display: block;
        margin-top: .12rem;
        color: #a9d0c8;
        font-size: .58rem;
        font-weight: 400;
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: #e6f4f1;
    }

    [data-testid="stSidebar"] [data-testid="stToggle"] label {
        color: #e6f4f1;
    }

    .st-key-hfrc-sidebar-navigation [data-testid="stPageLink"] {
        margin: 0;
        padding: 0 0 .12rem;
        border-bottom: 1px solid rgba(220, 244, 238, .16);
    }

    .st-key-hfrc-sidebar-navigation [data-testid="stPageLink"] a {
        min-height: 2.25rem;
        padding: .45rem .4rem;
        border-radius: .35rem;
        color: #d7ebe7;
        font-size: .74rem;
    }

    .st-key-hfrc-sidebar-navigation [data-testid="stPageLink"] a[aria-current="page"] {
        border-left: 3px solid #f2a477;
        background: #006d65;
        color: #ffffff;
    }

    [data-testid="stSidebar"] button[kind="secondary"] {
        border-color: #1d625c;
        background: #064c46;
        color: #e6f4f1;
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: var(--hfrc-line);
        border-radius: 16px;
        background: #ffffff;
    }

    [data-testid="stBaseButton-primary"],
    button[kind="primary"] {
        min-height: 2.75rem;
        border: 1px solid var(--hfrc-teal);
        border-radius: 999px;
        background: var(--hfrc-teal);
        color: #fff;
        font-family: "Roboto", "Segoe UI", sans-serif;
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
        font-family: "Roboto", "Segoe UI", sans-serif;
        font-weight: 600;
    }

    [data-testid="stBaseButton-secondary"]:hover,
    button[kind="secondary"]:hover {
        border-color: var(--hfrc-teal-bright);
        color: var(--hfrc-text);
    }

    .st-key-admin-notifications-page [data-testid="stBaseButton-primary"]:hover,
    .st-key-admin-notifications-page [data-testid="stBaseButton-secondary"]:hover,
    .st-key-admin-activity-page [data-testid="stBaseButton-primary"]:hover,
    .st-key-admin-activity-page [data-testid="stBaseButton-secondary"]:hover {
        border-color: var(--hfrc-line);
        background: transparent;
        color: var(--hfrc-text);
        filter: none;
        transform: none;
        transition: none;
    }

    .st-key-admin-notifications-page [data-testid="stBaseButton-primary"]:hover,
    .st-key-admin-activity-page [data-testid="stBaseButton-primary"]:hover {
        border-color: var(--hfrc-teal);
        background: var(--hfrc-teal);
        color: #ffffff;
        filter: none;
        transform: none;
        transition: none;
    }

    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stDateInput"] input,
    [data-testid="stTimeInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
        border-color: var(--hfrc-line);
        border-radius: 10px;
        background: #ffffff;
        color: var(--hfrc-text);
    }

    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus {
        border-color: var(--hfrc-teal-bright);
        box-shadow: 0 0 0 1px var(--hfrc-teal-bright);
    }

    [data-testid="stTabs"] [role="tab"] {
        font-family: "Roboto", "Segoe UI", sans-serif;
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
        border-radius: 12px;
    }

    .st-key-admin-home-page {
        color: var(--hfrc-text);
    }

    [data-testid="stMainBlockContainer"]:has(.st-key-admin-home-page),
    [data-testid="stMainBlockContainer"]:has(.st-key-admin-statistics-page),
    [data-testid="stMainBlockContainer"]:has(.st-key-admin-calendar-page),
    [data-testid="stMainBlockContainer"]:has(.st-key-admin-notifications-page),
    [data-testid="stMainBlockContainer"]:has(.st-key-admin-activity-page),
    [data-testid="stMainBlockContainer"]:has(.st-key-admin-search-page) {
        max-width: none;
        padding: 1rem 0 3rem !important;
    }

    .st-key-overview-toolbar {
        max-width: 1440px;
        margin: 0 auto;
        border-bottom: 1px solid var(--hfrc-line);
        background: var(--hfrc-surface);
        padding: .75rem clamp(1.25rem, 3vw, 2.5rem);
    }

    .st-key-overview-toolbar [data-testid="stHorizontalBlock"] {
        align-items: center;
    }

    .st-key-overview-toolbar [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        min-width: 0 !important;
    }

    .st-key-overview-toolbar [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {
        flex: 1.35 1 0% !important;
    }

    .st-key-overview-toolbar [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) {
        flex: .85 1 0% !important;
    }

    .st-key-overview-toolbar [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child {
        flex: 0 0 2.5rem !important;
        width: 2.5rem !important;
    }

    .st-key-overview-toolbar [data-testid="stTextInput"],
    .st-key-overview-toolbar [data-baseweb="input"] {
        min-width: 0;
        width: 100%;
    }

    .st-key-overview-toolbar h2 {
        margin: 0;
        color: var(--hfrc-text);
        font-family: "Roboto", "Segoe UI", sans-serif;
        font-size: 1.25rem;
        font-weight: 700;
    }

    .st-key-overview-toolbar [data-testid="stCaptionContainer"] {
        margin-top: .1rem;
    }

    .st-key-overview-toolbar [data-testid="stTextInput"] input {
        min-height: 2.5rem;
        border-radius: .65rem;
        background: var(--hfrc-surface-raised);
        color: var(--hfrc-text);
    }

    .st-key-overview-toolbar [data-testid="stTextInput"] input::placeholder {
        color: #536c67;
        -webkit-text-fill-color: #536c67;
        opacity: 1;
    }

    .st-key-overview-toolbar [data-testid="stTextInput"] [data-baseweb="input"] > div:not(:has(input)) {
        background: transparent !important;
        color: var(--hfrc-teal) !important;
    }

    .st-key-overview-toolbar [data-testid="stTextInput"] [data-baseweb="input"] svg {
        color: var(--hfrc-teal) !important;
        fill: currentColor;
    }

    .st-key-overview-notifications {
        display: grid;
        min-width: 2.5rem;
        min-height: 2.5rem;
        place-items: center;
        color: var(--hfrc-text);
    }

    .st-key-overview-notifications [data-testid="stMarkdownContainer"] {
        color: var(--hfrc-text);
        font-size: 1.45rem;
        line-height: 1;
    }

    .st-key-home-dashboard-content {
        max-width: 1440px;
        margin-inline: auto;
        margin-top: 0;
        padding: 1.75rem clamp(1.25rem, 3vw, 2.5rem) 2rem;
    }

    .st-key-admin-home-page .home-eyebrow {
        color: #007b73;
        font-size: .68rem;
        font-weight: 800;
        letter-spacing: .13em;
        text-transform: uppercase;
    }

    .st-key-home-dashboard-content h2,
    .st-key-home-dashboard-content h3 {
        color: var(--hfrc-text);
    }

    .st-key-home-dashboard-content h2 {
        margin: .25rem 0;
        font-size: clamp(1.55rem, 2vw, 2rem);
        font-weight: 650;
    }

    .st-key-home-dashboard-content h3 {
        margin: .15rem 0 .75rem;
        font-size: 1rem;
        font-weight: 650;
    }

    .st-key-home-dashboard-content p,
    .st-key-home-dashboard-content [data-testid="stCaptionContainer"] {
        color: #526b66;
    }

    .st-key-home-dashboard-content [data-testid="stBaseButton-primary"],
    .st-key-home-dashboard-content a[data-testid="stPageLink-Anchor"] {
        border-radius: .65rem;
    }

    .st-key-home-encode-action [data-testid="stPageLink"] a {
        min-height: 2.8rem;
        justify-content: center;
        border: 1px solid var(--hfrc-teal);
        border-radius: .75rem;
        background: var(--hfrc-teal);
        color: #ffffff !important;
        font-weight: 700;
        box-shadow: 0 5px 12px rgba(0, 68, 63, .15);
    }

    .st-key-home-encode-action [data-testid="stPageLink"] a:hover {
        border-color: var(--hfrc-teal-bright);
        background: var(--hfrc-teal-bright);
        color: #ffffff !important;
    }

    .st-key-home-dashboard-content [data-testid="stVerticalBlockBorderWrapper"] {
        border: 1px solid #d8e6e3;
        border-radius: 15px;
        background: #ffffff;
        box-shadow: 0 2px 8px rgba(14, 58, 52, .035);
    }

    .st-key-admin-home-page [class*="st-key-home-kpi-"] [data-testid="stVerticalBlockBorderWrapper"] {
        min-height: 112px;
        padding: .9rem;
    }

    .st-key-admin-home-page .home-kpi-icon {
        display: grid;
        width: 2.6rem;
        height: 2.6rem;
        place-items: center;
        border-radius: .7rem;
        font-size: 1.2rem;
    }

    .st-key-admin-home-page .home-kpi-icon-teal {
        background: #def3f0;
        color: #008477;
    }

    .st-key-admin-home-page .home-kpi-icon-blue {
        background: #e3f0f7;
        color: #287e9b;
    }

    .st-key-admin-home-page .home-kpi-icon-coral {
        background: #fcebe4;
        color: #df7351;
    }

    .st-key-admin-home-page .home-kpi-icon-purple {
        background: #f0eafa;
        color: #8064a8;
    }

    .st-key-admin-home-page .home-kpi-value {
        color: #142f2b;
        font-size: 1.55rem;
        font-weight: 750;
        line-height: 1.2;
    }

    .st-key-home-regional-card,
    .st-key-home-appointments-card {
        margin-top: 1rem;
    }

    .st-key-admin-home-page .home-province-row {
        display: grid;
        grid-template-columns: .55rem minmax(0, 1fr) auto 2.3rem;
        align-items: center;
        gap: .55rem;
        min-height: 2.35rem;
        border-bottom: 1px solid #e8efed;
        color: #274540;
        font-size: .78rem;
    }

    .st-key-admin-home-page .home-province-dot {
        width: .45rem;
        height: .45rem;
        border-radius: 50%;
    }

    .st-key-admin-home-page .home-province-row strong {
        color: #163632;
        font-variant-numeric: tabular-nums;
    }

    .st-key-admin-home-page .home-province-percent {
        color: #526a65;
        text-align: right;
    }

    .st-key-admin-home-page .home-appointment-detail {
        color: #526a65;
        font-size: .72rem;
    }

    .st-key-admin-home-page [class*="st-key-home-appointment-row-"] {
        padding: .2rem 0;
    }

    .st-key-admin-home-page [data-testid="stPageLink"] a {
        color: #005f57 !important;
        font-weight: 600;
    }

    @media (max-width: 800px) {
        .st-key-home-dashboard-content [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap;
        }
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

st.markdown(
        """
        <style>
        :root {
            color-scheme: dark;
            --hfrc-page: #101a19;
            --hfrc-page-deep: #003f3b;
            --hfrc-surface: #182523;
            --hfrc-surface-raised: #202f2d;
            --hfrc-line: #344945;
            --hfrc-text: #e5efed;
            --hfrc-muted: #a7bbb7;
            --hfrc-teal: #008f83;
            --hfrc-teal-bright: #43c4b5;
        }

        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"] {
            background: var(--hfrc-page) !important;
            color: var(--hfrc-text);
        }

        [data-testid="stHeader"] {
            background: #182523 !important;
            border-bottom-color: var(--hfrc-line);
        }

        [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"],
        [data-testid="stMainBlockContainer"] [data-testid="stWidgetLabel"],
        [data-testid="stMainBlockContainer"] [data-testid="stCaptionContainer"],
        [data-testid="stMainBlockContainer"] [data-testid="stMetricLabel"],
        [data-testid="stMainBlockContainer"] [data-testid="stMetricValue"],
        [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] li,
        [data-testid="stMainBlockContainer"] label,
        [data-testid="stMainBlockContainer"] h1,
        [data-testid="stMainBlockContainer"] h2,
        [data-testid="stMainBlockContainer"] h3 {
            color: var(--hfrc-text) !important;
        }

        [data-testid="stMainBlockContainer"] [data-testid="stCaptionContainer"],
        [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] small {
            color: var(--hfrc-muted) !important;
        }

        [data-testid="stVerticalBlockBorderWrapper"],
        [data-testid="stExpander"],
        [data-testid="stDataFrame"],
        [data-testid="stTable"],
        [data-testid="stForm"],
        [data-testid="stMainBlockContainer"] [data-baseweb="popover"],
        [data-testid="stMainBlockContainer"] [data-baseweb="menu"] {
            border-color: var(--hfrc-line) !important;
            background-color: var(--hfrc-surface) !important;
            color: var(--hfrc-text) !important;
        }

        [data-testid="stTextInput"] input,
        [data-testid="stNumberInput"] input,
        [data-testid="stDateInput"] input,
        [data-testid="stTimeInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
            border-color: var(--hfrc-line) !important;
            background-color: var(--hfrc-surface-raised) !important;
            color: var(--hfrc-text) !important;
        }

        [data-testid="stBaseButton-secondary"],
        [data-testid="stBaseButton-secondary"] button,
        [data-testid="stDownloadButton"] button {
            border-color: var(--hfrc-line) !important;
            background-color: var(--hfrc-surface-raised) !important;
            color: var(--hfrc-text) !important;
        }

        [data-testid="stTabs"] [role="tab"],
        [data-testid="stPageLink"] a,
        a {
            color: #68d5c7;
        }

        [data-testid="stAlert"] {
            background-color: var(--hfrc-surface-raised);
        }

        .st-key-admin-home-page .st-key-home-appointments-card,
        .st-key-admin-home-page [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--hfrc-line) !important;
            background-color: var(--hfrc-surface) !important;
            color: var(--hfrc-text) !important;
        }

        .st-key-admin-home-page .st-key-overview-toolbar [data-testid="stTextInput"] input {
            background-color: var(--hfrc-surface-raised) !important;
        }

        .st-key-admin-home-page .st-key-overview-toolbar [data-testid="stTextInput"] input::placeholder {
            color: #a7bbb7 !important;
            -webkit-text-fill-color: #a7bbb7 !important;
            opacity: 1;
        }

        .st-key-admin-home-page .st-key-overview-toolbar [data-testid="stTextInput"] [data-baseweb="input"] > div:not(:has(input)) {
            background: transparent !important;
            color: #68d5c7 !important;
        }

        .st-key-admin-home-page .st-key-overview-toolbar [data-testid="stTextInput"] [data-baseweb="input"] svg {
            color: #68d5c7 !important;
            fill: currentColor;
        }

        .st-key-admin-home-page .st-key-overview-notifications {
            color: var(--hfrc-text);
        }

        .st-key-admin-home-page .st-key-overview-notifications [data-testid="stMarkdownContainer"] {
            color: var(--hfrc-text) !important;
        }

        .st-key-admin-home-page .home-eyebrow,
        .st-key-admin-home-page [data-testid="stPageLink"] a {
            color: #68d5c7 !important;
        }

        .st-key-admin-home-page .st-key-home-encode-action [data-testid="stPageLink"] a,
        .st-key-admin-home-page .st-key-home-encode-action [data-testid="stPageLink"] a:hover {
            border-color: var(--hfrc-teal-bright) !important;
            background-color: var(--hfrc-teal-bright) !important;
            color: #08201d !important;
        }

        .st-key-admin-home-page .home-province-row,
        .st-key-admin-home-page .home-province-row strong,
        .st-key-admin-home-page .home-kpi-value {
            color: var(--hfrc-text) !important;
        }

        .st-key-admin-home-page .home-province-percent,
        .st-key-admin-home-page .home-appointment-detail {
            color: var(--hfrc-muted) !important;
        }

        .st-key-admin-home-page .home-appointment-date {
            color: #68d5c7 !important;
            font-size: .78rem;
            font-weight: 700;
        }

        .st-key-admin-home-page .home-province-row {
            border-bottom-color: var(--hfrc-line);
        }

        .st-key-admin-login-page [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2),
        .st-key-admin-login-page [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2)::before,
        .st-key-admin-login-panel,
        .st-key-admin-login-panel [data-testid="stVerticalBlock"],
        .st-key-admin-login-panel [data-testid="stVerticalBlockBorderWrapper"],
        .st-key-admin-login-panel [data-testid="stForm"] {
            border-color: #d7e5e2 !important;
            background-color: #ffffff !important;
            color: #173632 !important;
        }

        .st-key-admin-login-panel [data-testid="stMarkdownContainer"],
        .st-key-admin-login-panel [data-testid="stMarkdownContainer"] p,
        .st-key-admin-login-panel [data-testid="stWidgetLabel"],
        .st-key-admin-login-panel [data-testid="stCaptionContainer"],
        .st-key-admin-login-panel label,
        .st-key-admin-login-panel h2 {
            color: #173632 !important;
        }

        .st-key-admin-login-panel .login-panel-eyebrow {
            color: #006d65 !important;
        }

        .st-key-admin-login-panel .login-panel-description,
        .st-key-admin-login-panel .login-security-note {
            color: #4f6965 !important;
        }

        .st-key-admin-login-panel [data-testid="stTextInput"] input,
        .st-key-admin-login-panel [data-testid="stTextInput"] [data-baseweb="input"] > div {
            border-color: #d7e5e2 !important;
            background-color: #ffffff !important;
            color: #173632 !important;
        }

        .st-key-admin-login-panel [data-testid="stTextInput"] input::placeholder {
            color: #6b817d !important;
            -webkit-text-fill-color: #6b817d !important;
            opacity: 1;
        }

        .st-key-admin-statistics-page {
            max-width: 1440px;
            margin-inline: auto;
            padding: 1.75rem clamp(1.25rem, 3vw, 2.5rem) 2rem;
            color: var(--hfrc-text);
        }

        .st-key-admin-statistics-page .statistics-eyebrow,
        .st-key-admin-statistics-page .statistics-card-eyebrow {
            color: #43c4b5;
            font-size: .72rem;
            font-weight: 800;
            letter-spacing: .14em;
            text-transform: uppercase;
        }

        .st-key-admin-statistics-page .statistics-eyebrow {
            margin-bottom: .55rem;
        }

        .st-key-admin-statistics-page .statistics-title {
            margin: 0 0 .4rem;
            color: var(--hfrc-text);
            font-family: "Roboto", "Segoe UI", sans-serif;
            font-size: clamp(2rem, 3vw, 2.6rem);
            font-weight: 600;
            letter-spacing: -.04em;
        }

        .st-key-admin-statistics-page .statistics-description {
            margin: 0;
            color: var(--hfrc-muted);
        }

        .st-key-admin-statistics-page .st-key-statistics-intro {
            margin: .25rem 0 1.25rem;
        }

        .st-key-admin-statistics-page .st-key-statistics-filters [data-testid="stVerticalBlockBorderWrapper"],
        .st-key-admin-statistics-page .st-key-statistics-distribution [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--hfrc-line) !important;
            border-radius: 1rem !important;
            background-color: var(--hfrc-surface) !important;
        }

        .st-key-admin-statistics-page .st-key-statistics-kpis {
            margin: 1rem 0 1.25rem;
        }

        .st-key-admin-statistics-page .st-key-statistics-kpis [data-testid="stMetric"] {
            border-color: var(--hfrc-line);
            border-radius: 1rem;
            background-color: var(--hfrc-surface);
        }

        .st-key-admin-statistics-page .st-key-statistics-distribution {
            margin-bottom: 1.25rem;
        }

        .st-key-admin-statistics-page .statistics-card-eyebrow {
            margin-bottom: .35rem;
        }

        .st-key-admin-statistics-page .statistics-status-row {
            display: grid;
            grid-template-columns: .55rem 1fr auto;
            align-items: center;
            gap: .55rem;
            margin: .8rem 0;
            color: var(--hfrc-muted);
            font-size: .82rem;
        }

        .st-key-admin-statistics-page .statistics-status-dot {
            width: .5rem;
            height: .5rem;
            border-radius: 50%;
        }

        .st-key-admin-statistics-page .statistics-status-row strong {
            color: var(--hfrc-text);
            font-weight: 600;
        }

        .st-key-admin-calendar-page,
        .st-key-admin-notifications-page,
        .st-key-admin-activity-page,
        .st-key-admin-search-page {
            max-width: 1440px;
            margin-inline: auto;
            padding: 1.75rem clamp(1.25rem, 3vw, 2.5rem) 2rem;
            color: var(--hfrc-text);
        }

        .st-key-admin-calendar-page .calendar-eyebrow,
        .st-key-admin-notifications-page .notifications-eyebrow,
        .st-key-admin-activity-page .activity-eyebrow {
            margin-bottom: .45rem;
            color: var(--hfrc-teal-bright);
            font-size: .72rem;
            font-weight: 800;
            letter-spacing: .14em;
            text-transform: uppercase;
        }

        .st-key-admin-calendar-page h1,
        .st-key-admin-notifications-page h1,
        .st-key-admin-activity-page h1 {
            margin: 0 0 .35rem;
            font-size: clamp(2rem, 3vw, 2.6rem);
            font-weight: 600;
            letter-spacing: -.04em;
        }

        .st-key-admin-calendar-page [data-testid="stMetric"] {
            min-height: 6rem;
            box-sizing: border-box;
            border-color: var(--hfrc-line);
            border-radius: 1rem;
            background: var(--hfrc-surface);
        }

        .st-key-admin-calendar-page .st-key-appointment-calendar-panel [data-testid="stVerticalBlockBorderWrapper"],
        .st-key-admin-calendar-page .st-key-appointment-selected-day-panel [data-testid="stVerticalBlockBorderWrapper"],
        .st-key-admin-calendar-page .st-key-appointment-setting [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--hfrc-line);
            border-radius: 1rem;
            background: var(--hfrc-surface);
        }

        .st-key-appointment-calendar-panel [class*="st-key-appointment_day_"] button {
            min-height: 4.5rem;
            height: 4.5rem;
            justify-content: flex-start;
            align-items: flex-start;
            white-space: pre-line;
            text-align: left;
        }

        .appointment-calendar-empty-day {
            min-height: 4.5rem;
            border: 1px solid var(--hfrc-line);
            border-radius: .5rem;
            background: var(--hfrc-page);
        }

        [class*="st-key-appointment-selected-row-"] {
            margin: .55rem 0;
            padding: .65rem .75rem;
            border-left: 3px solid var(--hfrc-teal-bright);
            border-radius: .5rem;
            background: var(--hfrc-surface-raised);
        }

        .appointment-selected-time {
            margin-bottom: .25rem;
            color: var(--hfrc-muted);
            font-size: .72rem;
        }

        .appointment-selected-name {
            color: var(--hfrc-text);
            font-weight: 700;
        }

        .appointment-selected-status {
            margin-top: .2rem;
            color: var(--hfrc-muted);
            font-size: .72rem;
        }

        .st-key-admin-calendar-page [data-testid="stForm"] {
            border: 0;
            padding: 0;
        }

        .st-key-admin-search-page .search-eyebrow {
            margin-bottom: .45rem;
            color: var(--hfrc-teal-bright);
            font-size: .72rem;
            font-weight: 800;
            letter-spacing: .14em;
            text-transform: uppercase;
        }

        .st-key-admin-search-page h1 {
            margin: 0 0 .35rem;
            font-size: clamp(2rem, 3vw, 2.6rem);
            font-weight: 600;
            letter-spacing: -.04em;
        }

        .st-key-record-search-filters [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--hfrc-line);
            border-radius: 1rem;
            background: var(--hfrc-surface);
        }

        [class*="st-key-patient-result-"] [data-testid="stExpander"],
        [class*="st-key-patient-result-"][data-testid="stExpander"] {
            margin-top: .4rem !important;
            border-color: var(--hfrc-line);
            border-radius: .75rem;
            background: var(--hfrc-surface);
        }

        [class*="st-key-patient-result-"] [data-testid="stExpander"] summary,
        [class*="st-key-patient-result-"][data-testid="stExpander"] summary {
            min-height: 2.7rem;
            padding-block: .45rem;
        }

        .st-key-patient-delete-confirmation [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: #b94a48;
            border-radius: 1rem;
            background: var(--hfrc-surface);
        }

        .st-key-selected-patient-details .patient-not-recorded {
            color: var(--hfrc-muted) !important;
            font-size: .78rem;
        }

        [data-testid="stMainBlockContainer"]:has(.st-key-admin-search-page) [data-testid="stExpander"] {
            margin-top: 1.25rem;
            border-radius: 1rem;
        }

        @media (max-width: 900px) {
            .st-key-admin-calendar-page [data-testid="stHorizontalBlock"],
            .st-key-admin-search-page [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap;
            }
        }

        [data-testid="stMainBlockContainer"]:has(.st-key-encode-page-header) {
            max-width: 1440px;
            padding: 1.75rem clamp(1.25rem, 3vw, 2.5rem) 2rem !important;
            --encode-field-border: #3a514d;
            --encode-field-focus: #43c4b5;
        }

        .st-key-encode-page-header {
            margin-bottom: 1.5rem;
        }

        .st-key-encode-page-header .encode-page-eyebrow {
            margin-bottom: .65rem;
            color: #43c4b5;
            font-size: .75rem;
            font-weight: 800;
            letter-spacing: .12em;
            text-transform: uppercase;
        }

        .st-key-encode-page-header h1 {
            margin: 0 0 .45rem;
            color: #e5efed;
            font-family: "Roboto", "Segoe UI", sans-serif;
            font-size: clamp(2rem, 3vw, 2.6rem);
            font-weight: 600;
            letter-spacing: -.04em;
        }

        .st-key-encode-page-header p {
            margin: 0;
            color: #a7bbb7;
        }

        [data-testid="stMainBlockContainer"]:has(.st-key-encode-page-header) [data-testid="stTextInput"] input,
        [data-testid="stMainBlockContainer"]:has(.st-key-encode-page-header) [data-testid="stNumberInput"] input,
        [data-testid="stMainBlockContainer"]:has(.st-key-encode-page-header) [data-testid="stDateInput"] input,
        [data-testid="stMainBlockContainer"]:has(.st-key-encode-page-header) [data-testid="stTimeInput"] input,
        [data-testid="stMainBlockContainer"]:has(.st-key-encode-page-header) [data-testid="stTextArea"] textarea,
        [data-testid="stMainBlockContainer"]:has(.st-key-encode-page-header) [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [data-testid="stMainBlockContainer"]:has(.st-key-encode-page-header) [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
            border-color: var(--encode-field-border) !important;
            border-radius: .6rem !important;
        }

        [data-testid="stMainBlockContainer"]:has(.st-key-encode-page-header) [data-testid="stTextInput"] input::placeholder,
        [data-testid="stMainBlockContainer"]:has(.st-key-encode-page-header) [data-testid="stNumberInput"] input::placeholder,
        [data-testid="stMainBlockContainer"]:has(.st-key-encode-page-header) [data-testid="stTextArea"] textarea::placeholder {
            color: #a7bbb7 !important;
            -webkit-text-fill-color: #a7bbb7 !important;
            opacity: 1;
        }

        [data-testid="stMainBlockContainer"]:has(.st-key-encode-page-header) [data-testid="stTextInput"] input:focus,
        [data-testid="stMainBlockContainer"]:has(.st-key-encode-page-header) [data-testid="stNumberInput"] input:focus,
        [data-testid="stMainBlockContainer"]:has(.st-key-encode-page-header) [data-testid="stTextArea"] textarea:focus {
            border-color: var(--encode-field-focus) !important;
            box-shadow: 0 0 0 1px var(--encode-field-focus) !important;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


def show_login_page():
    with st.container(key="admin-login-page"):
        hero_column, form_column = st.columns([1.2, 1], gap="small")
        with hero_column:
            with st.container(key="admin-login-hero"):
                login_brand_mark = _brand_mark_markup(
                    "st-key-admin-login-brand-mark"
                )
                st.markdown(
                    f"""
                    <div class="st-key-admin-login-brand">
                      {login_brand_mark}
                      <span>Brothers of Charity<br>Holy Face Center</span>
                    </div>
                    <div class="st-key-admin-login-hero-copy">
                      <div class="login-eyebrow">Holy Face Center · Region V</div>
                      <h1>Care that begins<br>with <em>good information.</em></h1>
                      <div class="login-description">
                        A unified and secure patient records system built to support
                        compassionate mental healthcare at the Brothers of Charity
                        Holy Face Center for Mental Health.
                      </div>
                    </div>
                    <div class="st-key-admin-login-footer">
                      ♡ &nbsp; Compassionate mental health care across the Bicol Region
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with form_column:
            with st.container(key="admin-login-panel"):
                st.markdown('<div class="login-panel-eyebrow">Secure admin portal</div>', unsafe_allow_html=True)
                st.markdown("## Welcome back")
                st.markdown(
                    '<div class="login-panel-description">Enter your account details to access the system.</div>',
                    unsafe_allow_html=True,
                )
                with st.form("admin_login_form", border=False):
                    email = st.text_input(
                        "Email address",
                        placeholder="Enter your email address",
                        autocomplete="username",
                    )
                    password = st.text_input(
                        "Password",
                        type="password",
                        placeholder="Enter your password",
                        autocomplete="current-password",
                    )
                    submitted = st.form_submit_button(
                        "Log in",
                        type="primary",
                        width="stretch",
                    )
                st.markdown(
                    '<div class="login-security-note">Authorized personnel only. All access and activity are monitored for patient data protection.</div>',
                    unsafe_allow_html=True,
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
    login_page = st.Page(
        show_login_page,
        title="Login",
        default=True,
    )
    legacy_encode_login_page = st.Page(
        show_login_page,
        title="Login",
        url_path="show_encode_page",
    )
    st.navigation(
        [login_page, legacy_encode_login_page],
        position="hidden",
    ).run()
    st.stop()

def show_patient_statistics_page():
    show_dashboard_page()


dashboard_page = st.Page(
    show_patient_statistics_page,
    title="Patient statistics",
    icon=":material/analytics:",
)

encode_page = st.Page(
    show_encode_page,
    title="Record encoding",
    icon=":material/person_add:",
    url_path="show_encode_page",
)

search_page = st.Page(
    show_search_page,
    title="Search Records",
    icon=":material/search:",
)

appointments_page = st.Page(
    show_appointments_page,
    title="Calendar",
    icon=":material/calendar_month:",
    url_path="appointments",
)

notifications_page = st.Page(
    lambda: show_notifications_page(appointments_page=appointments_page),
    title="Notifications",
    icon=":material/notifications:",
    url_path="notifications",
)

audit_page = st.Page(
    show_audit_page,
    title="Activity History",
    icon=":material/history:",
)


notification_unread_count = 0
notification_ids = set()
notification_read_ids = set()
notification_load_errors = []
notification_read_state_error = None
if SUPABASE_URL and SUPABASE_KEY:
    notification_client = get_supabase_client()
    if notification_client is not None:
        notification_items, notification_load_errors = _load_notifications(
            notification_client
        )
        notification_ids = {item["id"] for item in notification_items}
        try:
            notification_read_ids = _load_notification_read_ids()
        except Exception as error:
            notification_read_state_error = error
            notification_unread_count = len(notification_ids)
        else:
            notification_unread_count = len(
                notification_ids - notification_read_ids
            )


def show_overview_page():
    show_home_dashboard_page(
        statistics_page=dashboard_page,
        encode_page=encode_page,
        appointments_page=appointments_page,
        search_page=search_page,
        notifications_page=notifications_page,
    )


home_page = st.Page(
    show_overview_page,
    title="Overview",
    icon=":material/home:",
    url_path="overview",
)

pg = st.navigation(
    [
        home_page,
        encode_page,
        dashboard_page,
        appointments_page,
        search_page,
        notifications_page,
        audit_page,
    ],
    position="hidden",
)

notification_mark_read_error = None
is_notifications_page = pg == notifications_page
if is_notifications_page:
    if not st.session_state.get("notifications_page_active", False):
        unread_notification_ids = notification_ids - notification_read_ids
        if unread_notification_ids:
            try:
                _mark_notifications_read(unread_notification_ids)
            except Exception as error:
                notification_mark_read_error = error
            else:
                notification_read_ids.update(unread_notification_ids)
                notification_unread_count = 0
    st.session_state["notifications_page_active"] = True
else:
    st.session_state["notifications_page_active"] = False

with st.sidebar:
    sidebar_brand_mark = _brand_mark_markup("hfrc-sidebar-brand-mark")
    st.markdown(
        f"""
        <div class="hfrc-sidebar-brand">
          {sidebar_brand_mark}
          <span>Brothers of Charity<br><strong>Holy Face Center</strong>
          <small>for Mental Health</small></span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="hfrc-sidebar-navigation"):
        for page, label, icon in (
            (home_page, "Home", ":material/home:"),
            (dashboard_page, "Patient Statistics", ":material/analytics:"),
            (encode_page, "Add Records", ":material/person_add:"),
            (search_page, "Search Records", ":material/search:"),
            (appointments_page, "Appointments", ":material/calendar_month:"),
            (
                notifications_page,
                "Notification",
                ":material/notifications:",
            ),
            (audit_page, "Activity History", ":material/history:"),
        ):
            if page is notifications_page:
                with st.container(key="hfrc-sidebar-notification-link"):
                    st.page_link(page, label=label, icon=icon, width="stretch")
            else:
                st.page_link(page, label=label, icon=icon, width="stretch")
        if SUPABASE_URL and SUPABASE_KEY:
            render_notification_alerts()
        for source, error in notification_load_errors:
            st.warning(f"Unread notifications could not be checked for {source}.")
            with st.expander("Notification status details"):
                st.code(str(error))
        if notification_read_state_error is not None:
            st.error("Unable to load saved notification read status.")
            with st.expander("Notification read status details"):
                st.code(str(notification_read_state_error))
        if notification_mark_read_error is not None:
            st.error("Unable to mark notifications as read.")
            with st.expander("Notification read status details"):
                st.code(str(notification_mark_read_error))

    st.space("stretch")
    if st.button("Log out"):
        st.session_state["admin_authenticated"] = False
        st.session_state.pop("admin_profile", None)
        st.rerun()

pg.run()
