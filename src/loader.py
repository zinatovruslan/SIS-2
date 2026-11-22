import argparse
import sqlite3
import sys

import pandas as pd

from src import config

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS earthquakes (
    id                    TEXT    PRIMARY KEY,
    mag                   REAL    NOT NULL,
    mag_type              TEXT    NOT NULL,
    place                 TEXT    NOT NULL,
    region                TEXT,
    time_utc              TEXT    NOT NULL,
    updated_utc           TEXT    NOT NULL,
    latitude              REAL    NOT NULL,
    longitude             REAL    NOT NULL,
    depth_km              REAL    NOT NULL,
    depth_band            TEXT    NOT NULL,
    sig                   REAL,
    tsunami               INTEGER NOT NULL CHECK (tsunami IN (0, 1)),
    status                TEXT    NOT NULL,
    alert                 TEXT,
    net                   TEXT,
    distance_from_equator_km REAL,
    energy_log10_j        REAL,
    severity_score        REAL,
    loaded_at             TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

COLUMN_MAP = {
    "id": "id",
    "mag": "mag",
    "magType": "mag_type",
    "place": "place",
    "region": "region",
    "time": "time_utc",
    "updated": "updated_utc",
    "latitude": "latitude",
    "longitude": "longitude",
    "depth": "depth_km",
    "depth_band": "depth_band",
    "sig": "sig",
    "tsunami": "tsunami",
    "status": "status",
    "alert": "alert",
    "net": "net",
    "distance_from_equator_km": "distance_from_equator_km",
    "energy_log10_j": "energy_log10_j",
    "severity_score": "severity_score",
}


def connect():
    return sqlite3.connect(config.DB_PATH)


def prepare_frame(df):
    df = df.copy()
    df = df.rename(columns=COLUMN_MAP)
    keep = list(COLUMN_MAP.values())
    df = df[[column for column in keep if column in df.columns]]
    for column in ("time_utc", "updated_utc"):
        df[column] = pd.to_datetime(df[column], utc=True, format="ISO8601").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return df


def insert(df, verbose=True):
    prepared = prepare_frame(df)
    with connect() as connection:
        connection.execute(CREATE_TABLE_SQL)
        before = connection.execute("SELECT COUNT(*) FROM earthquakes").fetchone()[0]
        columns = list(prepared.columns)
        placeholders = ", ".join("?" for _ in columns)
        sql = (
            f"INSERT OR IGNORE INTO earthquakes ({', '.join(columns)}) "
            f"VALUES ({placeholders})"
        )
        rows = list(prepared.itertuples(index=False, name=None))
        connection.executemany(sql, rows)
        after = connection.execute("SELECT COUNT(*) FROM earthquakes").fetchone()[0]
    inserted = after - before
    if verbose:
        print(f"Records processed: {len(prepared)}")
        print(f"Rows before insert: {before}")
        print(f"Rows after insert:  {after}")
        print(f"New rows inserted:  {inserted}")
        print(f"Skipped (already present by id): {len(prepared) - inserted}")
    return {"processed": len(prepared), "before": before, "after": after, "inserted": inserted}


def verify():
    with connect() as connection:
        total = connection.execute("SELECT COUNT(*) FROM earthquakes").fetchone()[0]
        distinct = connection.execute("SELECT COUNT(DISTINCT id) FROM earthquakes").fetchone()[0]
        print(f"Rows in table:          {total}")
        print(f"Distinct ids:           {distinct}")
        print(f"Duplicate ids:          {total - distinct}")
        print("\nTop 5 strongest events:")
        for row in connection.execute(
            "SELECT id, mag, place, time_utc FROM earthquakes ORDER BY mag DESC LIMIT 5"
        ):
            print(f"  {row[0]:<20} mag={row[1]:<5} {row[3]}  {row[2]}")
        print("\nCount by depth_band:")
        for band, count in connection.execute(
            "SELECT depth_band, COUNT(*) FROM earthquakes GROUP BY depth_band ORDER BY 2 DESC"
        ):
            print(f"  {band:<14} {count}")
        print("\nAverage magnitude by tsunami flag:")
        for flag, avg in connection.execute(
            "SELECT tsunami, ROUND(AVG(mag), 3) FROM earthquakes GROUP BY tsunami"
        ):
            print(f"  tsunami={flag}: {avg}")


def run(idempotency_test=False):
    if not config.CLEANED_CSV_PATH.exists():
        print(f"ERROR: {config.CLEANED_CSV_PATH.name} not found, run: python -m src.cleaner")
        sys.exit(1)
    df = pd.read_csv(config.CLEANED_CSV_PATH)
    print(f"Loaded cleaned records: {len(df)}")

    first = insert(df)
    second = None
    if idempotency_test:
        print("\n--- Idempotency test: loading the same file a second time ---")
        second = insert(df)
        if second["inserted"] != 0 or second["after"] != first["after"]:
            print("ERROR: repeated load changed the database (not idempotent)")
            sys.exit(1)
        print("Idempotency OK: no duplicate records created")

    stats = {"processed": first["processed"], "stored": first["after"]}
    if second is not None:
        stats["stored_after_second_run"] = second["after"]
    config.save_stats("loader", stats)
    print(f"\nDatabase: {config.DB_PATH.name}")


def parse_args():
    parser = argparse.ArgumentParser(description="Load cleaned earthquakes into SQLite3")
    parser.add_argument("--idempotency-test", action="store_true",
                        help="insert the dataset twice and check no duplicates are created")
    parser.add_argument("--verify", action="store_true",
                        help="only run SQL verification queries")
    return parser.parse_args()


def main():
    args = parse_args()
    config.ensure_dirs()
    if args.verify:
        verify()
        return
    run(idempotency_test=args.idempotency_test)


if __name__ == "__main__":
    main()
