import argparse
import sys

import numpy as np
import pandas as pd

from src import config

EARTH_RADIUS_KM = 6371.0


def load_valid():
    if not config.VALID_CSV_PATH.exists():
        print(f"ERROR: {config.VALID_CSV_PATH.name} not found, run: python -m src.validator")
        sys.exit(1)
    return pd.read_csv(config.VALID_CSV_PATH)


def report_missing(df):
    missing = df.isna().sum()
    missing = missing[missing > 0].sort_values(ascending=False)
    print("Missing values before cleaning:")
    if missing.empty:
        print("  none")
    else:
        for column, number in missing.items():
            print(f"  {column:<10} {number:>5} ({number / len(df):.1%})")
    return missing


def convert_types(df):
    # time/updated come from the API as milliseconds since epoch -> real datetime
    df = df.copy()
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    df["updated"] = pd.to_datetime(df["updated"], unit="ms", utc=True)
    for column in ("mag", "latitude", "longitude", "depth", "sig", "gap", "dmin", "rms"):
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce").astype("float64")
    df["tsunami"] = df["tsunami"].astype("int64")
    return df


def handle_missing(df):
    # Optional measurement columns: keep the record, mark the gap explicitly.
    # Mandatory columns (id, mag, place, time, lat, lon) are already guaranteed
    # by the Pandera schema, so we only fill the optional ones here.
    df = df.copy()
    optional_numeric = ["nst", "gap", "dmin", "rms", "felt", "sig"]
    for column in optional_numeric:
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    # alert is a categorical warning level; NaN means "no alert issued"
    if "alert" in df:
        df["alert"] = df["alert"].fillna("none")
    return df


def remove_duplicates(df):
    before = len(df)
    df = df.drop_duplicates(subset=["id"], keep="first").reset_index(drop=True)
    print(f"Duplicates removed by id: {before - len(df)}")
    return df


def normalize_text(df):
    df = df.copy()
    for column in ("magType", "status", "type", "alert", "net", "place"):
        if column in df:
            df[column] = df[column].astype(str).str.strip()
    df["magType"] = df["magType"].str.lower()
    df["status"] = df["status"].str.lower()
    df["place"] = df["place"].str.replace(r"\s+", " ", regex=True)
    # region = text after " of " / ", " in "12 km NE of City, Country"
    df["region"] = (
        df["place"].str.split(" of ").str[-1].str.split(", ").str[-1].str.strip()
    )
    return df


def numpy_features(df):
    df = df.copy()
    # radian conversion for the haversine distance to the equator
    lat_rad = np.radians(df["latitude"].to_numpy())
    df["distance_from_equator_km"] = np.abs(lat_rad) * EARTH_RADIUS_KM
    # energy proxy: log10 of radiated energy (Gutenberg-Richter)
    df["energy_log10_j"] = 1.5 * df["mag"].to_numpy() + 4.8
    # depth bands via np.select (faster than apply for large data)
    conditions = [df["depth"] < 70, df["depth"] < 300]
    df["depth_band"] = np.select(conditions, ["shallow", "intermediate"], default="deep")
    # severity score normalising magnitude to 0..1
    df["severity_score"] = np.clip((df["mag"] - df["mag"].min()) / (df["mag"].max() - df["mag"].min()), 0, 1)
    return df


def filter_data(df):
    # keep only reviewed events that are strong enough and located in the ocean/land dataset
    before = len(df)
    mask = (df["status"] == "reviewed") & (df["mag"] >= 3.0) & (df["sig"] >= 50)
    filtered = df.loc[mask].reset_index(drop=True)
    print(f"Filtered out {before - len(filtered)} records, kept {len(filtered)}")
    return filtered


def groupby_summary(df):
    summary = (
        df.groupby("depth_band")
        .agg(
            events=("id", "count"),
            avg_mag=("mag", "mean"),
            max_mag=("mag", "max"),
            avg_depth=("depth", "mean"),
        )
        .round(2)
        .reset_index()
    )
    print("GroupBy depth_band:")
    print(summary.to_string(index=False))
    summary.to_csv(config.DATA_DIR / "depth_band_summary.csv", index=False)
    return summary


def reshape(df):
    # pivot: average magnitude by depth band and tsunami flag
    pivot = df.pivot_table(
        index="depth_band",
        columns="tsunami",
        values="mag",
        aggfunc="mean",
    ).round(2)
    pivot.to_csv(config.DATA_DIR / "pivot_depth_tsunami.csv")
    print("Pivot table (mean magnitude by depth_band x tsunami):")
    print(pivot.to_string())

    # melt: long format of selected numeric columns for later analysis
    long_df = df[["id", "mag", "depth", "sig"]].melt(
        id_vars="id", var_name="metric", value_name="value"
    )
    long_df.to_csv(config.DATA_DIR / "melt_metrics.csv", index=False)
    print(f"Melted table saved: {len(long_df)} rows")
    return pivot, long_df


def run():
    config.ensure_dirs()
    df = load_valid()
    print(f"Loaded valid records: {len(df)}")
    report_missing(df)
    df = convert_types(df)
    df = handle_missing(df)
    df = remove_duplicates(df)
    df = normalize_text(df)
    df = numpy_features(df)
    groupby_summary(df)
    reshape(df)
    df = filter_data(df)

    df.to_csv(config.CLEANED_CSV_PATH, index=False)
    stats = {
        "valid_input": len(load_valid()),
        "cleaned_output": len(df),
        "unique_ids": int(df["id"].nunique()),
        "depth_bands": df["depth_band"].value_counts().to_dict(),
    }
    config.save_stats("cleaner", stats)
    print(f"Cleaned records: {len(df)}")
    print(f"Saved: {config.CLEANED_CSV_PATH.name}")
    return df


def parse_args():
    parser = argparse.ArgumentParser(description="Clean and transform validated earthquakes")
    return parser.parse_args()


def main():
    parse_args()
    run()


if __name__ == "__main__":
    main()
