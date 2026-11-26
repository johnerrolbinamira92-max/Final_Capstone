import base64
from html import escape
import mimetypes
import os
import sqlite3
from pathlib import Path

import streamlit as st
from database import (
    SUPABASE_KEY,
    authenticate_admin,
    authenticate_local_admin,
    cache_local_admin_user,
    get_supabase_client,
    is_supabase_connection_available,
    is_supabase_connection_error,
    OnlineAuthenticationUnavailable,
)
from views.appointments import show_appointments_page
from views.audit import show_audit_page
from views.dashboard import show_dashboard_page
from views.encode import show_encode_page
from views.home_dashboard import show_home_dashboard_page
from views.notifications import (
    _load_notification_read_ids,
    _load_notifications,
    _load_notification_snapshot,
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
    page_icon=str(BOC_LOGO_PATH),
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

    html,
    body,
    [data-testid="stApp"],
    [data-testid="stAppViewContainer"] {
        max-width: 100vw !important;
        width: 100vw !important;
        overflow-x: clip !important;
        overscroll-behavior: none !important;
        overscroll-behavior-x: none !important;
        overscroll-behavior-y: none !important;
        touch-action: pan-y !important;
    }

    [data-testid="stMain"],
    [data-testid="stMainBlockContainer"],
    .block-container,
    [data-testid="stHorizontalBlock"] {
        overscroll-behavior: none !important;
        max-width: 100% !important;
        overflow-x: clip !important;
        box-sizing: border-box !important;
    }

    [data-testid="column"] {
        min-width: 0 !important;
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

    .st-key-admin-login-panel [data-testid="stAlert"] {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
    }

    .st-key-admin-login-panel [data-testid="stMarkdownContainer"] .login-error-message {
        margin: 8px 0 0;
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        color: #dc2626 !important;
        font-size: .85rem;
        font-weight: 500;
        text-align: center;
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
        position: relative;
        height: 100vh !important;
        max-height: 100vh !important;
        overflow: hidden !important;
        overflow-y: hidden !important;
        background: var(--hfrc-page-deep);
        border-right: 1px solid var(--hfrc-line);
    }

    [data-testid="stSidebar"] > div:first-child {
        display: flex;
        height: 100vh !important;
        max-height: 100vh !important;
        overflow: hidden !important;
        overflow-y: hidden !important;
        flex-direction: column;
        min-height: 0;
    }

    [data-testid="stSidebarHeader"] {
        position: absolute;
        z-index: 1000;
        top: 0;
        right: 0;
        left: 0;
        display: flex;
        min-height: 3rem;
        align-items: center;
        justify-content: flex-end;
        background: transparent;
    }

    [data-testid="stSidebarContent"] {
        display: flex;
        flex: 1;
        height: 100vh !important;
        max-height: 100vh !important;
        overflow: hidden !important;
        overflow-y: hidden !important;
        box-sizing: border-box;
        flex-direction: column;
        min-height: 0;
    }

    [data-testid="stSidebarUserContent"] {
        display: flex !important;
        flex: 1;
        flex-direction: column !important;
        justify-content: space-between !important;
        height: calc(100vh - 56px) !important;
        margin-top: 56px;
        min-height: 0;
        box-sizing: border-box;
        padding: 0;
    }

    .st-key-hfrc-sidebar-layout,
    .st-key-hfrc-sidebar-layout > [data-testid="stVerticalBlock"] {
        display: flex;
        flex: 1;
        flex-direction: column;
        justify-content: flex-start;
        min-height: 0;
        gap: 8px;
    }

    .st-key-hfrc-sidebar-navigation,
    .st-key-hfrc-sidebar-navigation > [data-testid="stVerticalBlock"] {
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
        gap: 4px;
    }

    .st-key-hfrc-sidebar-navigation {
        margin-top: auto !important;
        margin-bottom: auto !important;
        border-top: 1px solid rgba(255, 255, 255, 0.14);
        padding-top: 12px;
    }

    .st-key-hfrc-sidebar-logout {
        margin-top: auto !important;
        padding-bottom: 16px;
    }

    .st-key-hfrc-sidebar-status {
        position: static !important;
        margin-top: 0 !important;
        margin-bottom: 10px !important;
    }

    .hfrc-sidebar-brand {
        position: absolute;
        z-index: 1;
        top: 0;
        right: 3.5rem;
        left: 1rem;
        display: flex;
        align-items: center;
        gap: 10px;
        min-height: 3rem;
        margin: 0;
        padding: 0;
        color: #ffffff;
        font-size: .95rem;
        font-weight: 700;
        line-height: 1.15;
        pointer-events: none;
    }

    .hfrc-sidebar-brand-mark {
        display: grid;
        box-sizing: border-box;
        width: 40px;
        height: 40px;
        flex: 0 0 40px;
        place-items: center;
        border: 1px solid rgba(255,255,255,.55);
        border-radius: 8px;
        background: #d7d2a4;
        color: #064c46;
        font-size: .9rem;
    }

    img.hfrc-sidebar-brand-mark {
        padding: .1rem;
        object-fit: contain;
    }

    .hfrc-sidebar-brand strong {
        font-size: .85rem;
        font-weight: 600;
    }

    .hfrc-sidebar-brand small {
        display: block;
        margin-top: .08rem;
        color: #a9d0c8;
        font-size: .75rem;
        font-weight: 400;
    }

    [data-testid="stSidebarCollapseButton"],
    [data-testid="collapsedControl"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        pointer-events: auto !important;
        z-index: 999 !important;
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
        padding: 4px 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.12);
    }

    .st-key-hfrc-sidebar-navigation [data-testid="stPageLink"] a {
        display: flex;
        min-height: 2.5rem;
        align-items: center;
        gap: 10px;
        padding: 9px 12px;
        border-radius: 8px;
        color: #d7ebe7;
        font-size: .95rem;
        font-weight: 500;
    }

    .st-key-hfrc-sidebar-navigation [data-testid="stPageLink"] a svg {
        width: 17px;
        height: 17px;
        flex: 0 0 17px;
    }

    .st-key-hfrc-sidebar-navigation [data-testid="stPageLink"] a:hover {
        background: rgba(0, 163, 148, .22);
        color: #ffffff;
    }

    .st-key-hfrc-sidebar-navigation [data-testid="stPageLink"] a[aria-current="page"] {
        border-left: 3px solid #f2a477;
        background: #006d65;
        color: #ffffff;
        font-weight: 500;
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

    .st-key-admin-statistics-page [data-testid="stTabs"] [role="tablist"],
    .st-key-admin-notifications-page [data-testid="stTabs"] [role="tablist"],
    .st-key-admin-calendar-page [data-testid="stTabs"] [role="tablist"],
    .st-key-selected-patient-details [data-testid="stTabs"] [role="tablist"] {
        gap: 12px;
        border-bottom: 1px solid rgba(145, 171, 165, .28);
    }

    .st-key-admin-statistics-page [data-testid="stTabs"] [role="tab"],
    .st-key-admin-notifications-page [data-testid="stTabs"] [role="tab"],
    .st-key-admin-calendar-page [data-testid="stTabs"] [role="tab"],
    .st-key-selected-patient-details [data-testid="stTabs"] [role="tab"] {
        min-height: 44px;
        padding: 10px 20px !important;
        border: 1px solid rgba(255, 255, 255, .14) !important;
        border-radius: 10px !important;
        background: rgba(255, 255, 255, .05) !important;
        box-shadow: none !important;
        font-size: 15px !important;
        font-weight: 700 !important;
        cursor: pointer;
    }

    .st-key-admin-statistics-page [data-testid="stTabs"] [role="tab"]:hover,
    .st-key-admin-notifications-page [data-testid="stTabs"] [role="tab"]:hover,
    .st-key-admin-calendar-page [data-testid="stTabs"] [role="tab"]:hover,
    .st-key-selected-patient-details [data-testid="stTabs"] [role="tab"]:hover {
        border-color: rgba(45, 212, 191, .6) !important;
        background: rgba(45, 212, 191, .08) !important;
    }

    .st-key-admin-statistics-page [data-testid="stTabs"] [role="tab"][aria-selected="true"],
    .st-key-admin-notifications-page [data-testid="stTabs"] [role="tab"][aria-selected="true"],
    .st-key-admin-calendar-page [data-testid="stTabs"] [role="tab"][aria-selected="true"],
    .st-key-selected-patient-details [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        border: 1.5px solid #2dd4bf !important;
        border-bottom: 3px solid #2dd4bf !important;
        border-radius: 10px !important;
        background: #145349 !important;
        color: #ffffff !important;
        font-weight: 700 !important;
    }

    .st-key-admin-statistics-page [data-testid="stTabs"] [role="tab"] > [data-rac],
    .st-key-admin-notifications-page [data-testid="stTabs"] [role="tab"] > [data-rac],
    .st-key-admin-calendar-page [data-testid="stTabs"] [role="tab"] > [data-rac],
    .st-key-selected-patient-details [data-testid="stTabs"] [role="tab"] > [data-rac] {
        display: none !important;
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
        flex: 0 0 4.5rem !important;
        width: 4.5rem !important;
        overflow: visible !important;
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
        font-size: 26px;
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

    .st-key-overview-toolbar [data-testid="stHorizontalBlock"],
    .st-key-overview-toolbar [data-testid="stColumn"]:nth-child(2),
    .st-key-home-quick-search {
        overflow: visible !important;
    }

    .st-key-home-quick-search {
        position: relative;
        z-index: 100;
    }

    .st-key-home-quick-search [data-testid="stForm"] [data-testid="InputInstructions"] {
        display: none !important;
    }

    .st-key-home-quick-search [data-testid="stTextInput"] button {
        display: none !important;
    }

    .st-key-home-quick-search-results {
        position: absolute !important;
        top: calc(100% + 6px);
        left: auto;
        right: 0;
        z-index: 1000;
        width: 495px !important;
        max-width: 495px !important;
        min-width: 420px !important;
        max-height: 240px !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        box-sizing: border-box;
        padding: 8px 10px !important;
        border-radius: 10px !important;
        background: #0f2926;
        border: 1px solid rgba(255, 255, 255, 0.14);
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.45);
        color: #e6f4f1;
    }

    .st-key-home-quick-search-results [data-testid="stVerticalBlock"] {
        gap: 0 !important;
    }

    .st-key-home-quick-search-results .st-key-patient-results-table [data-testid="stVerticalBlockBorderWrapper"] {
        border: none !important;
        border-radius: 0 !important;
        background: transparent !important;
        box-shadow: none !important;
        padding: 0 !important;
    }

    .st-key-home-quick-search-results [data-testid="stMarkdownContainer"],
    .st-key-home-quick-search-results [data-testid="stCaptionContainer"] {
        color: #e6f4f1 !important;
    }

    .st-key-home-quick-search-close-row [data-testid="stHorizontalBlock"] {
        display: flex !important;
        justify-content: flex-end !important;
        margin-bottom: 2px !important;
        padding-top: 2px !important;
    }

    .st-key-home-quick-search-close-row [data-testid="stButton"] button {
        width: 24px !important;
        height: 24px !important;
        min-height: 24px !important;
        font-size: 0.75rem !important;
        padding: 0 !important;
        margin-bottom: 0 !important;
        border-radius: 7px;
    }

    .st-key-home-quick-search-results .st-key-patient-results-table-header {
        min-height: 28px !important;
        padding: 5px 6px !important;
    }

    .st-key-home-quick-search-results .st-key-patient-results-table-header .patient-results-table-header-label {
        min-height: 20px !important;
        font-size: 0.74rem !important;
        white-space: nowrap;
    }

    .st-key-home-quick-search-results .st-key-patient-results-table-header strong {
        font-size: 0.74rem !important;
    }

    .st-key-home-quick-search-results [class*="st-key-patient-result-row-"] {
        padding: 5px 6px !important;
    }

    .st-key-home-quick-search-results .st-key-patient-results-table [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] + [data-testid="stColumn"] {
        padding-left: 6px !important;
    }

    .st-key-home-quick-search-results [class*="st-key-patient-result-row-"] [data-testid="stColumn"]:nth-child(-n+4) [data-testid="stMarkdownContainer"],
    .st-key-home-quick-search-results [class*="st-key-patient-result-row-"] [data-testid="stColumn"]:nth-child(-n+4) [data-testid="stMarkdownContainer"] p {
        font-size: 0.78rem !important;
        font-weight: 500 !important;
        color: #e2e8f0 !important;
        line-height: 1.2 !important;
    }

    .st-key-home-quick-search-results .st-key-patient-results-table-header [data-testid="stColumn"] {
        white-space: nowrap !important;
    }

    .st-key-home-quick-search-results .st-key-patient-results-table-header [data-testid="stHorizontalBlock"],
    .st-key-home-quick-search-results [class*="st-key-patient-result-row-"] [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        gap: 6px !important;
    }

    .st-key-home-quick-search-results .st-key-patient-results-table-header [data-testid="stColumn"],
    .st-key-home-quick-search-results [class*="st-key-patient-result-row-"] [data-testid="stColumn"] {
        box-sizing: border-box !important;
    }

    .st-key-home-quick-search-results .st-key-patient-results-table-header [data-testid="stColumn"]:nth-child(1),
    .st-key-home-quick-search-results [class*="st-key-patient-result-row-"] [data-testid="stColumn"]:nth-child(1) {
        flex: 0 0 112px !important;
        width: 112px !important;
        min-width: 112px !important;
        max-width: 112px !important;
    }

    .st-key-home-quick-search-results .st-key-patient-results-table-header [data-testid="stColumn"]:nth-child(2),
    .st-key-home-quick-search-results [class*="st-key-patient-result-row-"] [data-testid="stColumn"]:nth-child(2) {
        flex: 1 1 135px !important;
        min-width: 135px !important;
        max-width: none !important;
    }

    .st-key-home-quick-search-results .st-key-patient-results-table-header [data-testid="stColumn"]:nth-child(3),
    .st-key-home-quick-search-results [class*="st-key-patient-result-row-"] [data-testid="stColumn"]:nth-child(3) {
        flex: 0 0 54px !important;
        width: 54px !important;
        min-width: 54px !important;
        max-width: 54px !important;
    }

    .st-key-home-quick-search-results .st-key-patient-results-table-header [data-testid="stColumn"]:nth-child(4),
    .st-key-home-quick-search-results [class*="st-key-patient-result-row-"] [data-testid="stColumn"]:nth-child(4) {
        flex: 0 0 36px !important;
        width: 36px !important;
        min-width: 36px !important;
        max-width: 36px !important;
    }

    .st-key-home-quick-search-results .st-key-patient-results-table-header [data-testid="stColumn"]:nth-child(5),
    .st-key-home-quick-search-results [class*="st-key-patient-result-row-"] [data-testid="stColumn"]:nth-child(5) {
        flex: 0 0 72px !important;
        width: 72px !important;
        min-width: 72px !important;
        max-width: 72px !important;
    }

    .st-key-home-quick-search-results [class*="st-key-patient-result-row-"] [data-testid="stColumn"]:nth-child(-n+4) [data-testid="stMarkdownContainer"],
    .st-key-home-quick-search-results [class*="st-key-patient-result-row-"] [data-testid="stColumn"]:nth-child(-n+4) [data-testid="stMarkdownContainer"] p {
        display: block !important;
        max-width: 100% !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        white-space: nowrap !important;
    }

    .st-key-home-quick-search-results .st-key-patient-results-table [data-testid="stButton"] button {
        min-height: 24px !important;
        padding: 2px 8px !important;
        font-size: 0.72rem !important;
        white-space: nowrap !important;
    }

    .st-key-overview-toolbar [data-testid="stTextInput"] [data-baseweb="input"] > div:not(:has(input)) {
        background: transparent !important;
        color: var(--hfrc-teal) !important;
    }

    .st-key-overview-toolbar [data-testid="stTextInput"] [data-baseweb="input"] svg {
        color: var(--hfrc-teal) !important;
        fill: currentColor;
    }

    .st-key-overview-notification-control,
    .st-key-overview-notifications {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        width: auto;
        height: 40px;
        min-width: 0;
        min-height: 40px;
        overflow: visible !important;
        color: #ffffff;
    }

    .st-key-overview-notification-control {
        width: 40px !important;
        min-width: 40px !important;
        margin-left: auto !important;
    }

    .st-key-overview-notification-control .overview-notification-badge {
        position: absolute !important;
        top: -4px !important;
        right: -4px !important;
        z-index: 20 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        min-width: 18px !important;
        height: 18px !important;
        padding: 0 4px !important;
        border: 2px solid #0b2421 !important;
        border-radius: 999px !important;
        background: #ef4444 !important;
        color: #ffffff !important;
        box-sizing: border-box !important;
        font-size: 0.68rem !important;
        font-weight: 700 !important;
        line-height: 1 !important;
        white-space: nowrap !important;
        pointer-events: none !important;
    }

    .st-key-overview-notification-control [data-testid="stElementContainer"]:has(.overview-notification-badge) {
        position: absolute !important;
        top: 0 !important;
        right: 0 !important;
        width: 0 !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: visible !important;
        pointer-events: none !important;
    }

    .st-key-overview-toolbar [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child,
    .st-key-overview-notification-control,
    .st-key-overview-notification-control .st-key-overview-notifications,
    .st-key-overview-notification-control [data-testid="stPopover"],
    .st-key-overview-notification-control [data-testid="stPopoverButton"],
    .st-key-overview-notifications[data-testid="stPopover"],
    .st-key-overview-notifications [data-testid="stPopover"],
    [data-testid="stPopover"].st-key-overview-notifications,
    .st-key-overview-notifications [data-testid="stPopoverButton"],
    [data-testid="stPopoverButton"].st-key-overview-notifications {
        overflow: visible !important;
    }

    .st-key-overview-notification-control [data-testid="stPopover"] > div,
    .st-key-overview-notifications [data-testid="stPopover"] > div,
    [data-testid="stPopover"].st-key-overview-notifications > div {
        position: relative !important;
        overflow: visible !important;
    }

    .st-key-overview-notification-control [data-testid="stPopover"] > div > [data-testid="stPopoverButton"],
    .st-key-overview-notifications [data-testid="stPopover"] > div > [data-testid="stPopoverButton"],
    [data-testid="stPopover"].st-key-overview-notifications > div > [data-testid="stPopoverButton"] {
        position: relative !important;
        overflow: visible !important;
    }

    .st-key-overview-notification-control [data-testid="stPopoverButton"],
    .st-key-overview-notifications [data-testid="stPopoverButton"],
    [data-testid="stPopoverButton"].st-key-overview-notifications {
        width: 40px !important;
        height: 40px !important;
        padding: 0 !important;
        position: relative !important;
        overflow: visible !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 0 !important;
        border-radius: 10px !important;
        background: #122c29 !important;
        border: 1px solid rgba(255, 255, 255, 0.14) !important;
        color: #ffffff !important;
        box-shadow: none !important;
        box-sizing: border-box !important;
        font-size: 1.25rem !important;
    }

    .st-key-overview-notification-control [data-testid="stPopoverButton"]:focus,
    .st-key-overview-notification-control [data-testid="stPopoverButton"]:focus-visible,
    .st-key-overview-notification-control [data-testid="stPopoverButton"]:active,
    .st-key-overview-notifications [data-testid="stPopoverButton"]:focus,
    .st-key-overview-notifications [data-testid="stPopoverButton"]:focus-visible,
    .st-key-overview-notifications [data-testid="stPopoverButton"]:active,
    [data-testid="stPopoverButton"].st-key-overview-notifications:focus,
    [data-testid="stPopoverButton"].st-key-overview-notifications:focus-visible,
    [data-testid="stPopoverButton"].st-key-overview-notifications:active {
        outline: none !important;
        box-shadow: none !important;
    }

    .st-key-overview-notification-control [data-testid="stPopoverButton"] > div > div[aria-hidden="true"],
    .st-key-overview-notifications [data-testid="stPopoverButton"] > div > div[aria-hidden="true"],
    [data-testid="stPopoverButton"].st-key-overview-notifications > div > div[aria-hidden="true"] {
        display: none !important;
    }

    .st-key-overview-notification-control [data-testid="stPopoverButton"] [data-testid="stIconMaterial"],
    .st-key-overview-notifications [data-testid="stPopoverButton"] [data-testid="stIconMaterial"] {
        color: #ffffff !important;
        font-size: 20px !important;
    }

    [data-testid="stPopoverBody"]:has(.st-key-overview-callback-popover-content) {
        box-sizing: border-box !important;
        width: 320px !important;
        max-width: 90vw !important;
        max-height: 235px !important;
        overflow-y: auto !important;
        padding: 12px 14px !important;
        border: 1px solid rgba(255, 255, 255, 0.14) !important;
        background: #0b211e !important;
        scroll-behavior: smooth;
        -webkit-overflow-scrolling: touch;
    }

    .st-key-overview-callback-popover-content {
        box-sizing: border-box;
        width: 100% !important;
        max-width: 100% !important;
        padding: 0 !important;
        border: none !important;
        border-radius: 0 !important;
        background: transparent !important;
        box-shadow: none !important;
        color: #e6f4f1;
    }

    .st-key-overview-callback-popover-content [data-testid="stMarkdownContainer"],
    .st-key-overview-callback-popover-content [data-testid="stCaptionContainer"] {
        color: #e6f4f1 !important;
    }

    .st-key-overview-callback-popover-content .callback-popover-empty {
        padding: .8rem .25rem;
        color: #a9c7c1;
        font-size: .85rem;
        text-align: center;
    }

    .st-key-overview-callback-request-list [class*="st-key-overview-callback-request-"] {
        margin-bottom: 4px !important;
    }

    [data-testid="stPopoverBody"] button,
    [data-testid="stPopoverBody"] button > div,
    [data-testid="stPopoverBody"] [data-testid="stMarkdownContainer"],
    [data-testid="stPopoverBody"] button p {
        display: flex !important;
        flex-direction: column !important;
        align-items: flex-start !important;
        justify-content: center !important;
        text-align: left !important;
        width: 100% !important;
        margin-left: 0 !important;
    }

    [data-testid="stPopoverBody"] button {
        padding: 8px 14px !important;
    }

    .st-key-overview-callback-request-list [class*="st-key-overview-callback-request-"] button {
        min-height: 52px !important;
        border: 1px solid #31534f !important;
        border-radius: 11px !important;
        background: #17332f !important;
        color: #f5f1e7 !important;
        box-shadow: none !important;
        white-space: normal !important;
    }

    .st-key-overview-callback-request-list [class*="st-key-overview-callback-request-"] button:hover {
        border-color: #527a73 !important;
        background: #1b3c37 !important;
    }

    .st-key-overview-callback-request-list [class*="st-key-overview-callback-request-"] button:focus-visible {
        outline: 2px solid #6ecfc1 !important;
        outline-offset: 2px !important;
    }

    .st-key-overview-callback-request-list [class*="st-key-overview-callback-request-"] button p {
        margin: 0;
        overflow-wrap: anywhere;
    }

    .st-key-overview-callback-request-list [class*="st-key-overview-callback-request-"] button p:first-child {
        color: #f5f1e7;
        font-size: .8rem;
        font-weight: 700;
    }

    .st-key-overview-callback-request-list [class*="st-key-overview-callback-request-"] button p:last-child {
        margin-top: 5px;
        color: #c1d5d0;
        font-size: .7rem;
        line-height: 1.45;
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

    .st-key-admin-home-page .st-key-home-kpi-row [data-testid="stVerticalBlockBorderWrapper"] {
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        text-align: left !important;
        min-height: 82px !important;
        padding: 16px 20px !important;
    }

    .st-key-admin-home-page .st-key-home-kpi-row [data-testid="stVerticalBlockBorderWrapper"] > [data-testid="stVerticalBlock"] {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: flex-start;
    }

    .st-key-admin-home-page .st-key-home-kpi-row [data-testid="stMarkdownContainer"]:has(.home-kpi-content) {
        margin: 0 !important;
        padding: 0 !important;
    }

    .st-key-admin-home-page .st-key-home-kpi-row [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        gap: 10px !important;
    }

    .st-key-admin-home-page .st-key-home-kpi-row [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        min-width: 0 !important;
    }

    .st-key-admin-home-page .home-kpi-icon {
        display: flex;
        width: 2rem;
        height: 2rem;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        background: #ffffff !important;
        border-radius: .7rem;
        font-size: 1rem;
    }

    .st-key-admin-home-page .home-kpi-icon-teal {
        background: #def3f0;
        color: #008477;
    }

    .st-key-admin-home-page .home-kpi-icon-blue {
        background: #e3f0f7;
        color: #287e9b;
    }

    .st-key-admin-home-page .home-kpi-icon-purple {
        background: #f0eafa;
        color: #8064a8;
    }

    .st-key-admin-home-page .home-kpi-icon-slate {
        background: #edf0f2;
        color: #75828c;
    }

    .st-key-admin-home-page [data-testid="stMarkdownContainer"]:has(.home-kpi-content) {
        display: flex;
        width: 100%;
        justify-content: flex-start;
    }

    .st-key-admin-home-page .home-kpi-content {
        display: flex;
        align-items: center;
        gap: 10px;
        width: 100%;
    }

    .st-key-admin-home-page .home-kpi-copy {
        flex: 1 !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 3px;
        min-width: 0;
        text-align: center !important;
    }

    .st-key-admin-home-page .home-kpi-value {
        color: #142f2b;
        font-size: 1.65rem !important;
        font-weight: 700 !important;
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1.2 !important;
        white-space: nowrap;
    }

    .st-key-admin-home-page .home-kpi-label {
        color: #526b66;
        font-size: 0.85rem !important;
        font-weight: 600;
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1.2 !important;
        white-space: nowrap;
    }

    .st-key-home-regional-card,
    .st-key-home-appointments-card {
        margin-top: 1rem;
        height: 440px;
        box-sizing: border-box;
    }

    .st-key-home-appointments-card {
        display: flex;
        flex-direction: column;
    }

    .st-key-home-appointments-card > [data-testid="stVerticalBlock"] {
        display: flex;
        flex-direction: column;
        height: 100%;
        min-height: 0;
    }

    .st-key-admin-home-page .st-key-home-appointments-heading-row {
        margin-top: 8px !important;
        margin-bottom: 6px !important;
    }

    .st-key-admin-home-page .st-key-home-appointments-heading-row [data-testid="stHorizontalBlock"] {
        display: flex !important;
        align-items: center !important;
        justify-content: space-between !important;
    }

    .st-key-admin-home-page .st-key-home-upcoming-names-toggle {
        margin-top: -10px !important;
        padding-top: 0 !important;
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
            --hfrc-muted: #94a3b8;
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

        .st-key-admin-home-page .home-kpi-label {
            color: #cbd5e1 !important;
        }

        .st-key-admin-home-page .home-province-percent,
        .st-key-admin-home-page .home-appointment-detail {
            color: var(--hfrc-muted) !important;
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
        .st-key-admin-statistics-page .statistics-card-eyebrow,
        .st-key-admin-home-page .statistics-eyebrow {
            color: #43c4b5;
            font-size: .72rem;
            font-weight: 800;
            letter-spacing: .14em;
            text-transform: uppercase;
        }

        .st-key-admin-statistics-page .statistics-eyebrow,
        .st-key-admin-home-page .statistics-eyebrow {
            margin-bottom: .55rem;
        }

        .st-key-admin-statistics-page .statistics-title,
        .st-key-admin-home-page .statistics-title {
            margin: 0 0 .4rem;
            color: var(--hfrc-text);
            font-family: "Roboto", "Segoe UI", sans-serif;
            font-size: clamp(2rem, 3vw, 2.6rem);
            font-weight: 600;
            letter-spacing: -.04em;
        }

        .st-key-admin-statistics-page .statistics-description,
        .st-key-admin-home-page .statistics-description {
            margin: 0;
            color: var(--hfrc-muted);
        }

        .st-key-admin-statistics-page .st-key-statistics-intro,
        .st-key-admin-home-page .st-key-home-page-intro {
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
            grid-template-columns: .5rem minmax(0, 1fr) auto;
            align-items: center;
            gap: .4rem;
            margin: .65rem 0;
            padding-inline: 0;
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

        .st-key-admin-search-page {
            padding-bottom: .75rem;
        }

        .st-key-admin-search-results {
            max-width: 1440px;
            margin-inline: auto;
            padding-inline: clamp(1.25rem, 3vw, 2.5rem);
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

        .st-key-admin-calendar-page [class*="st-key-appointment-icon-reschedule-"] button,
        .st-key-admin-calendar-page [class*="st-key-appointment-icon-cancel-"] button {
            box-sizing: border-box;
            width: 36px !important;
            min-width: 36px !important;
            min-height: 36px !important;
            height: 36px !important;
            padding: 0 !important;
            border-radius: 8px !important;
        }

        .st-key-admin-calendar-page [class*="st-key-appointment-icon-cancel-"] button,
        .st-key-admin-calendar-page [class*="st-key-appointment-icon-cancel-"] button * {
            border-color: rgba(239, 68, 68, .45) !important;
            color: #ef4444 !important;
        }

        .st-key-admin-calendar-page [class*="st-key-appointment-confirm-cancel-"] button,
        .st-key-admin-calendar-page [class*="st-key-appointment-keep-"] button,
        .st-key-admin-calendar-page [class*="st-key-appointment-confirm-reschedule-"] button,
        .st-key-admin-calendar-page [class*="st-key-appointment-close-reschedule-"] button {
            box-sizing: border-box;
            width: 100% !important;
            min-width: 96px !important;
            white-space: nowrap !important;
            text-overflow: clip !important;
            overflow: visible !important;
        }

        .st-key-admin-calendar-page [class*="st-key-appointment-confirm-cancel-"] button *,
        .st-key-admin-calendar-page [class*="st-key-appointment-keep-"] button *,
        .st-key-admin-calendar-page [class*="st-key-appointment-confirm-reschedule-"] button *,
        .st-key-admin-calendar-page [class*="st-key-appointment-close-reschedule-"] button * {
            white-space: nowrap !important;
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

        .st-key-admin-search-page .st-key-record-name-lookup [data-testid="stTextInput"] {
            position: relative !important;
        }

        .st-key-admin-search-page .st-key-record-name-lookup [data-testid="stTextInput"]::before {
            position: absolute;
            top: 50%;
            left: 14px;
            z-index: 2;
            width: 15px;
            height: 15px;
            transform: translateY(-50%);
            background: url("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='15'%20height='15'%20viewBox='0%200%2024%2024'%20fill='none'%20stroke='rgba(203%2C224%2C220%2C0.55)'%20stroke-width='1.8'%20stroke-linecap='round'%20stroke-linejoin='round'%3E%3Ccircle%20cx='10.8'%20cy='10.8'%20r='6.6'/%3E%3Cpath%20d='m15.7%2015.7%204.1%204.1'/%3E%3C/svg%3E") center / 15px 15px no-repeat;
            content: "";
            pointer-events: none;
        }

        .st-key-admin-search-page .st-key-record-name-lookup [data-testid="stTextInput"]:has(input:focus)::before {
            background-image: url("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='15'%20height='15'%20viewBox='0%200%2024%2024'%20fill='none'%20stroke='rgba(226%2C242%2C239%2C0.85)'%20stroke-width='1.8'%20stroke-linecap='round'%20stroke-linejoin='round'%3E%3Ccircle%20cx='10.8'%20cy='10.8'%20r='6.6'/%3E%3Cpath%20d='m15.7%2015.7%204.1%204.1'/%3E%3C/svg%3E");
        }

        .st-key-admin-search-page .st-key-record-name-lookup [data-testid="stTextInput"] input {
            padding-left: 38px !important;
        }

        .st-key-patient-case-search-code [data-testid="stHorizontalBlock"] {
            gap: 6px !important;
            align-items: center;
        }

        .st-key-patient-results-table-hint [data-testid="stCaptionContainer"] {
            color: var(--hfrc-teal-bright) !important;
        }

        .st-key-patient-results-table [data-testid="stVerticalBlockBorderWrapper"] {
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, .12) !important;
            border-radius: 12px !important;
            background: #112926;
            padding: 0 !important;
        }

        .st-key-patient-results-table [data-testid="stVerticalBlock"] {
            gap: 0 !important;
        }

        .st-key-patient-results-table-header {
            display: flex;
            align-items: center;
            min-height: 44px;
            box-sizing: border-box;
            border-bottom: 1px solid rgba(45, 212, 191, .25);
            background: #0c201d;
            padding: 12px 16px;
            color: #99f6e4;
        }

        .st-key-patient-results-table-header [data-testid="stHorizontalBlock"] {
            width: 100%;
        }

        .st-key-patient-results-table-header .patient-results-table-header-label {
            display: flex;
            min-height: 44px;
            align-items: center;
        }

        .st-key-patient-results-table-header [data-testid="stMarkdownContainer"],
        .st-key-patient-results-table-header [data-testid="stMarkdownContainer"] p,
        .st-key-patient-results-table-header strong {
            color: #99f6e4 !important;
        }

        [class*="st-key-patient-result-row-"] {
            border-bottom: 1px solid rgba(255, 255, 255, .08);
            padding: .35rem .75rem .15rem;
        }

        .st-key-patient-results-table [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] + [data-testid="stColumn"] {
            border-left: 1px solid rgba(255, 255, 255, .08);
            padding-left: .65rem;
        }

        .st-key-patient-results-table [data-testid="stMarkdownContainer"] p {
            margin: 0;
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

        [role="dialog"]:has(.st-key-selected-patient-details) {
            background: #0c201d !important;
            color: #e6f4f1 !important;
        }

        [role="dialog"]:has(.st-key-selected-patient-details) *,
        .st-key-selected-patient-details,
        .st-key-selected-patient-details * {
            color: #e6f4f1 !important;
        }

        [class*="intake-section-"] [data-testid="stVerticalBlockBorderWrapper"],
        [class*="intake-section-"][data-testid="stVerticalBlockBorderWrapper"],
        .st-key-selected-patient-details [class*="intake-section-"] [data-testid="stVerticalBlockBorderWrapper"],
        .st-key-selected-patient-details [class*="intake-section-"][data-testid="stVerticalBlockBorderWrapper"] {
            box-sizing: border-box;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
            border-radius: 12px !important;
            padding: 18px 20px !important;
            background: #0f2926 !important;
        }

        .st-key-selected-patient-details .patient-field-label {
            display: block;
            margin-bottom: .35rem;
            color: #94b8b3 !important;
            font-size: 12.5px !important;
            font-weight: 700;
            letter-spacing: .04em;
            line-height: 1.35;
            text-transform: none;
        }

        .st-key-selected-patient-details .patient-empty-value {
            color: #6b8e89 !important;
            font-size: 18px;
            line-height: 1.5;
        }

        .st-key-selected-patient-details .patient-field-value {
            margin-bottom: .5rem;
            box-sizing: border-box;
            padding: 10px 12px;
            border: 1px solid rgba(167, 243, 208, .14);
            border-radius: 8px;
            background: #102824;
            color: #ffffff !important;
            font-size: 15.5px !important;
            font-weight: 500;
            line-height: 1.5;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
        }

        .st-key-selected-patient-details [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: #355a53 !important;
            background: #102824 !important;
        }

        .st-key-selected-patient-details [data-testid="stButton"] button {
            border-color: #355a53 !important;
            background: #102824 !important;
            color: #e6f4f1 !important;
        }

        .st-key-selected-patient-details [data-testid="stButton"] button * {
            color: #e6f4f1 !important;
        }

        .st-key-selected-patient-details [class*="st-key-delete_selected_patient_"] button {
            box-sizing: border-box;
            width: 38px !important;
            min-width: 38px !important;
            min-height: 38px !important;
            height: 38px !important;
            padding: 0 !important;
            border-radius: 8px !important;
        }

        .st-key-selected-patient-details [class*="st-key-view-intake-section-header-"] [data-testid="stHorizontalBlock"],
        .st-key-selected-patient-details [data-testid="stHorizontalBlock"]:has(.view-record-section-title) {
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            flex-wrap: nowrap !important;
            gap: 12px !important;
            padding-bottom: 10px !important;
            margin-bottom: 14px !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
        }

        .st-key-selected-patient-details [data-testid="stElementContainer"]:has(.view-record-section-title) {
            flex: 1 1 auto !important;
            min-width: 0 !important;
        }

        .st-key-selected-patient-details .view-record-section-title {
            color: #e6f4f1 !important;
            font-size: 1.02rem !important;
            font-weight: 650 !important;
            line-height: 1.35 !important;
        }

        .st-key-selected-patient-details [class*="st-key-view-record-edit-open-"] {
            flex: 0 0 auto !important;
            width: auto !important;
            min-width: 0 !important;
        }

        .st-key-selected-patient-details [class*="st-key-view-record-edit-open-"] button {
            min-height: 29px !important;
            height: 29px !important;
            padding: 4px 12px !important;
            border: 1px solid rgba(45, 212, 191, 0.35) !important;
            border-radius: 999px !important;
            background: rgba(20, 184, 166, 0.08) !important;
            color: #99f6e4 !important;
            font-size: 0.78rem !important;
            font-weight: 500 !important;
            line-height: 1 !important;
            box-shadow: none !important;
            transition: background 120ms ease, border-color 120ms ease !important;
        }

        .st-key-selected-patient-details [class*="st-key-view-record-edit-open-"] button * {
            color: #99f6e4 !important;
        }

        .st-key-selected-patient-details [class*="st-key-view-record-edit-open-"] button:hover:not(:disabled) {
            border-color: #2dd4bf !important;
            background: rgba(20, 184, 166, 0.18) !important;
            color: #ccfbf1 !important;
        }

        .st-key-selected-patient-details [class*="st-key-view-intake-section-actions-"] [data-testid="stHorizontalBlock"],
        .st-key-selected-patient-details [data-testid="stHorizontalBlock"]:has([class*="st-key-view-record-edit-save-"]) {
            justify-content: flex-end !important;
            gap: 8px !important;
            margin-top: 14px !important;
        }

        .st-key-selected-patient-details [class*="st-key-view-record-edit-cancel-"] button,
        .st-key-selected-patient-details [class*="st-key-view-record-edit-save-"] button {
            min-height: 30px !important;
            height: 30px !important;
            padding: 4px 14px !important;
            border-radius: 999px !important;
            font-size: 0.8rem !important;
            line-height: 1 !important;
            box-shadow: none !important;
        }

        .st-key-selected-patient-details [class*="st-key-view-record-edit-cancel-"] button {
            border: 1px solid rgba(255, 255, 255, 0.18) !important;
            background: transparent !important;
            color: #cbd5e1 !important;
            font-weight: 500 !important;
        }

        .st-key-selected-patient-details [class*="st-key-view-record-edit-cancel-"] button * {
            color: #cbd5e1 !important;
        }

        .st-key-selected-patient-details [class*="st-key-view-record-edit-cancel-"] button:hover {
            border-color: rgba(255, 255, 255, 0.32) !important;
            background: rgba(255, 255, 255, 0.06) !important;
        }

        .st-key-selected-patient-details [class*="st-key-view-record-edit-save-"] button {
            border: 1px solid #14b8a6 !important;
            background: #14b8a6 !important;
            color: #042f2e !important;
            font-weight: 600 !important;
        }

        .st-key-selected-patient-details [class*="st-key-view-record-edit-save-"] button * {
            color: #042f2e !important;
        }

        .st-key-selected-patient-details [class*="st-key-view-record-edit-save-"] button:hover {
            border-color: #2dd4bf !important;
            background: #2dd4bf !important;
            color: #042f2e !important;
        }

        .st-key-selected-patient-details [class*="st-key-delete_selected_patient_"] [data-testid="stButton"] button,
        .st-key-selected-patient-details [class*="st-key-delete_selected_patient_"] [data-testid="stButton"] button * {
            border-color: rgba(239, 68, 68, .45) !important;
            background: rgba(239, 68, 68, .12) !important;
            color: #ef4444 !important;
        }

        .st-key-selected-patient-details [data-testid="stDataFrame"],
        .st-key-selected-patient-details [data-testid="stDataFrame"] *,
        .st-key-selected-patient-details [data-testid="stDataEditor"],
        .st-key-selected-patient-details [data-testid="stDataEditor"] * {
            --gdg-bg-cell: #102824 !important;
            --gdg-bg-cell-medium: #17342f !important;
            --gdg-bg-group-header: #17342f !important;
            --gdg-bg-group-header-hovered: #164b45 !important;
            --gdg-bg-header: #17342f !important;
            --gdg-bg-header-has-focus: #164b45 !important;
            --gdg-bg-header-hovered: #164b45 !important;
            --gdg-bg-search-result: #3a625d !important;
            --gdg-border-color: #6f9c95 !important;
            --gdg-horizontal-border-color: #6f9c95 !important;
            --gdg-header-bottom-border-color: #8bb5ad !important;
            --gdg-text-dark: #ffffff !important;
            --gdg-text-medium: #e2f5f1 !important;
            --gdg-text-light: #c5e3dd !important;
            --gdg-text-header: #ffffff !important;
            --gdg-text-header-selected: #ffffff !important;
            --gdg-text-group-header: #ffffff !important;
            --gdg-accent-color: #7ce0d2 !important;
            --gdg-accent-fg: #0c201d !important;
            --gdg-accent-light: #164b45 !important;
            --gdg-bg-icon-header: #17342f !important;
            --gdg-fg-icon-header: #ffffff !important;
            --gdg-link-color: #9af0e3 !important;
        }

        .st-key-selected-patient-details [data-testid="stDataFrame"],
        .st-key-selected-patient-details [data-testid="stDataEditor"] {
            border: 1px solid #355a53 !important;
            border-radius: .5rem;
            background: #102824 !important;
        }

        .st-key-selected-patient-details [data-testid="stTable"],
        .st-key-selected-patient-details [data-testid="stTable"] table,
        .st-key-selected-patient-details [data-testid="stTable"] th,
        .st-key-selected-patient-details [data-testid="stTable"] td {
            border-color: #355a53 !important;
            background: #102824 !important;
            color: #ffffff !important;
        }

        .st-key-selected-patient-details [data-testid="stTable"] table {
            border-collapse: collapse;
        }

        .st-key-selected-patient-details [data-testid="stTable"] th,
        .st-key-selected-patient-details [data-testid="stTable"] td {
            border-bottom: 1px solid #355a53 !important;
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
                      <h1>Care That Begins<br>With <em>Good Information.</em></h1>
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
                st.markdown('<div class="login-panel-eyebrow">Secure Admin Portal</div>', unsafe_allow_html=True)
                st.markdown("## Welcome Back")
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
                login_error = None
                if submitted:
                    try:
                        admin = authenticate_admin(email, password)
                    except OnlineAuthenticationUnavailable:
                        try:
                            admin = authenticate_local_admin(email, password)
                        except PermissionError:
                            login_error = (
                                "Supabase is unavailable and the local admin "
                                "credentials could not be verified. Configure a "
                                "bootstrap account in the private .env file or "
                                "connect online and sign in once."
                            )
                        except (sqlite3.Error, ValueError):
                            login_error = (
                                "Supabase is unavailable and the local admin "
                                "credential cache could not be read. Restore the "
                                "local database or reconnect to sign in online."
                            )
                        else:
                            st.session_state["admin_authenticated"] = True
                            st.session_state["admin_auth_mode"] = "offline"
                            st.session_state["admin_profile"] = admin
                            st.rerun()
                    except PermissionError as error:
                        login_error = str(error)
                    except Exception as error:
                        login_error = f"Unable to authenticate with Supabase: {error}"
                    else:
                        try:
                            cache_local_admin_user(
                                email,
                                admin["display_name"],
                                admin["role"],
                                password,
                            )
                        except sqlite3.Error:
                            st.session_state["offline_cache_warning"] = (
                                "Signed in online, but the local offline "
                                "credential cache could not be updated."
                            )
                        st.session_state["admin_authenticated"] = True
                        st.session_state["admin_auth_mode"] = "online"
                        st.session_state["admin_profile"] = admin
                        st.rerun()
                if login_error is not None:
                    st.markdown(
                        f'<p class="login-error-message">{escape(login_error)}</p>',
                        unsafe_allow_html=True,
                    )


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

offline_cache_warning = st.session_state.pop("offline_cache_warning", None)
if offline_cache_warning:
    st.warning(offline_cache_warning)

def show_patient_statistics_page():
    show_dashboard_page()


dashboard_page = st.Page(
    show_patient_statistics_page,
    title="Patient Statistics",
    icon=":material/analytics:",
)

encode_page = st.Page(
    show_encode_page,
    title="Record Encoding",
    icon=":material/person_add:",
    url_path="show_encode_page",
)

search_page = st.Page(
    show_search_page,
    title="Record Management",
    icon=":material/search:",
    url_path="record_management",
)

appointments_page = st.Page(
    show_appointments_page,
    title="Calendar",
    icon=":material/calendar_month:",
    url_path="appointments",
)

notifications_page = st.Page(
    lambda: show_notifications_page(appointments_page=appointments_page),
    title="Callback Requests",
    icon=":material/notifications:",
    url_path="notifications",
)

audit_page = st.Page(
    show_audit_page,
    title="Activity History",
    icon=":material/history:",
)


notification_read_ids = set()
notification_items = []
notification_load_errors = []
notification_read_state_error = None
notification_data_available = False
notification_data_error = None
notification_snapshot_synced_at = None
notification_feed_is_cached = False
supabase_connection_online = is_supabase_connection_available()
if supabase_connection_online and SUPABASE_KEY:
    notification_client = get_supabase_client()
    if notification_client is not None:
        notification_items, notification_load_errors = _load_notifications(
            notification_client
        )
        if any(
            is_supabase_connection_error(error)
            for _, error in notification_load_errors
        ):
            supabase_connection_online = False
            is_supabase_connection_available.clear()
            notification_load_errors = []
            notification_items = []
        else:
            notification_data_available = not any(
                source == "patient help requests"
                for source, _ in notification_load_errors
            )

if not notification_data_available:
    try:
        notification_snapshot = _load_notification_snapshot()
    except (sqlite3.Error, ValueError) as error:
        notification_data_error = error
    else:
        if notification_snapshot is not None:
            notification_items, notification_snapshot_synced_at = (
                notification_snapshot
            )
            notification_data_available = True
            notification_feed_is_cached = True

try:
    notification_read_ids = _load_notification_read_ids()
except Exception as error:
    notification_read_state_error = error

callback_requests_error = None
unread_callback_requests = None
if notification_read_state_error is not None:
    callback_requests_error = "Unable to load saved notification read status."
elif not notification_data_available:
    if notification_data_error is not None:
        callback_requests_error = (
            f"Unable to load callback requests: {notification_data_error}"
        )
    elif any(
        source == "patient help requests"
        for source, _ in notification_load_errors
    ):
        callback_requests_error = "Unable to load callback requests."
    else:
        callback_requests_error = (
            "Callback requests are unavailable while offline."
        )
else:
    unread_callback_requests = [
        item
        for item in notification_items
        if item.get("kind") == "help_request"
        and item.get("status") == "Pending"
        and item["id"] not in notification_read_ids
    ]


@st.fragment(run_every="15s")
def render_offline_status_badge():
    if not is_supabase_connection_available():
        st.badge(
            "Offline Mode — Local Records Active",
            icon=":material/wifi_off:",
            color="orange",
        )


def show_overview_page():
    show_home_dashboard_page(
        statistics_page=dashboard_page,
        appointments_page=appointments_page,
        search_page=search_page,
        notifications_page=notifications_page,
        unread_callback_requests=unread_callback_requests,
        callback_requests_error=callback_requests_error,
        callback_requests_cached_at=notification_snapshot_synced_at,
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

with st.sidebar:
    with st.container(key="hfrc-sidebar-layout"):
        with st.container(key="hfrc-sidebar-header"):
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
        st.markdown(
            '<div style="height: 155px;"></div>',
            unsafe_allow_html=True,
        )
        with st.container(key="hfrc-sidebar-status"):
            render_offline_status_badge()
        with st.container(key="hfrc-sidebar-navigation"):
            for page, label, icon in (
                (home_page, "Home", ":material/home:"),
                (dashboard_page, "Patient Statistics", ":material/analytics:"),
                (search_page, "Record Management", ":material/manage_search:"),
                (appointments_page, "Appointments", ":material/calendar_month:"),
                (
                    notifications_page,
                    "Callback Requests",
                    ":material/notifications:",
                ),
                (audit_page, "Activity History", ":material/history:"),
            ):
                st.page_link(page, label=label, icon=icon, width="stretch")
            render_notification_alerts(
                cached_items=(
                    notification_items if notification_feed_is_cached else None
                ),
                cached_read_ids=(
                    notification_read_ids
                    if notification_feed_is_cached
                    and notification_read_state_error is None
                    else None
                ),
            )
            for source, error in notification_load_errors:
                st.warning(
                    f"Unread notifications could not be checked for {source}."
                )
                with st.expander("Notification status details"):
                    st.code(str(error))
            if notification_read_state_error is not None:
                st.error("Unable to load saved notification read status.")
                with st.expander("Notification read status details"):
                    st.code(str(notification_read_state_error))
        st.markdown(
            '<div style="height: 85px;"></div>',
            unsafe_allow_html=True,
        )
        if st.button("Log out", key="hfrc-sidebar-logout"):
            st.session_state["admin_authenticated"] = False
            st.session_state.pop("admin_auth_mode", None)
            st.session_state.pop("admin_profile", None)
            st.rerun()

pg.run()
