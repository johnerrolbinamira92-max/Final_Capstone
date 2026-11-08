from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()


def _setting(name: str) -> str | None:
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except (FileNotFoundError, KeyError):
        pass
    return os.getenv(name)


def connection_settings() -> tuple[str, str]:
    url = _setting("SUPABASE_URL")
    key = _setting("SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError(
            "Supabase is not configured. Add SUPABASE_URL and SUPABASE_ANON_KEY "
            "to .streamlit/secrets.toml or the environment."
        )
    return url, key


def new_client() -> Client:
    url, key = connection_settings()
    return create_client(url, key)


def session_client(session_key: str = "visitor_supabase_client") -> Client:
    if session_key not in st.session_state:
        st.session_state[session_key] = new_client()
    return st.session_state[session_key]


def ensure_anonymous_user(client: Client) -> str:
    user_id = st.session_state.get("visitor_user_id")
    if user_id:
        return str(user_id)

    response = client.auth.sign_in_anonymously()
    if not response.user:
        raise RuntimeError(
            "Anonymous sign-ins are disabled. Enable them in Supabase "
            "Authentication → Providers → Anonymous Sign-Ins."
        )
    st.session_state.visitor_user_id = response.user.id
    return response.user.id



def booked_slots(client: Client, selected_date: date) -> set[datetime]:
    result = client.rpc(
        "get_booked_slots",
        {"requested_date": selected_date.isoformat()},
    ).execute()
    return {
        datetime.fromisoformat(row["scheduled_for"].replace("Z", "+00:00"))
        for row in (result.data or [])
    }


def create_entry(client: Client, payload: dict[str, Any]) -> dict[str, Any]:
    """Submit through the allowlisted server function instead of direct table insert."""
    result = client.rpc(
        "submit_vent_entry",
        {
            "p_kind": payload["kind"],
            "p_message": payload["message"],
            "p_name": payload.get("name"),
            "p_age": payload.get("age"),
            "p_contact_number": payload.get("contact_number"),
            "p_scheduled_for": payload.get("scheduled_for"),
            "p_consent_to_contact": payload.get("consent_to_contact", False),
        },
    ).execute()
    if not result.data:
        raise RuntimeError("Supabase did not return the saved entry.")
    return dict(result.data[0])


def visitor_entries(client: Client) -> list[dict[str, Any]]:
    result = (
        client.table("vent_entries")
        .select("id,reference_code,kind,message,scheduled_for,expires_at,created_at,status")
        .order("created_at", desc=True)
        .execute()
    )
    return list(result.data or [])


def delete_entry(client: Client, entry_id: str) -> None:
    client.table("vent_entries").delete().eq("id", entry_id).execute()
