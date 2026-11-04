import pandas as pd
import streamlit as st
from database import get_local_connection


def _normalize_location(value):
    if pd.isna(value) or not str(value).strip():
        return "Not Specified"
    return str(value).strip().title()


def _reset_barangay_selection():
    st.session_state["geo_barangay"] = None


def _reset_city_selection():
    st.session_state["geo_city"] = None
    st.session_state["geo_barangay"] = None


def _render_distribution_card(title, data, category_column, count_column, color, alt):
    sorted_data = data.sort_values(count_column, ascending=False)

    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.bar_chart(
            sorted_data,
            x=category_column,
            y=count_column,
            color=color,
            horizontal=False,
            sort=False,
            height=360,
            width="stretch",
            alt=alt,
        )
        st.dataframe(
            sorted_data,
            hide_index=True,
            width="stretch",
            height=min(500, max(120, 38 * (len(sorted_data) + 1))),
            alt=f"{title} counts",
        )


def _location_counts(data, group_column, label):
    counts = (
        data[group_column]
        .value_counts()
        .rename_axis(label)
        .reset_index(name="Patient Count")
    )
    return counts


def show_dashboard_page():
    try:
        conn = get_local_connection()
        try:
            df = pd.read_sql_query(
                """
                SELECT province, city_municipality, barangay, purok, status
                FROM patients
                """,
                conn,
            )
        finally:
            conn.close()

        st.title("Patient Statistics")
        st.write("Explore the geographical distribution of archived patient records.")

        if df.empty:
            total_col, alive_col, deceased_col = st.columns(3)
            total_col.metric("Total Patients", 0, border=True)
            alive_col.metric("Alive Patients", 0, border=True)
            deceased_col.metric("Deceased Patients", 0, border=True)
            st.info(
                "No patient record folders have been archived yet. "
                "Statistics will appear once records are submitted."
            )
            return

        for column in ("province", "city_municipality", "barangay", "purok"):
            df[column] = df[column].map(_normalize_location)
        df["status"] = df["status"].fillna("Alive").str.strip().str.title()

        province_options = sorted(df["province"].unique().tolist())
        province = st.selectbox(
            "Province",
            province_options,
            index=None,
            placeholder="Choose a province",
            key="geo_province",
            on_change=_reset_city_selection,
        )

        province_data = (
            df[df["province"] == province] if province else df.iloc[0:0]
        )
        city_options = sorted(province_data["city_municipality"].unique().tolist())
        city = st.selectbox(
            "City / Municipality",
            city_options,
            index=None,
            placeholder="Choose a province first",
            key="geo_city",
            disabled=province is None,
            on_change=_reset_barangay_selection,
        )

        city_data = (
            province_data[province_data["city_municipality"] == city]
            if city
            else province_data.iloc[0:0]
        )
        barangay_options = sorted(city_data["barangay"].unique().tolist())
        barangay = st.selectbox(
            "Barangay",
            barangay_options,
            index=None,
            placeholder="Choose a city / municipality first",
            key="geo_barangay",
            disabled=city is None,
        )

        selected_data = df
        location_label = "Overall"
        if province is not None:
            selected_data = selected_data[selected_data["province"] == province]
            location_label = province
        if city is not None:
            selected_data = selected_data[
                selected_data["city_municipality"] == city
            ]
            location_label = city
        if barangay is not None:
            selected_data = selected_data[selected_data["barangay"] == barangay]
            location_label = barangay

        total_col, alive_col, deceased_col = st.columns(3)
        total_col.metric(
            f"Total Patients — {location_label}",
            len(selected_data),
            border=True,
        )
        alive_col.metric(
            "Alive Patients",
            int((selected_data["status"] == "Alive").sum()),
            border=True,
        )
        deceased_col.metric(
            "Deceased Patients",
            int((selected_data["status"] == "Deceased").sum()),
            border=True,
        )

        if province is None:
            chart_data = _location_counts(df, "province", "Province")
            chart_title = "Patient records by province"
            category_label = "Province"
        elif city is None:
            chart_data = _location_counts(
                province_data, "city_municipality", "City / Municipality"
            )
            chart_title = f"Patient records by city / municipality in {province}"
            category_label = "City / Municipality"
        elif barangay is None:
            chart_data = _location_counts(city_data, "barangay", "Barangay")
            chart_title = f"Patient records by barangay in {city}"
            category_label = "Barangay"
        else:
            barangay_data = city_data[city_data["barangay"] == barangay]
            chart_data = _location_counts(barangay_data, "purok", "Purok")
            chart_title = f"Patient records by purok in {barangay}"
            category_label = "Purok"

        st.markdown("### Geographical Distribution")
        _render_distribution_card(
            chart_title,
            chart_data,
            category_label,
            "Patient Count",
            "#0796A1",
            chart_title,
        )

    except Exception as e:
        st.error(f"❌ Analytics Processing Failure: {e}")


if __name__ == "__main__":
    show_dashboard_page()
