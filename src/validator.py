import argparse
import json
import sys
from datetime import datetime, timezone

import pandas as pd
import pandera.pandas as pa

from src import config

MAG_TYPES = ["mb", "ml", "mww", "md", "mwr", "mb_lg", "mw", "mwb", "ms_vx"]
STATUSES = ["automatic", "reviewed"]


def to_ms(date_string):
    moment = datetime.strptime(date_string, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


def time_in_period(series):
    # custom check: event time (ms UTC) must be inside START_TIME..END_TIME
    return (series >= to_ms(config.START_TIME)) & (series < to_ms(config.END_TIME))


def first_occurrence(series):
    # a repeated id is an error, but the first record with this id stays valid
    return ~series.duplicated(keep="first")


def not_blank(series):
    return series.astype(str).str.strip().ne("") & series.notna()


def build_schema():
    return pa.DataFrameSchema(
        {
            "id": pa.Column(str, checks=[pa.Check(not_blank, error="id is empty"), pa.Check(first_occurrence, error="duplicate id")], nullable=False),
            "mag": pa.Column(float, checks=pa.Check.in_range(-1, 10), nullable=False),
            "magType": pa.Column(str, checks=pa.Check.isin(MAG_TYPES), nullable=False),
            "place": pa.Column(str, checks=pa.Check(not_blank, error="place is empty"), nullable=False),
            "time": pa.Column(int, checks=pa.Check(time_in_period, error="time outside the period"), nullable=False),
            "updated": pa.Column(int, nullable=False),
            "latitude": pa.Column(float, checks=pa.Check.in_range(-90, 90), nullable=False),
            "longitude": pa.Column(float, checks=pa.Check.in_range(-180, 180), nullable=False),
            # depth is allowed to be negative: the point can be above sea level
            "depth": pa.Column(float, checks=pa.Check.in_range(-10, 800), nullable=False),
            "status": pa.Column(str, checks=pa.Check.isin(STATUSES), nullable=False),
            "tsunami": pa.Column(int, checks=pa.Check.isin([0, 1]), nullable=False),
        },
        strict=False,   # other columns (gap, dmin, alert, ...) may have NaN and are not checked here
        coerce=False,
    )


def load_consumed():
    with open(config.CONSUMED_JSON_PATH, encoding="utf-8") as file:
        records = json.load(file)
    return pd.DataFrame(records)


def reason_text(row):
    return f"{row['column']}: {row['check']} (value={row['failure_case']})"


def prepare_types(df):
    # JSON null in an int column gives float64 with NaN; keep real ints where there are no gaps
    df = df.copy()
    for column in ("time", "updated", "tsunami"):
        if column in df and df[column].notna().all():
            df[column] = df[column].astype("int64")
    return df


def validate(df):
    """Return (valid_df, invalid_df, errors_df). Invalid rows are not dropped silently."""
    df = prepare_types(df).reset_index(drop=True)
    schema = build_schema()
    try:
        schema.validate(df, lazy=True)
        errors = pd.DataFrame(columns=["column", "check", "index", "failure_case"])
    except pa.errors.SchemaErrors as error:
        errors = error.failure_cases[["column", "check", "index", "failure_case"]].copy()
    row_errors = errors.dropna(subset=["index"]).copy()
    row_errors["index"] = row_errors["index"].astype(int)
    row_errors["reason"] = row_errors.apply(reason_text, axis=1)
    reasons = row_errors.groupby("index")["reason"].agg("; ".join)
    bad_index = reasons.index
    invalid_df = df.loc[bad_index].copy()
    invalid_df["reason"] = reasons
    valid_df = df.drop(index=bad_index)
    return valid_df, invalid_df, errors


def inject_test_records(df):
    base = df.iloc[0].to_dict()
    bad = []
    for suffix, change in (
        ("BAD_MAG", {"mag": 15.0}),
        ("BAD_LAT", {"latitude": 200.0}),
        ("BAD_MAGTYPE", {"magType": "xyz"}),
        ("BAD_TIME", {"time": to_ms(config.START_TIME) - 86400000}),
    ):
        bad.append({**base, "id": f"TEST_{suffix}", **change})
    bad.append({**base, "id": df.iloc[1]["id"]})   # duplicate id of a real record
    bad.append({**base, "id": "TEST_DUP", "place": ""})
    return pd.concat([df, pd.DataFrame(bad)], ignore_index=True), len(bad)


def save_outputs(valid_df, invalid_df):
    config.ensure_dirs()
    valid_df.to_csv(config.VALID_CSV_PATH, index=False)
    invalid_df.to_csv(config.INVALID_CSV_PATH, index=False)


def summarize(errors):
    if errors.empty:
        return "no errors"
    counts = errors.groupby(["column", "check"]).size()
    return "\n".join(f"  {column:<10} {(str(check) if len(str(check)) <= 40 else str(check)[:37] + "..."):<42} {number}" for (column, check), number in counts.items())


def run(test=False):
    df = load_consumed()
    print(f"Loaded {len(df)} consumed records")
    injected = 0
    if test:
        df, injected = inject_test_records(df)
        print(f"TEST mode: injected {injected} bad records")
    valid_df, invalid_df, errors = validate(df)
    save_outputs(valid_df, invalid_df)
    stats = {"valid": len(valid_df), "invalid": len(invalid_df), "test_records_injected": injected}
    config.save_stats("validator", stats)
    print(f"Valid: {len(valid_df)}")
    print(f"Invalid: {len(invalid_df)}")
    print("Errors by rule:")
    print(summarize(errors))
    if not invalid_df.empty:
        print("Invalid records (quarantine):")
        for _, row in invalid_df.head(15).iterrows():
            print(f"  {row['id']:<18} {row['reason']}")
    if test:
        test_ids = set(df["id"][df["id"].astype(str).str.startswith("TEST_")])
        leaked = test_ids & set(valid_df["id"])
        caught = test_ids & set(invalid_df["id"])
        print(f"Test records caught: {len(caught)} of {len(test_ids)}, leaked to valid: {len(leaked)}")
        if leaked:
            print("ERROR: bad test records got into valid_records.csv")
            sys.exit(1)
    return valid_df, invalid_df, errors


def parse_args():
    parser = argparse.ArgumentParser(description="Validate consumed earthquakes with Pandera")
    parser.add_argument("--test", action="store_true", help="inject bad records and check that the schema catches them")
    return parser.parse_args()


def main():
    args = parse_args()
    if not config.CONSUMED_JSON_PATH.exists():
        print(f"ERROR: {config.CONSUMED_JSON_PATH.name} not found, run: python -m src.consumer")
        sys.exit(1)
    run(test=args.test)


if __name__ == "__main__":
    main()
