"""Runs the whole pipeline: API -> Kafka -> Consumer -> Pandera -> pandas/NumPy -> SQLite -> EDA.

Run: python main.py          (Kafka broker must be running: docker compose up -d)
Every stage reads the output of the previous one. If a stage fails, the pipeline stops
with a non-zero exit code. The final table is built from data/stats/*.json, not typed by hand.
"""
import subprocess
import sys

from src import config

# (description, module, extra arguments)
STAGES = [
    ("1. Kafka topic reset (delete + create)", "src.kafka_admin", ["--reset"]),
    ("2. API client (data collection)", "src.api_client", []),
    ("3. Kafka Producer (publish)", "src.producer", []),
    ("4. Kafka Consumer (consume)", "src.consumer", []),
    ("5. Pandera validation", "src.validator", []),
    ("6. Cleaning and transformation", "src.cleaner", []),
    ("7. SQLite loader (first load + second load = idempotency test)", "src.loader", ["--idempotency-test"]),
    ("8. SQL verification queries", "src.loader", ["--verify"]),
    ("9. EDA and figures", "src.analysis", []),
]


def remove_old_database():
    """Start the loading stage from an empty database so that the counts are comparable."""
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
        print(f"[INFO] Old database {config.DB_PATH.name} removed")


def run_stage(description, module, arguments):
    print(f"\n[RUNNING] {description}")
    command = [sys.executable, "-m", module, *arguments]  # same Python/venv as main.py
    result = subprocess.run(command)
    if result.returncode != 0:
        print(f"[ERROR] Stage failed: {description} (exit code {result.returncode})")
        print("Check the message above. If it is a Kafka error, run: docker compose up -d")
        sys.exit(result.returncode)
    print(f"[SUCCESS] {description}")


def get_stat(stage, key):
    stats = config.load_stats(stage)
    if stats is None or key not in stats:
        return None
    return stats[key]


def show(value):
    return "n/a" if value is None else str(value)


def print_summary():
    collected = get_stat("api", "collected")
    published = get_stat("producer", "published")
    consumed = get_stat("consumer", "consumed")
    valid = get_stat("validator", "valid")
    invalid = get_stat("validator", "invalid")
    cleaned = get_stat("cleaner", "cleaned_output")
    stored = get_stat("loader", "stored")
    stored_second = get_stat("loader", "stored_after_second_run")

    rows = [
        ("Collected from API", collected),
        ("Published to Kafka", published),
        ("Consumed from Kafka", consumed),
        ("Valid (Pandera)", valid),
        ("Invalid (quarantine)", invalid),
        ("After cleaning", cleaned),
        ("Stored in SQLite", stored),
        ("Stored after 2nd load", stored_second),
    ]
    print("\n" + "=" * 52)
    print("PIPELINE EXECUTION STATISTICS")
    print("=" * 52)
    for name, value in rows:
        print(f"{name:<26} | {show(value):>8}")
    print("=" * 52)

    print("Explanation of differences:")
    if None in (collected, published, consumed, valid, invalid, cleaned, stored):
        print("  Some stats files are missing, see the 'n/a' values above.")
        return
    print(f"  collected -> published: {collected - published} lost in the producer (expected 0).")
    print(f"  published -> consumed:  {published - consumed} lost in the consumer (expected 0).")
    print(f"  consumed -> valid:      {consumed - valid} records rejected by Pandera "
          f"(invalid = {invalid}, saved in data/invalid_records.csv).")
    print(f"  valid -> cleaned:       {valid - cleaned} records removed by cleaning "
          f"(duplicates by id + filter: status=reviewed, mag>=3.0, sig>=50).")
    print(f"  cleaned -> stored:      {cleaned - stored} difference "
          f"(expected 0: primary key id, one row per earthquake).")
    if stored_second is not None:
        status = "OK, no duplicates" if stored_second == stored else "ERROR, rows changed"
        print(f"  second load:            {stored} -> {stored_second} rows ({status}).")


def main():
    for description, module, arguments in STAGES:
        if module == "src.loader" and "--idempotency-test" in arguments:
            remove_old_database()
        run_stage(description, module, arguments)
    print_summary()
    print("\nPipeline finished successfully.")


if __name__ == "__main__":
    main()
