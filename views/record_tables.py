import json
import re

import pandas as pd


FAMILY_COLUMNS = [
    "Full Name",
    "Age",
    "Civil Status",
    "Educational Attainment",
    "Relation to Client",
    "Occupation",
    "Monthly Income (PHP)",
]

MEDICATION_COLUMNS = [
    "Date (1)",
    "FPZ (1)",
    "Date (2)",
    "FPZ (2)",
    "Date (3)",
    "FPZ (3)",
]


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
        return pd.DataFrame(rows, columns=columns)

    if not isinstance(records, list):
        raise ValueError("Stored table data must be a list of row records.")
    return pd.DataFrame(records, columns=columns) if not records else pd.DataFrame(records)


def dataframe_to_storage(dataframe):
    return json.dumps(dataframe.to_dict(orient="records"), default=str)
