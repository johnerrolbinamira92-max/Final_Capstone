from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

from database import get_local_connection, get_supabase_client
from views.encode import _open_encode_dialog, show_encode_dialog
from views.appointments import (
    CALENDAR_STATUSES,
    _appointment_summary_counts,
    _format_time,
    _load_appointments,
    _load_calendar_appointments,
)
from views.manage import (
    _patient_full_name,
    _render_patient_results_table,
    show_patient_detail_dialog,
)
from views.notifications import (
    _format_requested_date,
    _format_requested_time,
    _mark_notifications_read,
)
from views.privacy import mask_patient_name
from views.map_utils import (
    location_key as _base_location_key,
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
HOME_QUICK_SEARCH_COLUMN_WIDTHS = (112, 135, 54, 36, 72)


def _search_local_patients(query):
    normalized_query = query.strip().casefold()
    if not normalized_query:
        return []

    conn = get_local_connection()
    try:
        records = conn.execute(
            """
            SELECT patient_id, patient_case_number, first_name, middle_name,
                   last_name, extension_name, calculated_age, sex,
                   city_municipality, province, status
            FROM patients
            ORDER BY patient_case_number COLLATE NOCASE, patient_id
            """
        ).fetchall()
    finally:
        conn.close()

    matches = []
    for row in records:
        record = dict(row)
        searchable_values = (
            record.get("patient_case_number"),
            record.get("first_name"),
            record.get("middle_name"),
            record.get("last_name"),
            record.get("extension_name"),
            _patient_full_name(record),
            record.get("city_municipality"),
            record.get("province"),
        )
        if any(
            normalized_query in str(value or "").casefold()
            for value in searchable_values
        ):
            matches.append(record)
    return matches


def _select_home_patient_record(patient_id):
    st.session_state["manage_selected_patient_id"] = patient_id
    for key in (
        "manage_edit_patient_id",
        "manage_delete_patient_id",
        "manage_return_session_patient_id",
        "manage_edit_return_session_id",
        "manage_delete_return_session_id",
        "record_results_table",
        "manage_success_message",
    ):
        st.session_state.pop(key, None)


def _callback_request_seen_at(requests):
    timestamps = []
    for request in requests:
        value = request.get("created_at")
        if not value:
            continue
        try:
            timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            continue
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        timestamps.append(timestamp.astimezone(timezone.utc))
    return max(timestamps, default=datetime.now(timezone.utc)).isoformat()


def _open_callback_request(
    notifications_page,
    notification_id,
    unread_request_ids,
    last_seen_at,
):
    if notifications_page is None:
        return
    seen_ids = {str(request_id) for request_id in unread_request_ids}
    seen_ids.add(str(notification_id))
    _mark_notifications_read(seen_ids)

    profile = st.session_state.get("admin_profile") or {}
    admin_id = str(profile.get("user_id") or "local")
    last_seen_key = f"callback_requests_last_seen_at:{admin_id}"
    try:
        new_last_seen_at = datetime.fromisoformat(
            str(last_seen_at).replace("Z", "+00:00")
        )
    except ValueError:
        new_last_seen_at = datetime.now(timezone.utc)
    if new_last_seen_at.tzinfo is None:
        new_last_seen_at = new_last_seen_at.replace(tzinfo=timezone.utc)
    current_last_seen_at = st.session_state.get(last_seen_key)
    if current_last_seen_at:
        try:
            current_last_seen_at = datetime.fromisoformat(
                str(current_last_seen_at).replace("Z", "+00:00")
            )
        except ValueError:
            current_last_seen_at = None
        if current_last_seen_at is not None:
            if current_last_seen_at.tzinfo is None:
                current_last_seen_at = current_last_seen_at.replace(
                    tzinfo=timezone.utc
                )
            new_last_seen_at = max(
                new_last_seen_at,
                current_last_seen_at.astimezone(timezone.utc),
            )
    st.session_state[last_seen_key] = new_last_seen_at.astimezone(
        timezone.utc
    ).isoformat()

    selected_key = "notification_selected_item:not-responded"
    if st.session_state.get(selected_key) != notification_id:
        st.session_state["callback_action_mode"] = None
    st.session_state[selected_key] = notification_id
    st.session_state["notification_opened_item:not-responded"] = notification_id
    st.switch_page(notifications_page)


def _open_encode_from_home():
    for key in (
        "manage_selected_patient_id",
        "manage_edit_patient_id",
        "manage_delete_patient_id",
        "manage_return_session_patient_id",
        "record_results_table",
    ):
        st.session_state.pop(key, None)
    _open_encode_dialog()


def _render_overview_toolbar(
    notifications_page=None,
    unread_callback_requests=None,
    callback_requests_error=None,
    callback_requests_cached_at=None,
):
    unread_count = len(unread_callback_requests or ())
    notification_help = (
        "Callback requests unavailable"
        if unread_callback_requests is None
        else f"{unread_count} unread callback requests"
    )
    with st.container(key="overview-toolbar"):
        title_column, search_column, notification_column = st.columns(
            [1.35, 0.85, 0.08], vertical_alignment="center"
        )
        with title_column:
            with st.container(key="home-page-intro"):
                st.markdown(
                    """
                    <div class="statistics-eyebrow">Clinic Overview</div>
                    <h1 class="statistics-title">Home</h1>
                    <p class="statistics-description">
                      Regional patient care, organized in one place.
                    </p>
                    """,
                    unsafe_allow_html=True,
                )
        with search_column:
            with st.container(key="home-quick-search"):
                with st.form(key="overview-search-form", border=False):
                    with st.container(
                        horizontal=True,
                        wrap=False,
                        vertical_alignment="center",
                        gap="small",
                    ):
                        st.text_input(
                            "Search patient records",
                            placeholder="Search name, ID, or location...",
                            type="password",
                            icon=":material/search:",
                            label_visibility="collapsed",
                            key="home_search_query",
                            autocomplete="off",
                            width="stretch",
                        )
                        submitted = st.form_submit_button(
                            "Search",
                            key="overview-search-submit",
                            help="Search local patient records",
                            width="content",
                        )
                if submitted:
                    query = st.session_state.get("home_search_query", "").strip()
                    st.session_state["home_quick_search_query"] = query
                    st.session_state["home_quick_search_open"] = bool(query)
                    st.session_state["home_quick_search_error"] = None
                    if query:
                        try:
                            st.session_state["home_quick_search_results"] = (
                                _search_local_patients(query)
                            )
                        except Exception as error:
                            st.session_state["home_quick_search_results"] = []
                            st.session_state["home_quick_search_error"] = str(
                                error
                            )
                    else:
                        st.session_state["home_quick_search_results"] = []

                if st.session_state.get("home_quick_search_open", False):
                    with st.container(key="home-quick-search-results"):
                        with st.container(
                            horizontal=True,
                            vertical_alignment="center",
                            horizontal_alignment="right",
                            key="home-quick-search-close-row",
                        ):
                            if st.button(
                                "✕",
                                key="home-quick-search-close",
                                type="tertiary",
                                width="content",
                                help="Close quick-search results",
                            ):
                                st.session_state[
                                    "home_quick_search_open"
                                ] = False
                                st.rerun()

                        search_error = st.session_state.get(
                            "home_quick_search_error"
                        )
                        search_results = st.session_state.get(
                            "home_quick_search_results", []
                        )
                        if search_error:
                            st.error(
                                "Unable to search local patient records: "
                                f"{search_error}"
                            )
                        elif not search_results:
                            st.caption(
                                "No matching patient records found"
                            )
                        else:
                            selected_patient_id = (
                                _render_patient_results_table(
                                    search_results,
                                    column_widths=HOME_QUICK_SEARCH_COLUMN_WIDTHS,
                                    column_gap="small",
                                )
                            )
                            if selected_patient_id is not None:
                                _select_home_patient_record(
                                    selected_patient_id
                                )
        with notification_column:
            with st.container(key="overview-notification-control"):
                notification_popover = st.popover(
                    " ",
                    icon=":material/notifications:",
                    help=notification_help,
                    type="tertiary",
                    width="content",
                    key="overview-notifications",
                    on_change="rerun",
                )
                with notification_popover:
                    with st.container(
                        key="overview-callback-popover-content",
                        width=320,
                    ):
                        if callback_requests_error:
                            st.error(callback_requests_error)
                        elif unread_callback_requests is None:
                            st.info("Callback requests are unavailable.")
                        elif not unread_callback_requests:
                            st.markdown(
                                '<div class="callback-popover-empty">'
                                "No new notifications</div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            if callback_requests_cached_at:
                                st.caption(
                                    "Showing cached requests, last synced "
                                    f"{callback_requests_cached_at}."
                                )
                            with st.container(
                                key="overview-callback-request-list",
                            ):
                                unread_request_ids = tuple(
                                    str(item["id"])
                                    for item in unread_callback_requests
                                )
                                last_seen_at = _callback_request_seen_at(
                                    unread_callback_requests
                                )
                                for request in unread_callback_requests:
                                    request_id = str(request["id"])
                                    request_key = request_id.replace(":", "-")
                                    title = str(request.get("title") or "Patient")
                                    preferred_schedule = (
                                        "Preferred: "
                                        f"{_format_requested_date(request.get('requested_date'))}"
                                        " · "
                                        f"{_format_requested_time(request.get('requested_time'))}"
                                    )
                                    st.button(
                                        f"**{title}**\n\n{preferred_schedule}",
                                        key=f"overview-callback-request-{request_key}",
                                        type="tertiary",
                                        width="stretch",
                                        disabled=notifications_page is None,
                                        on_click=_open_callback_request,
                                        args=(
                                            notifications_page,
                                            request_id,
                                            unread_request_ids,
                                            last_seen_at,
                                        ),
                                    )
                if unread_count > 0:
                    st.markdown(
                        '<span class="overview-notification-badge" '
                        f'aria-label="{unread_count} unread callback requests">'
                        f"{unread_count}</span>",
                        unsafe_allow_html=True,
                    )


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


def _toggle_upcoming_names_visibility():
    key = "home_upcoming_names_visible"
    st.session_state[key] = not st.session_state[key]


def _render_appointments(appointments, today, appointments_page, error=None):
    names_visible_key = "home_upcoming_names_visible"
    st.session_state.setdefault(names_visible_key, False)
    names_visible = st.session_state[names_visible_key]

    with st.container(border=True, key="home-appointments-card"):
        with st.container(key="home-appointments-header", gap=None):
            st.markdown(
                f'<div class="home-eyebrow">Today · {today.strftime("%B")} {today.day}</div>',
                unsafe_allow_html=True,
            )
            with st.container(
                key="home-appointments-heading-row",
                gap=None,
            ):
                title_column, link_column = st.columns(
                    [1.5, 1],
                    vertical_alignment="center",
                )
                title_column.markdown("### Upcoming Appointments")
                if appointments_page is not None:
                    link_column.page_link(
                        appointments_page,
                        label="Full Calendar",
                        icon=":material/arrow_forward:",
                        width="content",
                    )
            st.button(
                "Hide" if names_visible else "Show",
                key="home-upcoming-names-toggle",
                icon=(
                    ":material/visibility_off:"
                    if names_visible
                    else ":material/visibility:"
                ),
                help=(
                    "Hide patient names"
                    if names_visible
                    else "Reveal patient names"
                ),
                type="tertiary",
                width="content",
                on_click=_toggle_upcoming_names_visibility,
            )

        upcoming = None
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
            active = active[dates.dt.date == today]
            active["_sort_date"] = pd.to_datetime(
                active["requested_date"], errors="coerce"
            )
            upcoming = active.sort_values(
                ["_sort_date", "requested_time_slot"],
                kind="stable",
                na_position="last",
            )

        with st.container(height=240, key="home-upcoming-appointment-rows"):
            if upcoming is None:
                pass
            elif upcoming.empty:
                st.caption("No appointments scheduled for today.")
            else:
                for index, appointment in enumerate(
                    upcoming.to_dict(orient="records")
                ):
                    time_label = _format_time(
                        appointment.get("requested_time_slot")
                    )
                    with st.container(key=f"home-appointment-row-{index}"):
                        detail_column, arrow_column = st.columns(
                            [1, 0.12],
                            vertical_alignment="center",
                        )
                        patient_name = appointment.get("patient_name")
                        display_name = (
                            str(patient_name or "").strip()
                            if names_visible
                            else mask_patient_name(patient_name)
                        )
                        detail_column.markdown(
                            f"**{escape(display_name)}**  \n"
                            f"<span class=\"home-appointment-detail\">"
                            f"{escape(time_label)}</span>",
                            unsafe_allow_html=True,
                        )
                        if appointments_page is not None:
                            arrow_column.page_link(
                                appointments_page,
                                icon=":material/chevron_right:",
                                help="Open appointment schedule",
                            )

        st.space("stretch")
        if appointments_page is not None:
            st.page_link(
                appointments_page,
                label="Add Appointment",
                icon=":material/add:",
                width="stretch",
                query_params={"focus": "schedule"},
            )


def show_home_dashboard_page(
    *,
    statistics_page=None,
    appointments_page=None,
    search_page=None,
    notifications_page=None,
    unread_callback_requests=None,
    callback_requests_error=None,
    callback_requests_cached_at=None,
):
    success_message = st.session_state.pop("manage_success_message", None)
    encode_success_toast = st.session_state.pop("encode_success_toast", None)
    if encode_success_toast:
        st.toast(encode_success_toast)
    if (
        success_message
        and st.session_state.get("home_quick_search_open", False)
    ):
        query = st.session_state.get("home_quick_search_query", "")
        try:
            st.session_state["home_quick_search_results"] = (
                _search_local_patients(query)
            )
            st.session_state["home_quick_search_error"] = None
        except Exception as error:
            st.session_state["home_quick_search_results"] = []
            st.session_state["home_quick_search_error"] = str(error)

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
    if calendar_appointments is not None:
        counts = _appointment_summary_counts(calendar_appointments, today)
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
            notifications_page=notifications_page,
            unread_callback_requests=unread_callback_requests,
            callback_requests_error=callback_requests_error,
            callback_requests_cached_at=callback_requests_cached_at,
        )
        selected_patient_id = st.session_state.get(
            "manage_selected_patient_id"
        )
        if selected_patient_id is not None:
            show_patient_detail_dialog(
                selected_patient_id,
                success_message,
            )
        elif success_message:
            st.success(success_message)
        with st.container(key="home-dashboard-content"):
            intro_column, encode_column = st.columns(
                [3, 1], vertical_alignment="top"
            )
            with intro_column:
                st.markdown(
                    f'<div class="home-eyebrow">{today.strftime("%A, %d %B %Y").upper()}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"## {greeting_period.title()}, Administrator.")
                st.write("Here’s what’s happening at Holy Face Center today.")
            with encode_column:
                if search_page is not None:
                    with st.container(key="home-encode-action"):
                        if st.button(
                            "+ Encode New Record",
                            type="primary",
                            key="home-encode-new-record",
                            width="stretch",
                        ):
                            _open_encode_from_home()

            kpi_data = [
                (
                    "Total Patient Records",
                    _format_count(len(records)),
                    "♙",
                    "teal",
                ),
                (
                    "Alive Patients",
                    _format_count(int((records["status"] == "Alive").sum())),
                    "♡",
                    "blue",
                ),
                (
                    "Deceased Patients",
                    _format_count(
                        int((records["status"] == "Deceased").sum())
                    ),
                    "✚",
                    "slate",
                ),
                (
                    "Pending Requests",
                    _format_count(pending_count) if appointments is not None else "—",
                    "♧",
                    "purple",
                ),
            ]
            with st.container(key="home-kpi-row"):
                kpi_columns = st.columns(4)
                for column, (label, value, icon, color) in zip(
                    kpi_columns, kpi_data
                ):
                    with column:
                        with st.container(
                            border=True,
                            key=f"home-kpi-{color}",
                        ):
                            st.markdown(
                                f'<div class="home-kpi-content">'
                                f'<div class="home-kpi-icon home-kpi-icon-{color}">'
                                f'{icon}</div>'
                                f'<div class="home-kpi-copy">'
                                f'<div class="home-kpi-label">{escape(label)}</div>'
                                f'<div class="home-kpi-value">{escape(value)}</div>'
                                "</div></div>",
                                unsafe_allow_html=True,
                            )

            left_column, right_column = st.columns(
                [1.55, 1.05],
                vertical_alignment="top",
            )
            with left_column:
                with st.container(border=True, key="home-regional-card"):
                    regional_title, regional_link = st.columns(
                        [1.5, 1], vertical_alignment="center"
                    )
                    with regional_title:
                        st.markdown(
                            '<div class="home-eyebrow">Regional Overview</div>',
                            unsafe_allow_html=True,
                        )
                        st.markdown("### Patients Across Bicol")
                    with regional_link:
                        if statistics_page is not None:
                            st.page_link(
                                statistics_page,
                                label="View Details",
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
                    _render_province_breakdown(
                        chart_data,
                        len(bicol_records),
                        dark_mode=True,
                    )

            with right_column:
                try:
                    _render_appointments(
                        calendar_appointments,
                        today,
                        appointments_page,
                        appointment_error,
                    )
                except Exception as error:
                    st.error(f"Unable to display upcoming appointments: {error}")

    if (
        st.session_state.get("manage_selected_patient_id") is None
        and st.session_state.get("show_encode_dialog")
    ):
        show_encode_dialog()


if __name__ == "__main__":
    show_home_dashboard_page()
