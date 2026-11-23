import json
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from database import get_local_connection
from views.map_utils import location_key as _base_location_key

BICOL_ADDRESS_FILE = (
    Path(__file__).resolve().parents[1] / "data" / "bicol_address_hierarchy.json"
)
AGE_GROUPS = (
    "Under 18",
    "18–24",
    "25–34",
    "35–49",
    "50+",
    "Unspecified",
)
GENDER_GROUPS = ("Male", "Female", "Other / Unspecified")
GENDER_COLORS = ("#43c4b5", "#e97954", "#91aba5")
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
.st-key-admin-statistics-page .st-key-statistics-age-distribution [data-testid="stVerticalBlockBorderWrapper"],
.st-key-admin-statistics-page .st-key-statistics-gender-distribution [data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid rgba(255, 255, 255, .08) !important;
    border-radius: 16px !important;
    background: #112926 !important;
    box-shadow: 0 8px 20px rgba(0, 0, 0, .12);
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


def _gender_counts(data):
    values = data["sex"].fillna("").astype(str).str.strip().str.casefold()
    groups = values.map({"male": "Male", "female": "Female"}).fillna(
        "Other / Unspecified"
    )
    return groups.value_counts().reindex(GENDER_GROUPS, fill_value=0)


def _render_analytics_table(data, category_label):
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(category))}</td>"
        f"<td>{int(count):,}</td>"
        "</tr>"
        for category, count in zip(
            data[category_label],
            data["Patient Count"],
        )
    )
    st.html(
        f'<table class="statistics-analytics-table" '
        f'aria-label="{escape(category_label)} patient counts">'
        "<thead><tr>"
        f"<th>{escape(category_label)}</th>"
        "<th>Patient Count</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table>",
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
        ("Alive", int(status_counts.get("Alive", 0)), "#00a394"),
        ("Deceased", int(status_counts.get("Deceased", 0)), "#e97954"),
    ]
    other_count = int(
        (~data["status"].isin(("Alive", "Deceased"))).sum()
    )
    if other_count:
        status_rows.append(("Other", other_count, "#a68bd1"))

    chart_data = pd.DataFrame(
        [
            {"Status": label, "Patients": count}
            for label, count, _ in status_rows
            if count > 0
        ]
    )
    chart_column, legend_column = st.columns([1.2, 1])
    with chart_column:
        if chart_data.empty:
            st.info("There are no patient records for this status distribution.")
        else:
            donut = (
                alt.Chart(chart_data)
                .mark_arc(innerRadius=65, outerRadius=108)
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
                .properties(height=260)
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
            st.altair_chart(
                (donut + total + label).properties(background="#182523"),
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
        return pd.read_sql_query(
            f"""
            SELECT {registered_date}, {calculated_age}, {sex},
                   province, city_municipality, barangay, purok, status
            FROM patients
            """,
            conn,
        )
    finally:
        conn.close()


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

        for column in ("province", "city_municipality", "barangay", "purok"):
            df[column] = df[column].map(_normalize_location)
        df["province_key"] = df["province"].map(_location_key)
        df["city_key"] = df["city_municipality"].map(_location_key)
        df["barangay_key"] = df["barangay"].map(_location_key)
        df["status"] = df["status"].fillna("Alive").str.strip().str.title()

        province_options = list(address_hierarchy)

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
        location_label = "All Patients"
        if province is not None:
            province_data = df[df["province_key"] == _location_key(province)]
            selected_data = province_data
            location_label = province
        if city is not None:
            city_data = province_data[
                province_data["city_key"] == _location_key(city)
            ]
            selected_data = city_data
            location_label = city
        if barangay is not None:
            barangay_data = city_data[
                city_data["barangay_key"] == _location_key(barangay)
            ]
            selected_data = barangay_data
            location_label = barangay

        geographical_tab, age_tab, gender_tab = st.tabs(
            ["Geographical", "Age", "Gender"]
        )
        with geographical_tab:
            with st.container(horizontal=True, key="statistics-kpis"):
                st.metric(
                    f"Total Patients · {location_label}",
                    f"{len(selected_data):,}",
                    border=True,
                )
                st.metric(
                    "Alive Patients",
                    f"{int((selected_data['status'] == 'Alive').sum()):,}",
                    border=True,
                )
                st.metric(
                    "Deceased Patients",
                    f"{int((selected_data['status'] == 'Deceased').sum()):,}",
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
            ages = pd.to_numeric(
                selected_data["calculated_age"],
                errors="coerce",
            )
            ages = ages[ages >= 0]
            average_age = f"{ages.mean():.1f} years" if not ages.empty else "—"
            known_age_counts = age_counts.drop("Unspecified")
            most_common_age_group = (
                str(known_age_counts.idxmax())
                if int(known_age_counts.sum()) > 0
                else "—"
            )
            with st.container(horizontal=True, key="statistics-age-summary"):
                st.metric(
                    "Total Filtered Patients",
                    f"{len(selected_data):,}",
                    border=True,
                )
                st.metric("Average Age", average_age, border=True)
                st.metric(
                    "Most Common Age Group",
                    most_common_age_group,
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
            with st.container(horizontal=True, key="statistics-gender-summary"):
                st.metric(
                    "Total Filtered Patients",
                    f"{len(selected_data):,}",
                    border=True,
                )
                st.metric(
                    "Male Patients",
                    f"{int(gender_counts['Male']):,}",
                    border=True,
                )
                st.metric(
                    "Female Patients",
                    f"{int(gender_counts['Female']):,}",
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
                    _render_analytics_table(gender_table, "Gender")


if __name__ == "__main__":
    show_dashboard_page()
