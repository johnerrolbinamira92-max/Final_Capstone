import datetime
import json
import math
import re
import sqlite3
from html import escape
from pathlib import Path

import altair as alt
import httpx
import pandas as pd
import streamlit as st
from postgrest.exceptions import APIError as PostgrestAPIError

from database import (
    SUPABASE_KEY,
    SUPABASE_URL,
    get_local_connection,
    get_supabase_client,
    is_supabase_connection_available,
    is_supabase_connection_error,
)
from views.map_utils import location_key as _base_location_key
from views.patient_care_status import (
    CARE_STATUS_ACTIVE,
    CARE_STATUS_COLORS,
    CARE_STATUS_DECEASED,
    CARE_STATUS_LOST_TO_FOLLOW_UP,
    load_patient_care_statuses,
)

BICOL_ADDRESS_FILE = (
    Path(__file__).resolve().parents[1] / "data" / "bicol_address_hierarchy.json"
)
PORTAL_ENGAGEMENT_ACTIONS = {
    "need_help_submitted",
    "no_help_submitted",
}
PORTAL_ENGAGEMENT_TIMEFRAMES = (
    "Daily",
    "Weekly",
    "Monthly",
    "Yearly",
    "All Time",
)
PORTAL_ENGAGEMENT_TIMEZONE = datetime.timezone(datetime.timedelta(hours=8))
PORTAL_ENGAGEMENT_EVENT_TYPES = {
    "need_help": "need_help_submitted",
    "no_help": "no_help_submitted",
}
PORTAL_REQUEST_QUERY_COLUMNS = (
    "approval_status,created_at,requested_date,requested_time_slot"
)
PORTAL_REQUEST_PAGE_SIZE = 1000
PORTAL_REQUEST_OUTCOMES = (
    "Pending / Awaiting",
    "Confirmed / Scheduled",
    "Rescheduled",
    "Done",
    "Cancelled",
    "No-show",
)
AGE_GROUPS = (
    "Under 18",
    "18–24",
    "25–34",
    "35–49",
    "50+",
    "Unspecified",
)
GENDER_GROUPS = ("Male", "Female", "Others")
GENDER_COLORS = ("#14b8a6", "#f97316", "#8b5cf6")
STATISTICS_ANALYTICS_STYLES = """
<style>
.st-key-admin-statistics-page .st-key-statistics-age-summary [data-testid="stMetric"],
.st-key-admin-statistics-page .st-key-statistics-gender-summary [data-testid="stMetric"] {
    border: 1px solid rgba(255, 255, 255, .08) !important;
    border-radius: 16px !important;
    background: #112926 !important;
    box-shadow: 0 8px 20px rgba(0, 0, 0, .12);
}
.st-key-admin-statistics-page .st-key-statistics-age-summary [data-testid="stMetricLabel"],
.st-key-admin-statistics-page .st-key-statistics-age-summary [data-testid="stMetricValue"],
.st-key-admin-statistics-page .st-key-statistics-gender-summary [data-testid="stMetricLabel"],
.st-key-admin-statistics-page .st-key-statistics-gender-summary [data-testid="stMetricValue"] {
    color: #e5efed !important;
}
.st-key-admin-statistics-page .statistics-status-row {
    gap: .45rem;
    margin: .38rem 0;
}
.st-key-admin-statistics-page .st-key-statistics-engagement-kpis [data-testid="stMetric"] {
    border: 1px solid rgba(255, 255, 255, .08) !important;
    border-radius: 16px !important;
    background: #112926 !important;
    box-shadow: 0 8px 20px rgba(0, 0, 0, .12);
}
.st-key-admin-statistics-page .st-key-statistics-engagement-kpis [data-testid="stMetricLabel"],
.st-key-admin-statistics-page .st-key-statistics-engagement-kpis [data-testid="stMetricValue"] {
    color: #e5efed !important;
}
.st-key-admin-statistics-page .st-key-statistics-age-distribution [data-testid="stVerticalBlockBorderWrapper"],
.st-key-admin-statistics-page .st-key-statistics-gender-distribution [data-testid="stVerticalBlockBorderWrapper"],
.st-key-admin-statistics-page .st-key-statistics-engagement-breakdown [data-testid="stVerticalBlockBorderWrapper"],
.st-key-admin-statistics-page .st-key-statistics-engagement-accounts [data-testid="stVerticalBlockBorderWrapper"],
.st-key-admin-statistics-page .st-key-statistics-engagement-outcomes [data-testid="stVerticalBlockBorderWrapper"],
.st-key-admin-statistics-page .st-key-statistics-engagement-peak-times [data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid rgba(255, 255, 255, .08) !important;
    border-radius: 16px !important;
    background: #112926 !important;
    box-shadow: 0 8px 20px rgba(0, 0, 0, .12);
}
.st-key-admin-statistics-page .st-key-statistics-engagement-outcomes,
.st-key-admin-statistics-page .st-key-statistics-engagement-peak-times {
    margin-top: 18px !important;
    margin-bottom: 24px !important;
}
.st-key-admin-statistics-page .st-key-statistics-age-distribution h3,
.st-key-admin-statistics-page .st-key-statistics-gender-distribution h3 {
    color: #f5f1e7;
}
.st-key-admin-statistics-page .statistics-analytics-table {
    width: 100%;
    border-collapse: collapse;
    border-radius: 12px;
    overflow: hidden;
    color: #e5efed;
    background: #0c201d;
    font-size: .9rem;
}
.st-key-admin-statistics-page .statistics-analytics-table th,
.st-key-admin-statistics-page .statistics-analytics-table td {
    padding: .8rem 1rem;
    border-bottom: 1px solid rgba(255, 255, 255, .07);
}
.st-key-admin-statistics-page .statistics-analytics-table th {
    color: #91aba5;
    font-size: .7rem;
    font-weight: 700;
    letter-spacing: .08em;
    text-align: left;
    text-transform: uppercase;
}
.st-key-admin-statistics-page .statistics-analytics-table td:last-child,
.st-key-admin-statistics-page .statistics-analytics-table th:last-child {
    text-align: right;
}
.st-key-admin-statistics-page .statistics-analytics-table td:last-child {
    color: #f5f1e7;
    font-weight: 700;
}
.st-key-admin-statistics-page .statistics-category-label {
    display: inline-flex;
    align-items: center;
    gap: .55rem;
}
.st-key-admin-statistics-page .statistics-analytics-legend-dot {
    width: .55rem;
    height: .55rem;
    flex: 0 0 .55rem;
    border-radius: 50%;
}
.st-key-admin-statistics-page .statistics-analytics-table tr:last-child td {
    border-bottom: 0;
}
</style>
"""


@st.cache_data
def _load_bicol_address_hierarchy():
    with BICOL_ADDRESS_FILE.open(encoding="utf-8") as address_file:
        provinces = json.load(address_file)["provinces"]
    return {province["name"]: province for province in provinces}


def _normalize_location(value):
    if pd.isna(value) or not str(value).strip():
        return "Not Specified"
    return str(value).strip().title()


def _location_key(value):
    key = _base_location_key(value)
    if key.startswith("city of "):
        key = key[len("city of ") :]
    if key.endswith(" city"):
        key = key[: -len(" city")]
    if key.endswith(" province"):
        key = key[: -len(" province")]
    return key


def _reset_barangay_selection():
    st.session_state["geo_barangay"] = None


def _reset_city_selection():
    st.session_state["geo_city"] = None
    st.session_state["geo_barangay"] = None


def _location_counts(data, group_column, label, options=None):
    values = data[group_column].map(_normalize_location)
    if options is None:
        counts = values.value_counts()
        return (
            counts.rename_axis(label)
            .reset_index(name="Patient Count")
            .sort_values("Patient Count", ascending=False, kind="stable")
        )

    option_by_key = {_location_key(option): option for option in options}
    canonical_values = values.map(
        lambda value: option_by_key.get(_location_key(value), value)
    )
    counts = canonical_values.value_counts()
    ordered_options = list(options)
    option_keys = {_location_key(option) for option in ordered_options}
    ordered_options.extend(
        value
        for value in counts.index
        if _location_key(value) not in option_keys
    )
    return (
        counts.reindex(ordered_options, fill_value=0)
        .rename_axis(label)
        .reset_index(name="Patient Count")
        .sort_values("Patient Count", ascending=False, kind="stable")
    )


def _age_group_counts(data):
    ages = pd.to_numeric(data["calculated_age"], errors="coerce").reset_index(
        drop=True
    )
    groups = pd.Series("Unspecified", index=ages.index, dtype="object")
    valid_age = ages.ge(0)
    groups.loc[valid_age & ages.lt(18)] = AGE_GROUPS[0]
    groups.loc[valid_age & ages.ge(18) & ages.lt(25)] = AGE_GROUPS[1]
    groups.loc[valid_age & ages.ge(25) & ages.lt(35)] = AGE_GROUPS[2]
    groups.loc[valid_age & ages.ge(35) & ages.lt(50)] = AGE_GROUPS[3]
    groups.loc[valid_age & ages.ge(50)] = AGE_GROUPS[4]
    return groups.value_counts().reindex(AGE_GROUPS, fill_value=0)


def _top_age_group_summary(data):
    known_age_counts = _age_group_counts(data).drop("Unspecified")
    known_age_total = int(known_age_counts.sum())
    if data.empty:
        return "No records yet", known_age_total
    if known_age_total == 0:
        return "No age data", known_age_total

    top_group = str(known_age_counts.idxmax())
    share = known_age_counts[top_group] / len(data) * 100
    return f"{top_group} yrs · {share:.0f}%", known_age_total


def _gender_counts(data):
    values = data["sex"].fillna("").astype(str).str.strip().str.casefold()
    groups = values.map({"male": "Male", "female": "Female"}).fillna(
        "Others"
    )
    return groups.value_counts().reindex(GENDER_GROUPS, fill_value=0)


def _render_analytics_table(
    data,
    category_label,
    count_column="Patient Count",
    count_label="Patient Count",
    table_label=None,
    category_colors=None,
):
    table_label = table_label or f"{category_label} patient counts"
    rows = []
    for category, count in zip(data[category_label], data[count_column]):
        category_text = escape(str(category))
        category_color = (
            category_colors.get(category) if category_colors else None
        )
        if category_color:
            category_text = (
                '<span class="statistics-category-label">'
                '<span class="statistics-analytics-legend-dot" '
                f'style="background:{escape(category_color)}" '
                'aria-hidden="true"></span>'
                f"{category_text}</span>"
            )
        rows.append(
            "<tr>"
            f"<td>{category_text}</td>"
            f"<td>{int(count):,}</td>"
            "</tr>"
        )
    st.html(
        f'<table class="statistics-analytics-table" '
        f'aria-label="{escape(table_label)}">'
        "<thead><tr>"
        f"<th>{escape(category_label)}</th>"
        f"<th>{escape(count_label)}</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>",
        width="stretch",
    )


def _render_age_group_chart(age_counts):
    chart_data = pd.DataFrame(
        {
            "Age Group": list(AGE_GROUPS),
            "Patient Count": [int(age_counts[group]) for group in AGE_GROUPS],
        }
    )
    chart = (
        alt.Chart(chart_data)
        .mark_bar(
            color="#2dd4bf",
            cornerRadiusTopLeft=6,
            cornerRadiusTopRight=6,
            size=28,
        )
        .encode(
            x=alt.X(
                "Age Group:N",
                title=None,
                sort=list(AGE_GROUPS),
                axis=alt.Axis(
                    labelAngle=-30,
                    labelColor="#e5efed",
                    labelLimit=100,
                    ticks=False,
                    domainColor="#344945",
                ),
            ),
            y=alt.Y(
                "Patient Count:Q",
                title="Patient Count",
                scale=alt.Scale(domainMin=0, nice=True),
                axis=alt.Axis(
                    format="d",
                    tickMinStep=1,
                    labelColor="#a7bbb7",
                    titleColor="#a7bbb7",
                    gridColor="#344945",
                    tickColor="#344945",
                    domainColor="#344945",
                ),
            ),
            tooltip=[
                alt.Tooltip("Age Group:N", title="Age group"),
                alt.Tooltip("Patient Count:Q", title="Patients", format=","),
            ],
        )
        .properties(height=280, background="#112926")
    )
    st.altair_chart(
        chart,
        width="stretch",
        theme=None,
        alt="Patient counts by age group",
    )


def _render_gender_chart(gender_counts):
    chart_data = pd.DataFrame(
        [
            {"Gender": label, "Patient Count": int(gender_counts[label])}
            for label in GENDER_GROUPS
            if gender_counts[label] > 0
        ]
    )
    if chart_data.empty:
        st.info("There are no patient records for this gender distribution.")
        return

    donut = (
        alt.Chart(chart_data)
        .mark_arc(innerRadius=74, outerRadius=118)
        .encode(
            theta=alt.Theta("Patient Count:Q", stack=True),
            color=alt.Color(
                "Gender:N",
                scale=alt.Scale(
                    domain=list(GENDER_GROUPS),
                    range=list(GENDER_COLORS),
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("Gender:N", title="Gender"),
                alt.Tooltip("Patient Count:Q", title="Patients", format=","),
            ],
        )
        .properties(height=280)
    )
    center_total = (
        alt.Chart(pd.DataFrame({"value": [int(gender_counts.sum())]}))
        .mark_text(
            font="DM Sans",
            fontSize=22,
            fontWeight="bold",
            color="#e5efed",
        )
        .encode(text=alt.Text("value:Q", format=","))
    )
    center_label = (
        alt.Chart(pd.DataFrame({"label": ["Patients"]}))
        .mark_text(dy=22, font="DM Sans", fontSize=11, color="#a7bbb7")
        .encode(text="label:N")
    )
    st.altair_chart(
        (donut + center_total + center_label).properties(background="#112926"),
        width="stretch",
        theme=None,
        alt="Patient counts by gender",
    )


def _render_distribution_chart(chart_data, category_label, total_patients):
    chart_values = chart_data[chart_data["Patient Count"] > 0]
    if chart_values.empty:
        st.info("There are no patient records for this geographic breakdown yet.")
        return

    donut = (
        alt.Chart(chart_values)
        .mark_arc(innerRadius=74, outerRadius=118)
        .encode(
            theta=alt.Theta("Patient Count:Q", stack=True),
            color=alt.Color(
                f"{category_label}:N",
                scale=alt.Scale(scheme="tableau20"),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip(f"{category_label}:N", title=category_label),
                alt.Tooltip("Patient Count:Q", title="Patients", format=","),
            ],
        )
        .properties(height=280)
    )
    center_total = (
        alt.Chart(pd.DataFrame({"value": [total_patients]}))
        .mark_text(
            font="DM Sans",
            fontSize=22,
            fontWeight="bold",
            color="#e5efed",
        )
        .encode(text=alt.Text("value:Q", format=","))
    )
    center_label = (
        alt.Chart(pd.DataFrame({"label": ["Patients"]}))
        .mark_text(
            dy=22,
            font="DM Sans",
            fontSize=11,
            color="#a7bbb7",
        )
        .encode(text="label:N")
    )
    chart = (donut + center_total + center_label).properties(
        background="#182523"
    )
    st.altair_chart(
        chart,
        width="stretch",
        theme=None,
        alt=f"Patient record distribution by {category_label.lower()}",
    )


def _render_registration_chart(data):
    registration_dates = pd.to_datetime(
        data["date_registered"], errors="coerce"
    )
    if not registration_dates.notna().any():
        st.info("Registration dates are not available in these archived records.")
        return

    current_month = pd.Timestamp.now().to_period("M").to_timestamp()
    months = pd.date_range(end=current_month, periods=6, freq="MS")
    monthly_counts = (
        registration_dates.dropna()
        .dt.to_period("M")
        .value_counts()
    )
    trend = pd.DataFrame(
        {
            "Month": months,
            "Registrations": [
                int(monthly_counts.get(month.to_period("M"), 0))
                for month in months
            ],
        }
    )

    base = alt.Chart(trend).encode(
        x=alt.X(
            "Month:T",
            title=None,
            axis=alt.Axis(format="%b", labelColor="#a7bbb7", tickColor="#344945"),
        ),
        y=alt.Y(
            "Registrations:Q",
            title=None,
            scale=alt.Scale(domainMin=0),
            axis=alt.Axis(labelColor="#a7bbb7", gridColor="#344945"),
        ),
        tooltip=[
            alt.Tooltip("Month:T", title="Month", format="%B %Y"),
            alt.Tooltip("Registrations:Q", title="New patient records", format=","),
        ],
    )
    chart = (
        base.mark_area(
            color="#43c4b5",
            opacity=0.2,
            interpolate="monotone",
        )
        + base.mark_line(
            color="#00a394",
            strokeWidth=3,
            interpolate="monotone",
        )
    ).properties(background="#182523", height=280)
    st.altair_chart(
        chart,
        width="stretch",
        theme=None,
        alt="Monthly patient registrations over the last six months",
    )


def _render_status_distribution(data):
    status_counts = data["status"].value_counts()
    status_rows = [
        (
            CARE_STATUS_ACTIVE,
            int(status_counts.get(CARE_STATUS_ACTIVE, 0)),
            CARE_STATUS_COLORS[CARE_STATUS_ACTIVE],
        ),
        (
            CARE_STATUS_LOST_TO_FOLLOW_UP,
            int(status_counts.get(CARE_STATUS_LOST_TO_FOLLOW_UP, 0)),
            CARE_STATUS_COLORS[CARE_STATUS_LOST_TO_FOLLOW_UP],
        ),
        (
            CARE_STATUS_DECEASED,
            int(status_counts.get(CARE_STATUS_DECEASED, 0)),
            CARE_STATUS_COLORS[CARE_STATUS_DECEASED],
        ),
    ]

    chart_data = pd.DataFrame(
        [
            {"Status": label, "Patients": count}
            for label, count, _ in status_rows
            if count > 0
        ]
    )
    chart_column, legend_column = st.columns([1.25, 1], gap="small")
    with chart_column:
        if chart_data.empty:
            st.info("There are no patient records for this status distribution.")
        else:
            donut = (
                alt.Chart(chart_data)
                .mark_arc(innerRadius=52, outerRadius=78)
                .encode(
                    theta=alt.Theta("Patients:Q", stack=True),
                    color=alt.Color(
                        "Status:N",
                        scale=alt.Scale(
                            domain=[label for label, _, _ in status_rows],
                            range=[color for _, _, color in status_rows],
                        ),
                        legend=None,
                    ),
                    tooltip=[
                        alt.Tooltip("Status:N", title="Patient status"),
                        alt.Tooltip("Patients:Q", title="Patients", format=","),
                    ],
                )
            )
            total = (
                alt.Chart(pd.DataFrame({"value": [len(data)]}))
                .mark_text(
                    font="DM Sans",
                    fontSize=20,
                    fontWeight="bold",
                    color="#e5efed",
                )
                .encode(text=alt.Text("value:Q", format=","))
            )
            label = (
                alt.Chart(pd.DataFrame({"label": ["Patients"]}))
                .mark_text(
                    dy=21,
                    font="DM Sans",
                    fontSize=10,
                    color="#a7bbb7",
                )
                .encode(text="label:N")
            )
            status_chart = (donut + total + label).properties(
                width=170,
                height=170,
                padding={"left": 8, "right": 8, "top": 8, "bottom": 8},
                background="#182523",
            )
            st.altair_chart(
                status_chart,
                width="stretch",
                theme=None,
                alt="Patient status distribution",
            )

    with legend_column:
        for label, count, color in status_rows:
            st.markdown(
                f"""
                <div class="statistics-status-row">
                  <span class="statistics-status-dot" style="background:{color}"></span>
                  <span>{escape(label)}</span>
                  <strong>{count:,}</strong>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _load_patient_locations():
    conn = get_local_connection()
    try:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(patients)").fetchall()
        }
        registered_date = (
            "date_registered"
            if "date_registered" in columns
            else "NULL AS date_registered"
        )
        calculated_age = (
            "calculated_age"
            if "calculated_age" in columns
            else "NULL AS calculated_age"
        )
        sex = "sex" if "sex" in columns else "NULL AS sex"
        records = pd.read_sql_query(
            f"""
            SELECT patient_id, {registered_date}, {calculated_age}, {sex},
                   province, city_municipality, barangay, purok, status
            FROM patients
            """,
            conn,
        )
        care_statuses = load_patient_care_statuses(conn)
        records["status"] = records["patient_id"].map(care_statuses)
        return records
    finally:
        conn.close()


def _normalize_portal_engagement_snapshot(snapshot):
    counts = {}
    for action_type in PORTAL_ENGAGEMENT_ACTIONS:
        value = snapshot["counts"][action_type]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Invalid portal engagement count for {action_type}.")
        counts[action_type] = value

    journal_accounts = []
    for row in snapshot["journal_accounts"]:
        code_name = row["code_name"]
        saved_entries = row["saved_entries"]
        if (
            not isinstance(code_name, str)
            or not re.fullmatch(r"User #\d{2,}", code_name)
            or isinstance(saved_entries, bool)
            or not isinstance(saved_entries, int)
            or saved_entries <= 0
        ):
            raise ValueError("Invalid anonymized journal statistics.")
        journal_accounts.append(
            {"code_name": code_name, "saved_entries": saved_entries}
        )

    refreshed_at = snapshot["refreshed_at"]
    if not isinstance(refreshed_at, str) or not refreshed_at:
        raise ValueError("Portal engagement snapshot has no refresh timestamp.")

    return {
        "counts": counts,
        "journal_accounts": journal_accounts,
        "refreshed_at": refreshed_at,
    }


def _ensure_portal_engagement_cache(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS portal_engagement_cache (
            snapshot_id INTEGER PRIMARY KEY CHECK (snapshot_id = 1),
            need_help_submitted INTEGER NOT NULL CHECK (need_help_submitted >= 0),
            no_help_submitted INTEGER NOT NULL CHECK (no_help_submitted >= 0),
            journal_accounts_json TEXT NOT NULL,
            refreshed_at TEXT NOT NULL
        )
        """
    )


def _read_portal_engagement_cache():
    conn = get_local_connection()
    try:
        _ensure_portal_engagement_cache(conn)
        conn.commit()
        row = conn.execute(
            """
            SELECT need_help_submitted, no_help_submitted,
                   journal_accounts_json, refreshed_at
            FROM portal_engagement_cache
            WHERE snapshot_id = 1
            """
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    return _normalize_portal_engagement_snapshot(
        {
            "counts": {
                "need_help_submitted": row["need_help_submitted"],
                "no_help_submitted": row["no_help_submitted"],
            },
            "journal_accounts": json.loads(row["journal_accounts_json"]),
            "refreshed_at": row["refreshed_at"],
        }
    )


def _save_portal_engagement_cache(snapshot):
    conn = get_local_connection()
    try:
        _ensure_portal_engagement_cache(conn)
        conn.execute(
            """
            INSERT INTO portal_engagement_cache (
                snapshot_id, need_help_submitted, no_help_submitted,
                journal_accounts_json, refreshed_at
            )
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(snapshot_id) DO UPDATE SET
                need_help_submitted = excluded.need_help_submitted,
                no_help_submitted = excluded.no_help_submitted,
                journal_accounts_json = excluded.journal_accounts_json,
                refreshed_at = excluded.refreshed_at
            """,
            (
                snapshot["counts"]["need_help_submitted"],
                snapshot["counts"]["no_help_submitted"],
                json.dumps(snapshot["journal_accounts"]),
                snapshot["refreshed_at"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _fetch_portal_engagement_snapshot(client):
    count_response = (
        client.table("portal_engagement_counts")
        .select("id,need_help_submitted,no_help_submitted")
        .eq("id", 1)
        .limit(1)
        .execute()
    )
    count_rows = count_response.data or []
    if len(count_rows) != 1:
        raise ValueError("Supabase returned no portal engagement counter row.")

    count_row = count_rows[0]
    counter_id = count_row["id"]
    if isinstance(counter_id, bool) or counter_id != 1:
        raise ValueError("Supabase returned an invalid portal engagement row.")

    counts = {}
    for action_type in PORTAL_ENGAGEMENT_ACTIONS:
        submission_count = count_row[action_type]
        if (
            isinstance(submission_count, bool)
            or not isinstance(submission_count, int)
            or submission_count < 0
        ):
            raise ValueError(
                f"Supabase returned an invalid count for {action_type}."
            )
        counts[action_type] = submission_count

    journal_response = client.rpc("get_anonymized_journal_stats").execute()
    snapshot = {
        "counts": counts,
        "journal_accounts": [
            {
                "code_name": row["code_name"],
                "saved_entries": row["saved_entries"],
            }
            for row in journal_response.data or []
        ],
        "refreshed_at": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds"),
    }
    return _normalize_portal_engagement_snapshot(snapshot)


def _load_portal_engagement_snapshot():
    try:
        cached_snapshot = _read_portal_engagement_cache()
    except (
        sqlite3.Error,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        return None, "error", f"Could not read the local engagement snapshot: {error}"

    if not SUPABASE_URL or not SUPABASE_KEY or not is_supabase_connection_available():
        return cached_snapshot, "cached" if cached_snapshot else "unavailable", None

    client = get_supabase_client()
    if client is None:
        return cached_snapshot, "cached" if cached_snapshot else "unavailable", None

    try:
        snapshot = _fetch_portal_engagement_snapshot(client)
    except (httpx.RequestError, PostgrestAPIError) as error:
        if is_supabase_connection_error(error):
            is_supabase_connection_available.clear()
            return cached_snapshot, "cached" if cached_snapshot else "unavailable", None
        return None, "error", f"Could not load portal engagement metrics: {error}"
    except (KeyError, TypeError, ValueError) as error:
        return None, "error", f"Could not load portal engagement metrics: {error}"

    try:
        _save_portal_engagement_cache(snapshot)
    except sqlite3.Error as error:
        return (
            snapshot,
            "online_uncached",
            f"Live metrics loaded, but the offline snapshot could not be saved: {error}",
        )
    return snapshot, "online", None


def _portal_engagement_time_window(timeframe, now=None):
    if timeframe not in PORTAL_ENGAGEMENT_TIMEFRAMES:
        raise ValueError(f"Unknown portal engagement timeframe: {timeframe}")

    end = now or datetime.datetime.now(PORTAL_ENGAGEMENT_TIMEZONE)
    if end.tzinfo is None:
        end = end.replace(tzinfo=PORTAL_ENGAGEMENT_TIMEZONE)
    else:
        end = end.astimezone(PORTAL_ENGAGEMENT_TIMEZONE)

    if timeframe == "All Time":
        start = None
    elif timeframe == "Daily":
        start = end.replace(hour=0, minute=0, second=0, microsecond=0)
    elif timeframe == "Weekly":
        start = end - datetime.timedelta(days=7)
    elif timeframe == "Monthly":
        start = end - datetime.timedelta(days=30)
    else:
        start = end - datetime.timedelta(days=365)

    utc = datetime.timezone.utc
    return (
        start.astimezone(utc) if start is not None else None,
        end.astimezone(utc),
    )


def _fetch_portal_engagement_event_counts(client, timeframe, now=None):
    start, end = _portal_engagement_time_window(timeframe, now)
    counts = {action_type: 0 for action_type in PORTAL_ENGAGEMENT_ACTIONS}
    for event_type, action_type in PORTAL_ENGAGEMENT_EVENT_TYPES.items():
        query = (
            client.table("portal_engagement_events")
            .select("choice_type", count="exact", head=True)
            .eq("choice_type", event_type)
            .lte("created_at", end.isoformat())
        )
        if start is not None:
            query = query.gte("created_at", start.isoformat())
        response = query.execute()
        count = response.count
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(
                f"Supabase returned an invalid portal engagement event "
                f"count for {event_type}."
            )
        counts[action_type] = count
    return counts


def _load_portal_engagement_event_counts(timeframe):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None, "Supabase is not configured for timestamped engagement events."
    if not is_supabase_connection_available():
        return None, "Supabase is unavailable for timestamped engagement events."

    client = get_supabase_client()
    if client is None:
        return None, "Supabase is unavailable for timestamped engagement events."

    try:
        return _fetch_portal_engagement_event_counts(client, timeframe), None
    except (httpx.RequestError, PostgrestAPIError) as error:
        if is_supabase_connection_error(error):
            is_supabase_connection_available.clear()
            return None, "Supabase is unavailable for timestamped engagement events."
        if getattr(error, "code", None) in {"42P01", "PGRST204", "PGRST205"}:
            return (
                None,
                "Timestamped engagement events are not installed yet. "
                "Run portal_engagement.sql in Supabase.",
            )
        return None, f"Could not load timestamped engagement events: {error}"
    except (KeyError, TypeError, ValueError) as error:
        return None, f"Could not load timestamped engagement events: {error}"


def _fetch_portal_request_rows(client, timeframe, now=None):
    start, end = _portal_engagement_time_window(timeframe, now)
    rows = []
    for table_name in ("patient_help_requests", "appointments"):
        offset = 0
        while True:
            query = (
                client.table(table_name)
                .select(PORTAL_REQUEST_QUERY_COLUMNS)
                .lte("created_at", end.isoformat())
            )
            if start is not None:
                query = query.gte("created_at", start.isoformat())
            response = query.range(
                offset,
                offset + PORTAL_REQUEST_PAGE_SIZE - 1,
            ).execute()
            page = response.data or []
            rows.extend(page)
            if len(page) < PORTAL_REQUEST_PAGE_SIZE:
                break
            offset += PORTAL_REQUEST_PAGE_SIZE
    return rows


def _parse_portal_request_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _parse_portal_request_time(value):
    if isinstance(value, datetime.datetime):
        return value.time().replace(tzinfo=None)
    if isinstance(value, datetime.time):
        return value.replace(tzinfo=None)
    if not isinstance(value, str):
        return None

    time_value = value.strip()
    try:
        return datetime.time.fromisoformat(time_value)
    except ValueError:
        for time_format in ("%I:%M %p", "%I:%M%p", "%I:%M:%S %p"):
            try:
                return datetime.datetime.strptime(
                    time_value.upper(),
                    time_format,
                ).time()
            except ValueError:
                continue
    return None


def _summarize_portal_request_rows(rows):
    outcome_counts = {outcome: 0 for outcome in PORTAL_REQUEST_OUTCOMES}
    slot_counts = {}
    weekday_counts = {}

    for row in rows:
        status = str(row.get("approval_status") or "Pending").strip().casefold()
        if status in {"pending", "awaiting"}:
            outcome = "Pending / Awaiting"
        elif status in {"confirmed", "scheduled"}:
            outcome = "Confirmed / Scheduled"
        elif status == "rescheduled":
            outcome = "Rescheduled"
        elif status in {"done", "completed"}:
            outcome = "Done"
        elif status in {"cancelled", "canceled", "declined"}:
            outcome = "Cancelled"
        elif status in {"no-show", "no show", "noshow"}:
            outcome = "No-show"
        else:
            continue
        outcome_counts[outcome] += 1

        request_time = _parse_portal_request_time(
            row.get("requested_time_slot")
        )
        if request_time is not None:
            slot_label = request_time.strftime("%I:%M %p").lstrip("0")
            slot_counts[slot_label] = slot_counts.get(slot_label, 0) + 1

        request_date = _parse_portal_request_date(row.get("requested_date"))
        if request_date is not None:
            weekday = request_date.strftime("%A")
            weekday_counts[weekday] = weekday_counts.get(weekday, 0) + 1

    peak_slots = sorted(
        slot_counts.items(),
        key=lambda item: (-item[1], _parse_portal_request_time(item[0])),
    )
    busiest_day = None
    if weekday_counts:
        busiest_day = sorted(
            weekday_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[0]
    return {
        "outcomes": outcome_counts,
        "peak_slots": peak_slots[:5],
        "busiest_day": busiest_day,
    }


def _load_portal_request_analytics(timeframe):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None, "Supabase is not configured for request analytics."
    if not is_supabase_connection_available():
        return None, "Supabase is unavailable for request analytics."

    client = get_supabase_client()
    if client is None:
        return None, "Supabase is unavailable for request analytics."

    try:
        rows = _fetch_portal_request_rows(client, timeframe)
        return _summarize_portal_request_rows(rows), None
    except (httpx.RequestError, PostgrestAPIError) as error:
        if is_supabase_connection_error(error):
            is_supabase_connection_available.clear()
            return None, "Supabase is unavailable for request analytics."
        return None, f"Could not load request analytics: {error}"
    except (KeyError, TypeError, ValueError) as error:
        return None, f"Could not load request analytics: {error}"


def _render_portal_engagement(snapshot):
    timeframe = st.segmented_control(
        "Timeframe",
        PORTAL_ENGAGEMENT_TIMEFRAMES,
        default="All Time",
        label_visibility="collapsed",
        key="portal_engagement_timeframe",
        wrap=False,
    )

    event_error = None
    if timeframe == "All Time" and snapshot:
        counts = snapshot["counts"]
    else:
        counts, event_error = _load_portal_engagement_event_counts(timeframe)
    request_analytics, request_error = _load_portal_request_analytics(timeframe)

    journal_accounts = snapshot["journal_accounts"] if snapshot else None
    if counts is not None and timeframe != "All Time" and not any(counts.values()):
        st.caption("No timestamped choices have been recorded for this period.")
    if event_error:
        st.warning(event_error)

    with st.container(horizontal=True, key="statistics-engagement-kpis"):
        st.metric(
            "I Need Help",
            (
                f'{counts["need_help_submitted"]:,}'
                if counts is not None
                else "—"
            ),
            border=True,
        )
        st.metric(
            "I Don't Need Help",
            (
                f'{counts["no_help_submitted"]:,}'
                if counts is not None
                else "—"
            ),
            border=True,
        )
        st.metric(
            "Signed-In Journal Accounts (All Time)",
            f"{len(journal_accounts):,}" if journal_accounts is not None else "—",
            border=True,
        )
    st.caption("Choice counts include both guest and signed-in portal users.")

    comparison_chart = None
    if counts is not None:
        comparison_data = pd.DataFrame(
            [
                {
                    "Submission Type": "I Need Help",
                    "Choice Count": counts["need_help_submitted"],
                },
                {
                    "Submission Type": "I Don't Need Help",
                    "Choice Count": counts["no_help_submitted"],
                },
            ]
        )
        comparison_max = int(comparison_data["Choice Count"].max())
        comparison_axis_max = 10 * max(1, math.ceil(comparison_max / 10))
        comparison_chart = (
            alt.Chart(comparison_data)
            .mark_bar(size=34, cornerRadiusEnd=6)
            .encode(
                x=alt.X(
                    "Choice Count:Q",
                    axis=alt.Axis(
                        format="d",
                        values=list(range(0, comparison_axis_max + 1, 10)),
                        gridColor="#2b403c",
                        labelColor="#a7bbb7",
                        title=None,
                    ),
                    scale=alt.Scale(
                        domain=[0, comparison_axis_max],
                        nice=False,
                    ),
                ),
                y=alt.Y(
                    "Submission Type:N",
                    sort=["I Need Help", "I Don't Need Help"],
                    axis=alt.Axis(
                        domain=False,
                        labelColor="#e5efed",
                        ticks=False,
                        title=None,
                    ),
                ),
                color=alt.Color(
                    "Submission Type:N",
                    scale=alt.Scale(
                        domain=["I Need Help", "I Don't Need Help"],
                        range=["#2dd4bf", "#43c4b5"],
                    ),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("Submission Type:N"),
                    alt.Tooltip("Choice Count:Q", format=","),
                ],
            )
            .properties(height=220, background="#112926")
        )

    chart_column, accounts_column = st.columns([1, 1.15])
    with chart_column:
        with st.container(
            height=330,
            border=True,
            key="statistics-engagement-breakdown",
        ):
            st.markdown(
                '<div class="statistics-card-eyebrow">'
                f"Public choices · {escape(timeframe)}"
                "</div>",
                unsafe_allow_html=True,
            )
            st.markdown("### I Need Help vs. I Don't Need Help")
            if comparison_chart is not None:
                st.altair_chart(
                    comparison_chart,
                    width="stretch",
                    theme=None,
                    alt=(
                        "I Need Help and I Don't Need Help choices for "
                        f"{timeframe}"
                    ),
                )
            else:
                st.info("Choice counts are unavailable for this timeframe.")
    with accounts_column:
        with st.container(
            height=330,
            border=True,
            key="statistics-engagement-accounts",
        ):
            st.markdown(
                '<div class="statistics-card-eyebrow">Anonymized Accounts</div>',
                unsafe_allow_html=True,
            )
            st.markdown("### Signed-In Journal Accounts")
            if journal_accounts:
                _render_analytics_table(
                    pd.DataFrame(
                        [
                            {
                                "Code Name": row["code_name"],
                                "Saved Entries": row["saved_entries"],
                            }
                            for row in journal_accounts
                        ]
                    ),
                    "Code Name",
                    count_column="Saved Entries",
                    count_label="Saved Entries",
                    table_label="Anonymized signed-in journal account counts",
                )
            elif journal_accounts is not None:
                st.info("No signed-in journal entries have been saved yet.")
            else:
                st.info("Signed-in journal account data is unavailable.")
            st.caption(
                "RA 10173 privacy note: signed-in accounts are shown only as "
                "sequential code names and saved-entry counts. Guest submissions "
                "are included only in the aggregate totals above; guest identities "
                "and entries are not listed."
            )

    outcomes_column, peak_times_column = st.columns(2)
    with outcomes_column:
        with st.container(
            height=390,
            border=True,
            key="statistics-engagement-outcomes",
        ):
            st.markdown(
                '<div class="statistics-card-eyebrow">Request activity · '
                f"{escape(timeframe)}</div>",
                unsafe_allow_html=True,
            )
            st.markdown("### Request Outcome Breakdown")
            if request_error:
                st.warning(request_error)
            elif request_analytics is not None:
                outcomes = pd.DataFrame(
                    [
                        {"Outcome": outcome, "Requests": count}
                        for outcome, count in request_analytics["outcomes"].items()
                    ]
                )
                max_outcome_count = max(
                    1,
                    int(outcomes["Requests"].max()),
                )
                outcome_tick_step = max(
                    1,
                    math.ceil(max_outcome_count / 5),
                )
                outcome_chart = (
                    alt.Chart(outcomes)
                    .mark_bar(size=22, cornerRadiusEnd=5, color="#2dd4bf")
                    .encode(
                        x=alt.X(
                            "Requests:Q",
                            axis=alt.Axis(
                                format="d",
                                values=list(
                                    range(
                                        0,
                                        max_outcome_count + 1,
                                        outcome_tick_step,
                                    )
                                ),
                                gridColor="#2b403c",
                                labelColor="#a7bbb7",
                                title=None,
                            ),
                            scale=alt.Scale(
                                domain=[0, max_outcome_count],
                                nice=False,
                            ),
                        ),
                        y=alt.Y(
                            "Outcome:N",
                            sort=list(PORTAL_REQUEST_OUTCOMES),
                            axis=alt.Axis(
                                domain=False,
                                labelColor="#e5efed",
                                ticks=False,
                                title=None,
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip("Outcome:N"),
                            alt.Tooltip("Requests:Q", format="d"),
                        ],
                    )
                    .properties(height=230, background="#112926")
                )
                st.altair_chart(
                    outcome_chart,
                    width="stretch",
                    theme=None,
                    alt=f"Callback request outcomes for {timeframe}",
                )
                if not any(request_analytics["outcomes"].values()):
                    st.caption("No callback requests or appointments in this period.")

    with peak_times_column:
        with st.container(
            height=390,
            border=True,
            key="statistics-engagement-peak-times",
        ):
            st.markdown(
                '<div class="statistics-card-eyebrow">Requested schedules · '
                f"{escape(timeframe)}</div>",
                unsafe_allow_html=True,
            )
            st.markdown("### Peak Request Time Slots")
            if request_error:
                st.warning(request_error)
            elif request_analytics is not None:
                busiest_day = request_analytics["busiest_day"]
                if request_analytics["peak_slots"]:
                    peak_slots = pd.DataFrame(
                        [
                            {"Time Slot": slot, "Requests": count}
                            for slot, count in request_analytics["peak_slots"]
                        ]
                    )
                    peak_max = max(1, int(peak_slots["Requests"].max()))
                    peak_tick_step = max(1, math.ceil(peak_max / 5))
                    peak_chart = (
                        alt.Chart(peak_slots)
                        .mark_bar(size=22, cornerRadiusEnd=5, color="#43c4b5")
                        .encode(
                            x=alt.X(
                                "Requests:Q",
                                axis=alt.Axis(
                                    format="d",
                                    values=list(
                                        range(
                                            0,
                                            peak_max + 1,
                                            peak_tick_step,
                                        )
                                    ),
                                    gridColor="#2b403c",
                                    labelColor="#a7bbb7",
                                    title=None,
                                ),
                                scale=alt.Scale(
                                    domain=[0, peak_max],
                                    nice=False,
                                ),
                            ),
                            y=alt.Y(
                                "Time Slot:N",
                                sort="-x",
                                axis=alt.Axis(
                                    domain=False,
                                    labelColor="#e5efed",
                                    ticks=False,
                                    title=None,
                                ),
                            ),
                            tooltip=[
                                alt.Tooltip("Time Slot:N"),
                                alt.Tooltip("Requests:Q", format="d"),
                            ],
                        )
                        .properties(height=230, background="#112926")
                    )
                    st.altair_chart(
                        peak_chart,
                        width="stretch",
                        theme=None,
                        alt=f"Most requested callback times for {timeframe}",
                    )
                else:
                    st.info("No requested time slots in this period.")

                if busiest_day:
                    st.caption(
                        f"Busiest day: {busiest_day[0]} · "
                        f"{busiest_day[1]:,} requests"
                    )
                else:
                    st.caption("Busiest day: No requested dates in this period.")


def show_dashboard_page():
    try:
        df = _load_patient_locations()
        address_hierarchy = _load_bicol_address_hierarchy()
    except Exception as error:
        st.error(f"Unable to load patient statistics: {error}")
        return

    with st.container(key="admin-statistics-page"):
        st.html(STATISTICS_ANALYTICS_STYLES)
        with st.container(key="statistics-intro"):
            st.markdown(
                """
                <div class="statistics-eyebrow">Regional Analytics</div>
                <h1 class="statistics-title">Patient Statistics</h1>
                <p class="statistics-description">
                  Explore patient distribution and status across Bicol Region.
                </p>
                """,
                unsafe_allow_html=True,
            )

        overview_tab, age_tab, gender_tab, engagement_tab = st.tabs(
            ["Overview", "Age", "Gender", "Portal Engagement"],
            key="patient_statistics_sections",
            on_change="rerun",
        )
        show_location_filters = (
            overview_tab.open or age_tab.open or gender_tab.open
        )

        for column in ("province", "city_municipality", "barangay", "purok"):
            df[column] = df[column].map(_normalize_location)
        df["province_key"] = df["province"].map(_location_key)
        df["city_key"] = df["city_municipality"].map(_location_key)
        df["barangay_key"] = df["barangay"].map(_location_key)
        df["status"] = df["status"].fillna(CARE_STATUS_LOST_TO_FOLLOW_UP)

        province_options = list(address_hierarchy)
        province = st.session_state.get("geo_province")
        city = st.session_state.get("geo_city")
        barangay = st.session_state.get("geo_barangay")
        province_record = address_hierarchy.get(province)
        municipality_options = (
            [item["name"] for item in province_record["municipalities"]]
            if province_record
            else []
        )
        municipality = next(
            (
                item
                for item in province_record["municipalities"]
                if item["name"] == city
            ),
            None,
        ) if province_record and city else None
        barangay_options = (
            [item["name"] for item in municipality["barangays"]]
            if municipality
            else []
        )

        if show_location_filters:
            active_location_tab = next(
                tab
                for tab in (overview_tab, age_tab, gender_tab)
                if tab.open
            )
            with active_location_tab:
                with st.container(border=True, key="statistics-filters"):
                    province_column, city_column, barangay_column = st.columns(3)
                    with province_column:
                        province = st.selectbox(
                            "Province",
                            province_options,
                            index=None,
                            placeholder="Choose a Bicol province",
                            key="geo_province",
                            on_change=_reset_city_selection,
                        )

                    province_record = address_hierarchy.get(province)
                    municipality_options = (
                        [item["name"] for item in province_record["municipalities"]]
                        if province_record
                        else []
                    )
                    with city_column:
                        city = st.selectbox(
                            "Municipality / City",
                            municipality_options,
                            index=None,
                            placeholder=(
                                "Choose a province first"
                                if province is None
                                else "Choose a municipality or city"
                            ),
                            key="geo_city",
                            disabled=province is None,
                            on_change=_reset_barangay_selection,
                        )

                    municipality = next(
                        (
                            item
                            for item in province_record["municipalities"]
                            if item["name"] == city
                        ),
                        None,
                    ) if province_record and city else None
                    barangay_options = (
                        [item["name"] for item in municipality["barangays"]]
                        if municipality
                        else []
                    )
                    with barangay_column:
                        barangay = st.selectbox(
                            "Barangay",
                            barangay_options,
                            index=None,
                            placeholder=(
                                "Choose a municipality or city first"
                                if city is None
                                else "Choose a barangay"
                            ),
                            key="geo_barangay",
                            disabled=city is None,
                        )

        selected_data = df
        province_data = df.iloc[0:0]
        city_data = df.iloc[0:0]
        barangay_data = df.iloc[0:0]
        if province is not None:
            province_data = df[df["province_key"] == _location_key(province)]
            selected_data = province_data
        if city is not None:
            city_data = province_data[
                province_data["city_key"] == _location_key(city)
            ]
            selected_data = city_data
        if barangay is not None:
            barangay_data = city_data[
                city_data["barangay_key"] == _location_key(barangay)
            ]
            selected_data = barangay_data

        with overview_tab:
            with st.container(horizontal=True, key="statistics-kpis"):
                st.metric(
                    "Active",
                    f"{int((selected_data['status'] == CARE_STATUS_ACTIVE).sum()):,}",
                    border=True,
                )
                st.metric(
                    "Lost to Follow-Up",
                    f"{int((selected_data['status'] == CARE_STATUS_LOST_TO_FOLLOW_UP).sum()):,}",
                    border=True,
                )
                st.metric(
                    "Deceased",
                    f"{int((selected_data['status'] == CARE_STATUS_DECEASED).sum()):,}",
                    border=True,
                )

            growth_column, status_column = st.columns([1.55, 1])
            with growth_column:
                with st.container(border=True, key="statistics-growth-card"):
                    st.markdown(
                        '<div class="statistics-card-eyebrow">Patient Growth</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown("### Monthly Registrations")
                    _render_registration_chart(selected_data)
            with status_column:
                with st.container(border=True, key="statistics-status-card"):
                    st.markdown(
                        '<div class="statistics-card-eyebrow">Patient Status</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown("### Current Distribution")
                    _render_status_distribution(selected_data)

            if province is None:
                chart_data = _location_counts(
                    df,
                    "province",
                    "Province",
                    province_options,
                )
                chart_title = "Patients by Province"
                category_label = "Province"
            elif city is None:
                chart_data = _location_counts(
                    province_data,
                    "city_municipality",
                    "Municipality / City",
                    municipality_options,
                )
                chart_title = f"Patients by Municipality / City in {province}"
                category_label = "Municipality / City"
            elif barangay is None:
                chart_data = _location_counts(
                    city_data,
                    "barangay",
                    "Barangay",
                    barangay_options,
                )
                chart_title = f"Patients by Barangay in {city}"
                category_label = "Barangay"
            else:
                chart_data = _location_counts(
                    barangay_data,
                    "purok",
                    "Purok",
                )
                chart_title = f"Patients by Purok in {barangay}"
                category_label = "Purok"

            with st.container(border=True, key="statistics-distribution"):
                st.markdown(
                    '<div class="statistics-card-eyebrow">Geographic Breakdown</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"### {chart_title}")
                chart_column, table_column = st.columns([1, 1.2])
                with chart_column:
                    _render_distribution_chart(
                        chart_data,
                        category_label,
                        len(selected_data),
                    )
                with table_column:
                    st.dataframe(
                        chart_data,
                        hide_index=True,
                        width="stretch",
                        height="content",
                        alt=f"{chart_title} with patient counts",
                    )

            if df.empty:
                st.info(
                    "No patient record folders have been archived yet. "
                    "Statistics will appear once records are submitted."
                )

        with age_tab:
            age_counts = _age_group_counts(selected_data)
            top_age_group, known_age_total = _top_age_group_summary(selected_data)
            with st.container(horizontal=True, key="statistics-age-summary"):
                st.metric(
                    "Total Filtered Patients",
                    f"{len(selected_data):,}",
                    border=True,
                )
                st.metric(
                    "Top Age Group",
                    top_age_group,
                    border=True,
                )
                st.metric(
                    "Records with Age Data",
                    f"{known_age_total:,}",
                    border=True,
                )

            with st.container(
                border=True,
                key="statistics-age-distribution",
            ):
                st.markdown(
                    '<div class="statistics-card-eyebrow">Age Distribution</div>',
                    unsafe_allow_html=True,
                )
                st.markdown("### Patients by Age Group")
                chart_column, table_column = st.columns([1, 1.2])
                with chart_column:
                    _render_age_group_chart(age_counts)
                with table_column:
                    age_table = pd.DataFrame(
                        {
                            "Age Group": list(AGE_GROUPS),
                            "Patient Count": [
                                int(age_counts[group]) for group in AGE_GROUPS
                            ],
                        }
                    )
                    _render_analytics_table(age_table, "Age Group")

        with gender_tab:
            gender_counts = _gender_counts(selected_data)
            with st.container(key="statistics-gender-summary"):
                total_column, male_column, female_column, others_column = (
                    st.columns(4)
                )
                with total_column:
                    st.metric(
                        "Total Filtered Patients",
                        f"{len(selected_data):,}",
                        border=True,
                    )
                with male_column:
                    st.metric(
                        "Male Patients",
                        f"{int(gender_counts['Male']):,}",
                        border=True,
                    )
                with female_column:
                    st.metric(
                        "Female Patients",
                        f"{int(gender_counts['Female']):,}",
                        border=True,
                    )
                with others_column:
                    st.metric(
                        "Others",
                        f"{int(gender_counts['Others']):,}",
                        border=True,
                    )

            with st.container(
                border=True,
                key="statistics-gender-distribution",
            ):
                st.markdown(
                    '<div class="statistics-card-eyebrow">Gender Distribution</div>',
                    unsafe_allow_html=True,
                )
                st.markdown("### Patients by Gender")
                chart_column, table_column = st.columns([1, 1.2])
                with chart_column:
                    _render_gender_chart(gender_counts)
                with table_column:
                    gender_table = pd.DataFrame(
                        {
                            "Gender": list(GENDER_GROUPS),
                            "Patient Count": [
                                int(gender_counts[group])
                                for group in GENDER_GROUPS
                            ],
                        }
                    )
                    _render_analytics_table(
                        gender_table,
                        "Gender",
                        category_colors=dict(zip(GENDER_GROUPS, GENDER_COLORS)),
                    )

        with engagement_tab:
            if engagement_tab.open:
                snapshot, source, error_message = _load_portal_engagement_snapshot()
                if source == "unavailable":
                    st.warning(
                        "Supabase is unavailable and no cached engagement snapshot "
                        "is available yet. Open this tab while connected to create one."
                    )

                if error_message:
                    if source == "online_uncached":
                        st.warning(error_message)
                    else:
                        st.error(error_message)
                _render_portal_engagement(snapshot)


if __name__ == "__main__":
    show_dashboard_page()
