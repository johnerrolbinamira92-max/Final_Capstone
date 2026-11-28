import datetime
import json
import math
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
PERSON_NAME_PATTERN = r"[A-Za-zÀ-ÿÑñ\s.'-]+"
PERSON_NAME_INPUT_PATTERN = r"^[A-Za-zÀ-ÖØ-öø-ÿÑñ\s.'-]*$"
PERSON_NAME_INPUT_VALIDATION = (
    PERSON_NAME_INPUT_PATTERN,
    "Names must contain letters only and cannot include numbers.",
)
PERSON_NAME_VALIDATION_MESSAGE = (
    "Names must contain letters only and cannot include numbers."
)


def is_valid_person_name(value):
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    name = str(value).strip()
    return (
        not name
        or (
            re.fullmatch(PERSON_NAME_PATTERN, name) is not None
            and any(character.isalpha() for character in name)
            and all(
                character.isalpha()
                or character.isspace()
                or character in ".'-"
                for character in name
            )
        )
    )


def validate_person_names(fields):
    return [
        f"{label}: {PERSON_NAME_VALIDATION_MESSAGE}"
        for label, value in fields.items()
        if value is not None
        and str(value).strip()
        and not is_valid_person_name(value)
    ]


def family_column_config(dataframe):
    column_config = {}
    column_config["Name"] = st.column_config.TextColumn(
        "Name",
        validate=PERSON_NAME_INPUT_PATTERN,
    )
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
    column_config["Age"] = st.column_config.NumberColumn(
        "Age",
        min_value=0,
        max_value=120,
        step=1,
        format="%d",
    )
    column_config["Monthly Income"] = st.column_config.NumberColumn(
        "Monthly Income",
        min_value=0.0,
        step=0.01,
        format="%.2f",
    )
    return column_config


def validate_family_composition(dataframe):
    errors = []
    for row_number, (_, row) in enumerate(dataframe.iterrows(), start=1):
        name = row.get("Name")
        if not _is_empty_numeric_value(name) and not is_valid_person_name(name):
            errors.append(
                f"Family composition row {row_number}: "
                f"{PERSON_NAME_VALIDATION_MESSAGE}"
            )

        age = row.get("Age")
        if not _is_empty_numeric_value(age) and not _is_valid_family_age(age):
            errors.append(
                f"Family composition row {row_number}: Age must be a whole "
                "number from 0 to 120."
            )

        monthly_income = row.get("Monthly Income")
        if (
            not _is_empty_numeric_value(monthly_income)
            and not _is_valid_nonnegative_amount(monthly_income)
        ):
            errors.append(
                f"Family composition row {row_number}: Monthly Income must "
                "be a valid non-negative amount."
            )
    return errors


def _is_empty_numeric_value(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _is_valid_nonnegative_amount(value):
    try:
        amount = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(amount) and amount >= 0


def _is_valid_family_age(value):
    try:
        age = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(age) and age.is_integer() and 0 <= age <= 120


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
