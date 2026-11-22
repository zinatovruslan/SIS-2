import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATS_DIR = DATA_DIR / "stats"
FIGURES_DIR = BASE_DIR / "figures"

RAW_GEOJSON_PATH = DATA_DIR / "raw_earthquakes_geojson.json"
RAW_JSON_PATH = DATA_DIR / "raw_earthquakes.json"
RAW_CSV_PATH = DATA_DIR / "raw_earthquakes.csv"
CONSUMED_JSON_PATH = DATA_DIR / "consumed_earthquakes.json"
VALID_CSV_PATH = DATA_DIR / "valid_records.csv"
INVALID_CSV_PATH = DATA_DIR / "invalid_records.csv"
CLEANED_CSV_PATH = DATA_DIR / "cleaned_earthquakes.csv"
DB_PATH = DATA_DIR / "earthquakes.db"

API_URL = os.getenv("API_URL", "https://earthquake.usgs.gov/fdsnws/event/1/query")
API_COUNT_URL = os.getenv("API_COUNT_URL", "https://earthquake.usgs.gov/fdsnws/event/1/count")
START_TIME = os.getenv("START_TIME", "2026-10-01")
END_TIME = os.getenv("END_TIME", "2026-11-01")
MIN_MAGNITUDE = float(os.getenv("MIN_MAGNITUDE", "2.5"))
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "1000"))
MAX_RECORDS = int(os.getenv("MAX_RECORDS", "5000"))
MIN_RECORDS = 200
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "earthquakes")
KAFKA_PARTITIONS = 1
KAFKA_REPLICATION_FACTOR = 1

FIELDS = [
    "id", "mag", "magType", "place", "time", "updated",
    "latitude", "longitude", "depth", "sig", "nst", "gap", "dmin", "rms",
    "status", "type", "alert", "tsunami", "felt", "net",
]


def ensure_dirs():
    for folder in (DATA_DIR, STATS_DIR, FIGURES_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def save_stats(stage, stats):
    ensure_dirs()
    path = STATS_DIR / f"{stage}.json"
    with open(path, "w", encoding="utf-8") as file:
        json.dump(stats, file, indent=2, ensure_ascii=False)
    return path


def load_stats(stage):
    path = STATS_DIR / f"{stage}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as file:
        return json.load(file)
