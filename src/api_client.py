import argparse
import json
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from src import config

RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


class ApiError(Exception):
    pass


def request_json(url, params):
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            response = requests.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as error:
            print(f"  attempt {attempt}/{config.MAX_RETRIES}: network error: {type(error).__name__}")
        else:
            if response.status_code == 204:
                return {"type": "FeatureCollection", "features": []}
            if response.status_code in RETRY_STATUS_CODES:
                print(f"  attempt {attempt}/{config.MAX_RETRIES}: server answered {response.status_code}")
            elif response.status_code != 200:
                message = response.text.strip().splitlines()
                details = message[2] if len(message) > 2 else response.text[:200]
                raise ApiError(f"API returned {response.status_code}: {details}")
            else:
                try:
                    return response.json()
                except ValueError:
                    raise ApiError("API response is not valid JSON")
        if attempt < config.MAX_RETRIES:
            wait_seconds = 2 ** attempt
            print(f"  waiting {wait_seconds} s before the next attempt")
            time.sleep(wait_seconds)
    raise ApiError(f"API is not available after {config.MAX_RETRIES} attempts")


def build_params(start_time, end_time, min_magnitude):
    return {
        "format": "geojson",
        "starttime": start_time,
        "endtime": end_time,
        "minmagnitude": min_magnitude,
        "orderby": "time",
    }


def get_total_count(params):
    data = request_json(config.API_COUNT_URL, params)
    if "count" not in data:
        raise ApiError("Count endpoint did not return a count")
    return data["count"]


def fetch_pages(params, total):
    pages = []
    offset = 1
    last_record = min(total, config.MAX_RECORDS)
    while offset <= last_record:
        page_params = {**params, "limit": config.PAGE_SIZE, "offset": offset}
        page = request_json(config.API_URL, page_params)
        if "features" not in page:
            raise ApiError("Response has no 'features' list, it is not GeoJSON")
        print(f"  page offset={offset}: {len(page['features'])} events")
        if not page["features"]:
            break
        pages.append(page)
        offset += config.PAGE_SIZE
    return pages


def flatten(feature):
    properties = feature.get("properties") or {}
    coordinates = (feature.get("geometry") or {}).get("coordinates") or []
    coordinates = list(coordinates) + [None] * (3 - len(coordinates))
    return {
        "id": feature.get("id"),
        "mag": properties.get("mag"),
        "magType": properties.get("magType"),
        "place": properties.get("place"),
        "time": properties.get("time"),
        "updated": properties.get("updated"),
        "latitude": coordinates[1],
        "longitude": coordinates[0],
        "depth": coordinates[2],
        "sig": properties.get("sig"),
        "nst": properties.get("nst"),
        "gap": properties.get("gap"),
        "dmin": properties.get("dmin"),
        "rms": properties.get("rms"),
        "status": properties.get("status"),
        "type": properties.get("type"),
        "alert": properties.get("alert"),
        "tsunami": properties.get("tsunami"),
        "felt": properties.get("felt"),
        "net": properties.get("net"),
    }


def save_raw(params, total, pages, records):
    config.ensure_dirs()
    original = {
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "endpoint": config.API_URL,
        "params": params,
        "available_in_api": total,
        "pages": pages,
    }
    with open(config.RAW_GEOJSON_PATH, "w", encoding="utf-8") as file:
        json.dump(original, file, ensure_ascii=False)
    with open(config.RAW_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=1)
    pd.DataFrame(records, columns=config.FIELDS).to_csv(config.RAW_CSV_PATH, index=False)


def fetch_earthquakes(start_time=None, end_time=None, min_magnitude=None):
    params = build_params(
        start_time or config.START_TIME,
        end_time or config.END_TIME,
        config.MIN_MAGNITUDE if min_magnitude is None else min_magnitude,
    )
    print(f"Request: {config.API_URL}")
    print(f"Params: {params}")
    total = get_total_count(params)
    print(f"Earthquakes available in API: {total}")
    if total == 0:
        raise ApiError("API has no earthquakes for these parameters")
    pages = fetch_pages(params, total)
    records = [flatten(feature) for page in pages for feature in page["features"]]
    if not records:
        raise ApiError("API returned an empty list of earthquakes")
    save_raw(params, total, pages, records)
    config.save_stats("api", {
        "collected": len(records),
        "available_in_api": total,
        "pages": len(pages),
        "start_time": params["starttime"],
        "end_time": params["endtime"],
        "min_magnitude": params["minmagnitude"],
    })
    if len(records) < config.MIN_RECORDS:
        print(f"WARNING: only {len(records)} records, at least {config.MIN_RECORDS} are needed. "
              f"Use a longer period or a lower --min-mag.")
    return records


def parse_args():
    parser = argparse.ArgumentParser(description="Collect earthquakes from the USGS Earthquake API")
    parser.add_argument("--start", default=config.START_TIME, help="start date, YYYY-MM-DD")
    parser.add_argument("--end", default=config.END_TIME, help="end date, YYYY-MM-DD")
    parser.add_argument("--min-mag", type=float, default=config.MIN_MAGNITUDE, help="minimum magnitude")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        records = fetch_earthquakes(args.start, args.end, args.min_mag)
    except ApiError as error:
        print(f"ERROR: {error}")
        sys.exit(1)
    frame = pd.DataFrame(records, columns=config.FIELDS)
    print(f"Collected records: {len(records)}")
    print(f"Saved: {config.RAW_GEOJSON_PATH.name}, {config.RAW_JSON_PATH.name}, {config.RAW_CSV_PATH.name}")
    print("Examples:")
    print(frame[["id", "mag", "magType", "place", "time", "depth"]].head(3).to_string(index=False))


if __name__ == "__main__":
    main()
