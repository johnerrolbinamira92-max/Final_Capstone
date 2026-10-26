import streamlit as st
import pandas as pd
from database import get_local_connection


def _render_distribution_card(title, data, category_column, count_column, color, alt):
    sorted_data = data.sort_values(count_column, ascending=False)
    chart_data = sorted_data.head(10)
    chart_height = max(220, min(360, 38 * (len(chart_data) + 2)))

    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.bar_chart(
            chart_data,
            x=category_column,
            y=count_column,
            color=color,
            horizontal=True,
            sort=False,
            height=chart_height,
            width="stretch",
            alt=alt,
        )
        if len(sorted_data) > len(chart_data):
            st.caption("Chart shows the 10 most common categories; the table includes all categories.")
        st.dataframe(
            sorted_data,
            hide_index=True,
            width="stretch",
            height=min(320, max(120, 38 * (len(sorted_data) + 1))),
            alt=f"{title} counts",
        )


def show_dashboard_page():
    try:
        conn = get_local_connection()
        query = "SELECT city_municipality, province, status, total_annual_income, poverty_rating FROM patients"
        try:
            df = pd.read_sql_query(query, conn)
        finally:
            conn.close()

        total_records = len(df)
        st.title("Patient Statistics")
        st.write("A summary of archived records, demographics, and household income.")

        records_col, selector_col = st.columns([1, 3], vertical_alignment="bottom")
        with records_col:
            st.metric("Total records", total_records, border=True)
        with selector_col:
            analytics_view = st.selectbox(
                "Statistics category",
                [
                    "Patient Administrative Status",
                    "Geographical Regional Distributions",
                    "Socio-Economic Income Classifications",
                ],
                index=None,
                placeholder="Choose a statistics category",
            )

        if df.empty:
            st.info("No patient record folders have been archived yet. Statistics will appear once records are submitted.")
            return

        if analytics_view is None:
            return

        if analytics_view == "Patient Administrative Status":
            st.markdown("### Current Patient Administrative Status")
            df["status"] = df["status"].fillna("Alive").str.strip().str.title()
            status_counts = df["status"].value_counts()
            alive_count = int(status_counts.get("Alive", 0))
            deceased_count = int(status_counts.get("Deceased", 0))

            m1, m2 = st.columns(2)
            with m1:
                st.metric(label="Active (Alive) Patients", value=alive_count, border=True)
            with m2:
                st.metric(label="Deceased Records", value=deceased_count, border=True)

            status_df = pd.DataFrame({
                "Administrative Status": ["Alive", "Deceased"],
                "Total Patients": [alive_count, deceased_count],
            })
            _render_distribution_card(
                "Patient records by status",
                status_df,
                "Administrative Status",
                "Total Patients",
                "#0796A1",
                "Patient counts for active and deceased administrative statuses",
            )

        elif analytics_view == "Geographical Regional Distributions":
            st.markdown("### Bicol Region Geographic Breakdown")
            geo_col1, geo_col2 = st.columns(2)
            
            with geo_col1:
                st.markdown("#### Municipalities and Cities")
                df["city_municipality"] = (
                    df["city_municipality"].fillna("Not Specified").str.strip().str.title()
                )
                city_counts = df["city_municipality"].value_counts().reset_index()
                city_counts.columns = ["Municipality / City", "Patient Count"]
                _render_distribution_card(
                    "Patient records by municipality or city",
                    city_counts,
                    "Municipality / City",
                    "Patient Count",
                    "#0796A1",
                    "Patient counts by municipality or city",
                )

            with geo_col2:
                st.markdown("#### Provinces")
                df["province"] = (
                    df["province"].fillna("Not Specified").str.strip().str.title()
                )
                province_counts = df["province"].value_counts().reset_index()
                province_counts.columns = ["Province", "Patient Count"]
                _render_distribution_card(
                    "Patient records by province",
                    province_counts,
                    "Province",
                    "Patient Count",
                    "#3671C8",
                    "Patient counts by province",
                )

        elif analytics_view == "Socio-Economic Income Classifications":
            st.markdown("### Socio-Economic Metrics")
            fin_col1, fin_col2 = st.columns(2)
            
            with fin_col1:
                st.markdown("#### Poverty Threshold Standings")
                df["poverty_rating"] = (
                    df["poverty_rating"].fillna("Unrated / Pending").str.strip().str.title()
                )
                pov_counts = df["poverty_rating"].value_counts().reset_index()
                pov_counts.columns = ["Poverty Rating Group", "Patient Count"]
                _render_distribution_card(
                    "Patient records by poverty rating",
                    pov_counts,
                    "Poverty Rating Group",
                    "Patient Count",
                    "#D08A2D",
                    "Patient counts by poverty rating group",
                )
                
            with fin_col2:
                st.markdown("#### Household Income")
                avg_income = df['total_annual_income'].mean()
                max_income = df['total_annual_income'].max()
                
                st.metric(
                    label="Average Annual Household Income",
                    value=f"₱ {avg_income:,.2f}",
                    border=True,
                )
                st.metric(
                    label="Highest Registered Household Income",
                    value=f"₱ {max_income:,.2f}",
                    border=True,
                )
                st.caption("Based on household income values in archived patient records.")

    except Exception as e:
        st.error(f"❌ Analytics Processing Failure: {e}")


if __name__ == "__main__":
    show_dashboard_page()
