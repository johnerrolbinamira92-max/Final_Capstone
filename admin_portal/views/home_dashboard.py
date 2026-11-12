from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

from database import get_local_connection, get_supabase_client
from views.appointments import (
    CALENDAR_STATUSES,
    _appointment_summary_counts,
    _format_time,
    _load_appointments,
    _load_calendar_appointments,
)
from views.map_utils import (
    load_map_features,
    location_key as _base_location_key,
    render_choropleth_svg,
)

BICOL_MAP_FILE = (
    Path(__file__).resolve().parents[1] / "data" / "bicol_provinces.geojson"
)
BICOL_PROVINCES = (
    "Albay",
    "Camarines Norte",
    "Camarines Sur",
    "Catanduanes",
    "Masbate",
    "Sorsogon",
)
PROVINCE_ALIASES = {
    "albay province": "albay",
    "camarines norte province": "camarines norte",
    "cam norte": "camarines norte",
    "north camarines": "camarines norte",
    "northern camarines": "camarines norte",
    "camarines sur province": "camarines sur",
    "cam sur": "camarines sur",
    "south camarines": "camarines sur",
    "southern camarines": "camarines sur",
    "catanduanes province": "catanduanes",
    "masbate province": "masbate",
    "sorsogon province": "sorsogon",
}
PROVINCE_COLORS = (
    "#00786e",
    "#00958a",
    "#59aaa0",
    "#e97954",
    "#f2a278",
    "#c8cbc5",
)


def _submit_overview_search(search_page):
    query = st.session_state.get("home_search_query", "").strip()
    if search_page is not None:
        st.session_state["patient_search_query"] = query
        st.switch_page(search_page)


def _render_overview_toolbar(
    search_page,
    notifications_page=None,
    notifications_unread=False,
):
    with st.container(key="overview-toolbar"):
        if notifications_unread:
            st.markdown(
                """
                <style>
                .st-key-overview-notifications [data-testid="stPageLink"] a {
                    position: relative;
                }
                .st-key-overview-notifications [data-testid="stPageLink"] a::after {
                    content: "";
                    position: absolute;
                    top: .38rem;
                    right: .38rem;
                    width: .38rem;
                    height: .38rem;
                    border-radius: 50%;
                    background: #e53935;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
        title_column, search_column, notification_column = st.columns(
            [1.35, 0.85, 0.08], vertical_alignment="center"
        )
        with title_column:
            st.markdown("## Overview")
            st.caption("Regional patient care, organized in one place.")
        with search_column:
            with st.form(key="overview-search-form", border=False):
                with st.container(
                    horizontal=True,
                    wrap=False,
                    vertical_alignment="center",
                    gap="small",
                ):
                    st.text_input(
                        "Search patient records",
                        placeholder="Search patient name, ID, or location...",
                        icon=":material/search:",
                        label_visibility="collapsed",
                        key="home_search_query",
                        width="stretch",
                    )
                    submitted = st.form_submit_button(
                        "Search",
                        key="overview-search-submit",
                        help="Open Search Records",
                        width="content",
                        disabled=search_page is None,
                    )
            if submitted:
                _submit_overview_search(search_page)
        with notification_column:
            with st.container(key="overview-notifications"):
                if notifications_page is not None:
                    st.page_link(
                        notifications_page,
                        label=" ",
                        icon=":material/notifications:",
                        help="Open notifications",
                    )
                else:
                    st.markdown(":material/notifications:")


def _province_key(value):
    key = _base_location_key(value)
    return PROVINCE_ALIASES.get(key, key)


def _get_patient_records():
    conn = get_local_connection()
    try:
        return pd.read_sql_query("SELECT province, status FROM patients", conn)
    finally:
        conn.close()


def _load_dashboard_appointments():
    client = get_supabase_client()
    if client is None:
        return None
    appointments = _load_appointments(client)
    calendar_appointments = _load_calendar_appointments(client, appointments)
    return appointments, calendar_appointments


def _format_count(value):
    return f"{value:,}"


def _render_province_breakdown(chart_data, total_bicol, dark_mode=False):
    chart_column, province_column = st.columns([0.85, 1.15])
    donut = (
        alt.Chart(chart_data)
        .mark_arc(innerRadius=56, outerRadius=92)
        .encode(
            theta=alt.Theta("Patients:Q", stack=True),
            color=alt.Color(
                "Province:N",
                scale=alt.Scale(
                    domain=list(BICOL_PROVINCES),
                    range=list(PROVINCE_COLORS),
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("Province:N", title="Province"),
                alt.Tooltip("Patients:Q", title="Patient records"),
            ],
        )
        .properties(height=230)
    )
    center_total = (
        alt.Chart(pd.DataFrame({"value": [total_bicol]}))
        .mark_text(
            font="DM Sans",
            fontSize=20,
            fontWeight="bold",
            color="#e5efed" if dark_mode else "#143633",
        )
        .encode(text=alt.Text("value:Q", format="~s"))
    )
    center_label = (
        alt.Chart(pd.DataFrame({"label": ["Total"]}))
        .mark_text(
            dy=20,
            font="DM Sans",
            fontSize=10,
            color="#a7bbb7" if dark_mode else "#738987",
        )
        .encode(text="label:N")
    )
    chart = (donut + center_total + center_label).properties(
        background="#182523" if dark_mode else "#ffffff"
    )
    with chart_column:
        st.altair_chart(
            chart,
            width="stretch",
            theme=None,
            alt="Patient record share across six Bicol provinces",
        )
    with province_column:
        for index, row in chart_data.iterrows():
            province = row["Province"]
            count = int(row["Patients"])
            percent = round(count / total_bicol * 100) if total_bicol else 0
            st.markdown(
                f"""
                <div class="home-province-row">
                  <span class="home-province-dot" style="background:{PROVINCE_COLORS[index]}"></span>
                  <span class="home-province-name">{province}</span>
                  <strong>{count:,}</strong>
                  <span class="home-province-percent">{percent}%</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.caption(
        f"{_format_count(total_bicol)} recognized Bicol patient records"
    )


def _render_bicol_map(province_counts):
    features = load_map_features(BICOL_MAP_FILE)
    st.html(
        render_choropleth_svg(
            province_counts,
            features,
            _province_key,
            "Bicol Region patient records by province",
            dark_mode=True,
        )
    )
    st.caption("Hover over a province to see its count. The map works offline.")


def _render_appointments(appointments, today, appointments_page, error=None):
    with st.container(border=True, key="home-appointments-card"):
        title_column, link_column = st.columns([1.5, 1], vertical_alignment="center")
        with title_column:
            st.markdown(
                f'<div class="home-eyebrow">Today · {today.strftime("%B")} {today.day}</div>',
                unsafe_allow_html=True,
            )
            st.markdown("### Upcoming appointments")
        with link_column:
            if appointments_page is not None:
                st.page_link(
                    appointments_page,
                    label="Full calendar",
                    icon=":material/arrow_forward:",
                    width="content",
                )

        if error is not None:
            st.warning("Upcoming appointments could not be loaded.")
            with st.expander("Technical details"):
                st.code(str(error))
        elif appointments is None:
            st.info("Appointment details require a connection to Supabase.")
        else:
            active = appointments[
                appointments["approval_status"].isin(CALENDAR_STATUSES)
            ].copy()
            dates = pd.to_datetime(active["requested_date"], errors="coerce")
            active = active[dates.dt.date >= today]
            active["_sort_date"] = pd.to_datetime(
                active["requested_date"], errors="coerce"
            )
            upcoming = active.sort_values(
                ["_sort_date", "requested_time_slot"],
                kind="stable",
                na_position="last",
            ).head(3)

            if upcoming.empty:
                st.caption("No upcoming appointments are scheduled.")
            else:
                for index, appointment in enumerate(
                    upcoming.to_dict(orient="records")
                ):
                    visit_date = pd.to_datetime(
                        appointment["requested_date"], errors="coerce"
                    )
                    date_label = (
                        "Today"
                        if visit_date.date() == today
                        else visit_date.strftime("%b %d")
                    )
                    time_label = _format_time(
                        appointment.get("requested_time_slot")
                    )
                    with st.container(key=f"home-appointment-row-{index}"):
                        time_column, icon_column, detail_column, arrow_column = (
                            st.columns([1.05, 0.45, 2.4, 0.25], vertical_alignment="center")
                        )
                        time_column.caption(date_label)
                        icon_column.markdown(":material/event:")
                        detail_column.markdown(
                            f"**{escape(str(appointment['patient_name']))}**  \n"
                            f"<span class=\"home-appointment-detail\">{escape(time_label)} · "
                            f"{escape(str(appointment['approval_status']))}</span>",
                            unsafe_allow_html=True,
                        )
                        if appointments_page is not None:
                            arrow_column.page_link(
                                appointments_page,
                                icon=":material/chevron_right:",
                                help="Open appointment schedule",
                            )

        if appointments_page is not None:
            st.page_link(
                appointments_page,
                label="Add appointment",
                icon=":material/add:",
                width="stretch",
                query_params={"focus": "schedule"},
            )


def show_home_dashboard_page(
    *,
    statistics_page=None,
    encode_page=None,
    appointments_page=None,
    search_page=None,
    notifications_page=None,
    notifications_unread=False,
):
    today = datetime.now(ZoneInfo("Asia/Manila")).date()
    try:
        records = _get_patient_records()
        records["province_key"] = records["province"].map(_province_key)
        records["status"] = (
            records["status"].fillna("Alive").str.strip().str.title()
        )
        bicol_records = records[
            records["province_key"].isin(
                {_province_key(province) for province in BICOL_PROVINCES}
            )
        ].copy()
        province_counts = (
            bicol_records["province_key"]
            .value_counts()
            .reindex(
                [_province_key(province) for province in BICOL_PROVINCES],
                fill_value=0,
            )
        )
    except Exception as error:
        st.error(f"Unable to load the home dashboard: {error}")
        return
    appointment_error = None
    appointments = None
    calendar_appointments = None
    try:
        appointment_data = _load_dashboard_appointments()
        if appointment_data is not None:
            appointments, calendar_appointments = appointment_data
    except Exception as error:
        appointment_error = error

    pending_count = 0
    today_count = 0
    if calendar_appointments is not None:
        counts = _appointment_summary_counts(calendar_appointments, today)
        today_count = counts["scheduled_today"]
        pending_count = counts["pending"]
    greeting_period = (
        "Good morning"
        if datetime.now(ZoneInfo("Asia/Manila")).hour < 12
        else "Good afternoon"
        if datetime.now(ZoneInfo("Asia/Manila")).hour < 18
        else "Good evening"
    )

    with st.container(key="admin-home-page"):
        _render_overview_toolbar(
            search_page,
            notifications_page,
            notifications_unread,
        )
        with st.container(key="home-dashboard-content"):
            intro_column, encode_column = st.columns(
                [3, 1], vertical_alignment="top"
            )
            with intro_column:
                st.markdown(
                    f'<div class="home-eyebrow">{today.strftime("%A, %d %B %Y").upper()}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"## {greeting_period}, Administrator.")
                st.write("Here’s what’s happening at Holy Face Center today.")
            with encode_column:
                if encode_page is not None:
                    with st.container(key="home-encode-action"):
                        st.page_link(
                            encode_page,
                            label="Encode new record",
                            icon=":material/add:",
                            width="stretch",
                        )

            kpi_data = [
                (
                    "Total patient records",
                    _format_count(len(records)),
                    "All archived records",
                    "♙",
                    "teal",
                ),
                (
                    "Alive patients",
                    _format_count(int((records["status"] == "Alive").sum())),
                    "Current administrative status",
                    "♡",
                    "blue",
                ),
                (
                    "Appointments today",
                    _format_count(today_count) if appointments is not None else "—",
                    "Scheduled for today",
                    "▦",
                    "coral",
                ),
                (
                    "Pending requests",
                    _format_count(pending_count) if appointments is not None else "—",
                    "Awaiting staff review",
                    "♧",
                    "purple",
                ),
            ]
            kpi_columns = st.columns(4)
            for column, (label, value, detail, icon, color) in zip(
                kpi_columns, kpi_data
            ):
                with column:
                    with st.container(border=True, key=f"home-kpi-{color}"):
                        icon_column, metric_column = st.columns(
                            [0.35, 1.65], vertical_alignment="top"
                        )
                        with icon_column:
                            st.markdown(
                                f'<div class="home-kpi-icon home-kpi-icon-{color}">'
                                f'{icon}</div>',
                                unsafe_allow_html=True,
                            )
                        with metric_column:
                            st.caption(label)
                            st.markdown(
                                f'<div class="home-kpi-value">{value}</div>',
                                unsafe_allow_html=True,
                            )
                            st.caption(detail)

            left_column, right_column = st.columns([1.55, 1.05])
            with left_column:
                with st.container(border=True, key="home-regional-card"):
                    regional_title, regional_link = st.columns(
                        [1.5, 1], vertical_alignment="center"
                    )
                    with regional_title:
                        st.markdown(
                            '<div class="home-eyebrow">Regional overview</div>',
                            unsafe_allow_html=True,
                        )
                        st.markdown("### Patients across Bicol")
                    with regional_link:
                        if statistics_page is not None:
                            st.page_link(
                                statistics_page,
                                label="View details",
                                icon=":material/arrow_forward:",
                            )

                    chart_data = pd.DataFrame(
                        {
                            "Province": list(BICOL_PROVINCES),
                            "Patients": [
                                int(province_counts[_province_key(province)])
                                for province in BICOL_PROVINCES
                            ],
                        }
                    )
                    overview_tab, map_tab = st.tabs(
                        ["Province breakdown", "Offline map"]
                    )
                    with overview_tab:
                        _render_province_breakdown(
                            chart_data,
                            len(bicol_records),
                            dark_mode=True,
                        )
                    with map_tab:
                        _render_bicol_map(province_counts.to_dict())

            with right_column:
                try:
                    _render_appointments(
                        appointments, today, appointments_page, appointment_error
                    )
                except Exception as error:
                    st.error(f"Unable to display upcoming appointments: {error}")


if __name__ == "__main__":
    show_home_dashboard_page()
