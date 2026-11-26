import datetime
import json
import re

import pandas as pd
import streamlit as st


FAMILY_COLUMNS = [
    "Name",
    "Age",
    "Civil Status",
    "Educational Attainment",
    "Relation to Client",
    "Occupation",
    "Monthly Income",
]

FAMILY_SELECTBOX_OPTIONS = {
    "Civil Status": ["Single", "Married", "Widowed", "Separated", "Live-in"],
    "Educational Attainment": [
        "No Formal Education",
        "Elementary Level",
        "Elementary Graduate",
        "High School Level",
        "High School Graduate",
        "Vocational / Technical",
        "College Level",
        "College Graduate",
        "Postgraduate",
    ],
    "Relation to Client": [
        "Mother",
        "Father",
        "Spouse",
        "Son",
        "Daughter",
        "Brother",
        "Sister",
        "Grandparent",
        "Guardian",
        "Relative",
    ],
}

MEDICATION_COLUMNS = [
    "Date (1)",
    "FPZ (1)",
    "Date (2)",
    "FPZ (2)",
    "Date (3)",
    "FPZ (3)",
]

MEDICATION_COLUMN_LABELS = {
    "Date (1)": "Date",
    "FPZ (1)": "FPZ",
    "Date (2)": "Date",
    "FPZ (2)": "FPZ",
    "Date (3)": "Date",
    "FPZ (3)": "FPZ",
}

DATE_DISPLAY_FORMAT = "MM/DD/YYYY"


def family_column_config(dataframe):
    column_config = {}
    for column, preset_options in FAMILY_SELECTBOX_OPTIONS.items():
        options = list(preset_options)
        if column in dataframe:
            for value in dataframe[column].dropna().unique():
                option = value.item() if hasattr(value, "item") else value
                if option != "" and option not in options:
                    options.append(option)
        column_config[column] = st.column_config.SelectboxColumn(
            column,
            options=options,
        )
    return column_config


def parse_stored_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text[:10])
    except ValueError:
        try:
            return datetime.datetime.strptime(text, "%m/%d/%Y").date()
        except ValueError:
            return text


def format_date_for_display(value):
    parsed = parse_stored_date(value)
    if isinstance(parsed, datetime.date):
        return parsed.strftime("%m/%d/%Y")
    return str(parsed or "")


def dataframe_from_storage(value, columns):
    if not value:
        return pd.DataFrame(columns=columns)

    try:
        records = json.loads(value)
    except json.JSONDecodeError:
        lines = value.splitlines()
        if len(lines) < 2:
            return pd.DataFrame(columns=columns)

        rows = []
        for line in lines[1:]:
            if not line.strip():
                continue
            fields = re.split(r"\s{2,}", line.strip())
            if len(fields) != len(columns):
                if columns != MEDICATION_COLUMNS:
                    raise ValueError("Unable to parse a legacy stored table.")
                medication_row = {column: "" for column in columns}
                date_columns = columns[::2]
                fpz_columns = columns[1::2]
                next_date = 0
                next_fpz = 0
                for field in fields:
                    if field == "None" or re.match(r"^\d{4}-\d{2}-\d{2}", field):
                        if next_date < len(date_columns) and field != "None":
                            medication_row[date_columns[next_date]] = field
                        next_date += 1
                    else:
                        if next_fpz < len(fpz_columns):
                            medication_row[fpz_columns[next_fpz]] = field
                        next_fpz += 1
                rows.append(medication_row)
                continue
            rows.append(fields)
        dataframe = pd.DataFrame(rows, columns=columns)
        return _normalize_medication_dates(dataframe, columns)

    if not isinstance(records, list):
        raise ValueError("Stored table data must be a list of row records.")
    if columns == FAMILY_COLUMNS:
        legacy_labels = {
            "Full Name": "Name",
            "Monthly Income (PHP)": "Monthly Income",
        }
        normalized_records = []
        for record in records:
            normalized = dict(record)
            for legacy_label, current_label in legacy_labels.items():
                if current_label not in normalized and legacy_label in normalized:
                    normalized[current_label] = normalized[legacy_label]
                normalized.pop(legacy_label, None)
            normalized_records.append(normalized)
        records = normalized_records
        return pd.DataFrame(records, columns=columns)
    dataframe = (
        pd.DataFrame(records, columns=columns)
        if not records or columns == MEDICATION_COLUMNS
        else pd.DataFrame(records)
    )
    return _normalize_medication_dates(dataframe, columns)


def _normalize_medication_dates(dataframe, columns):
    if columns == MEDICATION_COLUMNS:
        for column in MEDICATION_COLUMNS:
            if column in MEDICATION_COLUMNS[::2]:
                dataframe[column] = dataframe[column].map(parse_stored_date)
            else:
                dataframe[column] = dataframe[column].fillna("")
    return dataframe


def dataframe_to_storage(dataframe):
    return json.dumps(dataframe.to_dict(orient="records"), default=str)
