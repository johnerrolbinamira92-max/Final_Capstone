from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from database import get_supabase_client

MANILA = ZoneInfo("Asia/Manila")
STATUSES = ("new", "contact-attempted", "scheduled", "closed", "stored")
PAGE_SIZE = 500


def _load_entries(client):
    records = []
    offset = 0
    while True:
        response = (
            client.table("vent_entries")
            .select("*")
            .order("created_at", desc=True)
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        records.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return records


def _format_datetime(value):
    if not value:
        return "Not provided"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(MANILA).strftime("%b %d, %Y at %I:%M %p")
    except (TypeError, ValueError):
        return str(value)


def _save_update(client, entry_id, status, notes):
    response = (
        client.table("vent_entries")
        .update({"status": status, "staff_notes": notes.strip() or None})
        .eq("id", entry_id)
        .select("id")
        .execute()
    )
    if not response.data:
        raise RuntimeError("No matching helpline entry was updated.")


def show_helpline_page():
    st.title("Helpline Requests")
    st.write(
        "Review private vent entries and respond to consented callback requests. "
        "Access is limited to authorized administrators."
    )

    client = get_supabase_client()
    if client is None:
        st.stop()

    try:
        entries = _load_entries(client)
    except Exception:
        st.error(
            "Unable to load helpline submissions. Verify the Supabase project, "
            "run helpline/supabase/schema.sql, and confirm the server-side key."
        )
        return

    help_count = sum(entry.get("kind") == "support" for entry in entries)
    new_count = sum(entry.get("status") == "new" for entry in entries)
    self_release_count = sum(entry.get("kind") == "self-release" for entry in entries)

    metric_one, metric_two, metric_three, metric_four = st.columns(4)
    metric_one.metric("Active entries", len(entries))
    metric_two.metric("Help requests", help_count)
    metric_three.metric("New requests", new_count)
    metric_four.metric("Self-release", self_release_count)

    filter_one, filter_two = st.columns(2)
    with filter_one:
        status_filter = st.selectbox(
            "Status",
            ("all",) + STATUSES,
            key="helpline_status_filter",
        )
    with filter_two:
        kind_filter = st.selectbox(
            "Entry type",
            ("all", "support", "self-release"),
            format_func=lambda value: {
                "all": "All entries",
                "support": "Help requested",
                "self-release": "Self-release only",
            }[value],
            key="helpline_kind_filter",
        )

    visible = [
        entry
        for entry in entries
        if (status_filter == "all" or entry.get("status") == status_filter)
        and (kind_filter == "all" or entry.get("kind") == kind_filter)
    ]

    if not visible:
        st.info("No helpline entries match the selected filters.")
        return

    for entry in visible:
        entry_id = str(entry["id"])
        reference = entry.get("reference_code") or entry_id
        entry_kind = entry.get("kind")
        kind_label = "Help requested" if entry_kind == "support" else "Self-release"
        status = entry.get("status") or "new"

        with st.expander(f"{reference} | {kind_label} | {status}"):
            st.caption(
                f"Submitted {_format_datetime(entry.get('created_at'))} | "
                f"Expires {_format_datetime(entry.get('expires_at'))}"
            )
            st.subheader("Private narrative")
            st.write(entry.get("message") or "No narrative was provided.")

            if entry_kind == "support":
                name_col, age_col, contact_col = st.columns(3)
                name_col.markdown(f"**Name**  \n{entry.get('name') or 'Not provided'}")
                age_col.markdown(f"**Age**  \n{entry.get('age') or 'Not provided'}")
                contact = entry.get("contact_number") or "Not provided"
                contact_col.markdown(f"**Contact number**  \n{contact}")
                st.markdown(
                    f"**Requested callback:** {_format_datetime(entry.get('scheduled_for'))}"
                )
                st.caption(
                    "Consent to contact: Yes"
                    if entry.get("consent_to_contact")
                    else "Consent to contact: Not recorded"
                )

            with st.form(f"helpline-update-{entry_id}"):
                current_status = status if status in STATUSES else "new"
                selected_status = st.selectbox(
                    "Workflow status",
                    STATUSES,
                    index=STATUSES.index(current_status),
                )
                staff_notes = st.text_area(
                    "Private staff notes",
                    value=entry.get("staff_notes") or "",
                )
                submitted = st.form_submit_button("Save helpline update")

            if submitted:
                try:
                    _save_update(client, entry_id, selected_status, staff_notes)
                except Exception as error:
                    st.error(f"Unable to save the helpline update: {error}")
                else:
                    st.success(f"{reference} was updated.")
                    st.rerun()


if __name__ == "__main__":
    show_helpline_page()
