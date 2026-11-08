from __future__ import annotations

import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from database import (
    booked_slots,
    create_entry,
    delete_entry,
    ensure_anonymous_user,
    session_client,
    visitor_entries,
)
from logic import (
    MANILA,
    SLOT_TIMES,
    available_dates,
    combine_schedule,
    format_slot,
    normalize_phone,
    valid_phone,
    valid_schedule,
    validate_message,
)
from styles import apply_styles

APP_DIR = Path(__file__).resolve().parent
LOGO = APP_DIR / "assets" / "holy-face-logo.png"
LOGO_DATA = base64.b64encode(LOGO.read_bytes()).decode("ascii")
PHONE = "0920-691-5015"
logger = logging.getLogger("holy_face_helpline")

st.set_page_config(
    page_title="Holy Face Center Helpline",
    page_icon=str(LOGO),
    layout="wide",
    initial_sidebar_state="collapsed",
)


def rerun_with_notice(kind: str, message: str) -> None:
    st.session_state.flash = {"kind": kind, "message": message}
    st.rerun()


def show_flash() -> None:
    flash = st.session_state.pop("flash", None)
    if not flash:
        return
    if flash["kind"] == "success":
        st.success(flash["message"])
    else:
        st.error(flash["message"])


def header() -> None:
    st.markdown(
        f"""
        <header class="hf-site-header">
          <div class="hf-header-inner">
            <div class="hf-brand">
              <img src="data:image/png;base64,{LOGO_DATA}" alt="Holy Face Center logo">
              <div>
                <strong>BROTHERS OF CHARITY</strong>
                <span>Holy Face Center for Mental Health</span>
              </div>
            </div>
            <a class="hf-call" href="tel:{PHONE.replace('-', '')}">Call {PHONE}</a>
          </div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def hero() -> None:
    st.markdown(
        """
        <section class="hf-hero">
          <div class="hf-kicker">A private space to be heard</div>
          <h1>You don’t have to carry it <em>alone.</em></h1>
          <p>
            Share what’s on your mind, without judgment. Keep it as a private
            release or ask a mental health professional to reach out.
          </p>
        </section>
        <section class="hf-crisis">
          <strong>Need urgent help?</strong>
          <p>
            This form is not monitored as an emergency service. If you may hurt
            yourself or someone else, call <strong>911</strong> or go to the
            nearest emergency room now.
          </p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def submit_visitor_entry(client: Any, kind: str) -> None:
    if st.session_state.pop("clear_vent_message", False):
        st.session_state.vent_message = ""

    st.subheader("What’s weighing on you today?")
    st.caption("Write freely. There is no word limit, and your words remain private.")
    message = st.text_area(
        "Vent-out space",
        height=260,
        placeholder="I’ve been feeling…",
        key="vent_message",
    )

    name = ""
    age = 18
    contact = ""
    selected_schedule = None
    consent = False

    if kind == "support":
        st.markdown("### Request a confidential callback")
        st.caption("These details are visible only to authorized administrators.")
        col_name, col_age = st.columns([3, 1])
        with col_name:
            name = st.text_input("Name", placeholder="Your full name")
        with col_age:
            age = st.number_input("Age", min_value=7, max_value=120, step=1)
        contact = st.text_input("Contact number", placeholder="09XX XXX XXXX")

        minimum_date, maximum_date = available_dates()
        selected_date = st.date_input(
            "Preferred callback date",
            min_value=minimum_date,
            max_value=maximum_date,
        )

        if selected_date.weekday() >= 5:
            st.warning("The center accepts callback schedules from Monday to Friday.")
            available_slots = []
        else:
            try:
                reserved = booked_slots(client, selected_date)
                reserved_local = {
                    item.astimezone(MANILA).replace(second=0, microsecond=0)
                    for item in reserved
                }
                now = datetime.now(MANILA)
                available_slots = [
                    slot
                    for slot in SLOT_TIMES
                    if combine_schedule(selected_date, slot) > now
                    and combine_schedule(selected_date, slot) not in reserved_local
                ]
            except Exception:
                st.error("Current schedule availability could not be loaded. Please refresh.")
                available_slots = []

        if available_slots:
            selected_time = st.selectbox(
                "Available time",
                available_slots,
                format_func=format_slot,
            )
            selected_schedule = combine_schedule(selected_date, selected_time)
        else:
            st.info("No callback times are available for this date.")

        consent = st.checkbox(
            "I give Holy Face Center permission to securely collect and use my "
            "name, age, contact number, message, and schedule to respond to this request."
        )
    else:
        st.info(
            "No personal details are needed. Your release will remain available "
            "in this private session and retained securely for up to 30 days."
        )

    submitted = st.button(
        "Send my help request" if kind == "support" else "Store my private entry",
        type="primary",
        use_container_width=True,
    )
    if not submitted:
        return

    message_error = validate_message(message)
    if message_error:
        st.error(message_error)
        return

    if kind == "support":
        if len(name.strip()) < 2:
            st.error("Please enter your name.")
            return
        if not valid_phone(contact):
            st.error("Enter a valid Philippine mobile number.")
            return
        if not selected_schedule or not valid_schedule(selected_schedule):
            st.error("Choose an available weekday schedule.")
            return
        if not consent:
            st.error("Permission is required before the center can contact you.")
            return

        # Recheck immediately before insert. The unique database index is the
        # final guard if two visitors choose the same slot simultaneously.
        try:
            if selected_schedule.astimezone(MANILA).replace(
                second=0, microsecond=0
            ) in {
                item.astimezone(MANILA).replace(second=0, microsecond=0)
                for item in booked_slots(client, selected_schedule.date())
            }:
                st.error("That schedule was just reserved. Please choose another time.")
                return
        except Exception:
            st.error("We could not confirm the schedule. Please try again.")
            return

    payload: dict[str, Any] = {
        "kind": kind,
        "message": message.strip(),
        "name": name.strip() if kind == "support" else None,
        "age": int(age) if kind == "support" else None,
        "contact_number": normalize_phone(contact) if kind == "support" else None,
        "scheduled_for": selected_schedule.isoformat() if selected_schedule else None,
        "consent_to_contact": consent if kind == "support" else False,
    }

    try:
        saved = create_entry(client, payload)
    except Exception as error:
        logger.exception("Helpline entry submission failed")
        detail = str(error).lower()
        if "duplicate" in detail or "unique" in detail:
            st.error("That schedule was just reserved. Please choose another time.")
        else:
            st.error(
                "We could not securely save your entry. Please try again or call the center."
            )
        return

    st.session_state.clear_vent_message = True
    rerun_with_notice(
        "success",
        f"Your entry was stored securely. Reference: {saved['reference_code']}. "
        "It will expire after 30 days.",
    )


def visitor_history(client: Any) -> None:
    st.subheader("Your recent entries")
    st.caption(
        "Only entries belonging to this anonymous Supabase session are shown. "
        "They expire after 30 days."
    )
    try:
        entries = visitor_entries(client)
    except Exception:
        st.error("Your private entries could not be loaded.")
        return

    if not entries:
        st.info("No active entries are associated with this session.")
        return

    for entry in entries:
        created = datetime.fromisoformat(entry["created_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(entry["expires_at"].replace("Z", "+00:00"))
        days_left = max(1, (expires - datetime.now(expires.tzinfo)).days + 1)
        label = "Help requested" if entry["kind"] == "support" else "Private release"
        with st.container(border=True):
            st.markdown(f'<span class="hf-badge">{label}</span>', unsafe_allow_html=True)
            st.write(entry["message"])
            st.caption(
                f"{entry['reference_code']} · {created.astimezone(MANILA):%b %d, %Y %I:%M %p} "
                f"· {days_left} days left"
            )
            if entry.get("scheduled_for"):
                schedule = datetime.fromisoformat(
                    entry["scheduled_for"].replace("Z", "+00:00")
                )
                st.write(f"Callback: **{schedule.astimezone(MANILA):%b %d, %Y at %I:%M %p}**")
            if st.button("Remove my entry", key=f"delete-{entry['id']}"):
                try:
                    delete_entry(client, entry["id"])
                    rerun_with_notice("success", "Your entry was removed.")
                except Exception:
                    st.error("The entry could not be removed.")


def visitor_app() -> None:
    try:
        client = session_client("visitor_supabase_client")
        ensure_anonymous_user(client)
    except Exception as error:
        st.error(str(error))
        st.stop()

    show_flash()
    share_tab, history_tab, privacy_tab = st.tabs(
        ["Share privately", "Your entries", "Privacy & safety"]
    )
    with share_tab:
        kind_label = st.radio(
            "What would feel right after sharing?",
            ("I need help", "I don’t need help"),
            horizontal=True,
        )
        kind = "support" if kind_label == "I need help" else "self-release"
        submit_visitor_entry(client, kind)
    with history_tab:
        visitor_history(client)
    with privacy_tab:
        st.markdown(
            """
            ### How your information is handled

            - Entries are retained for up to **30 days**.
            - Narratives and contact details are protected by Supabase Row Level Security.
            - Only authorized administrators can access help-request contact information.
            - Self-release entries do not collect a name, age, or contact number.
            - You may remove an entry associated with your current anonymous session.

            This website is not an emergency response service. Call **911** in an emergency.
            """
        )



apply_styles(bool(st.session_state.get("dark_theme", False)))
header()
control_space, theme_control = st.columns([5, 1], vertical_alignment="center")
with theme_control:
    st.toggle("Dark theme", key="dark_theme")
hero()
visitor_app()

st.markdown("---")
st.caption(
    "Holy Face Center for Mental Health · Nazareth Complex, Zone 6, "
    "Tabiguian, Tabaco City · Brothers of Charity Philippine Jurisdiction, Inc."
)
