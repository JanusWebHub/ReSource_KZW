import csv
import json
import math
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


WATERPORTAL_URL = "https://wasserportal.berlin.de/station.php"
BATCH_SIZE = 5
MAX_UPLOAD_ITEMS_PER_RUN = 500
REQUEST_TIMEOUT = 20
UPLOAD_RETRIES = 3


def parse_value(text, minimum=None, maximum=None):
    value = text.strip().replace(" ", "")
    if not value:
        raise ValueError("empty measurement")
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("measurement is not finite")
    if minimum is not None and number < minimum:
        raise ValueError("measurement below configured minimum")
    if maximum is not None and number > maximum:
        raise ValueError("measurement outside plausible range")
    return number


def parse_measurements(csv_text, series=None):
    series = series or {}
    value_column = series.get("value_column", 1)
    measurements = {}
    for row in csv.reader(csv_text.splitlines(), delimiter=";"):
        if len(row) <= value_column:
            continue
        date_text = row[0].strip().strip('"')
        value_text = row[value_column].strip().strip('"')
        measurement_date = None
        for date_format in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
            try:
                measurement_date = datetime.strptime(date_text, date_format)
                break
            except ValueError:
                continue
        if measurement_date is None:
            continue
        try:
            value = parse_value(
                value_text,
                series.get("minimum_value"),
                series.get("maximum_value"),
            )
        except ValueError:
            continue

        timestamp = int(measurement_date.replace(tzinfo=timezone.utc).timestamp() * 1000)
        measurements[timestamp] = value
    return [
        {"ts": timestamp, "value": value}
        for timestamp, value in sorted(measurements.items())
    ]


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read {path}: {error}") from None


def save_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary:
        json.dump(content, temporary, ensure_ascii=False, separators=(",", ":"))
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def get_csv(series, start_date, end_date):
    parameters = {
        "anzeige": "d",
        "station": series["station_id"],
        "thema": series["topic"],
        "sreihe": series["series"],
        "smode": "c",
        "exportthema": series["export_topic"],
        "nstoffid": series["substance_id"],
        "nstoffid2": series["substance_id_2"],
        "sdatum": start_date,
        "senddatum": end_date,
    }
    request = Request(
        f"{WATERPORTAL_URL}?{urlencode(parameters)}",
        headers={
            "Accept": "text/csv,text/plain,*/*",
            "User-Agent": "ReSource-KZW groundwater collector",
            "Referer": "https://wasserportal.berlin.de/",
        },
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return response.read().decode("utf-8-sig", errors="replace")
    except HTTPError as error:
        raise RuntimeError(f"Wasserportal returned HTTP {error.code}") from None
    except URLError as error:
        raise RuntimeError(
            f"Could not reach Wasserportal ({type(error.reason).__name__})"
        ) from None


def load_existing_series(data_path, series_id):
    data = load_json(data_path, {"series": []})
    for item in data.get("series", []):
        if item.get("id") == series_id:
            return item.get("measurements", [])
    return []


def load_state(state_path):
    state = load_json(state_path, {"series": {}})
    if "series" not in state:
        state["series"] = {}
    return state


def cursor_for(state, series_id):
    cursors = state["series"].get(series_id, {})
    legacy_timestamp = state.get("last_measurement_timestamp")
    return {
        "last_fetched_timestamp": cursors.get(
            "last_fetched_timestamp", legacy_timestamp
        ),
        "last_uploaded_timestamp": cursors.get(
            "last_uploaded_timestamp", legacy_timestamp
        ),
    }


def date_for_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp / 1000, timezone.utc).strftime("%d.%m.%Y")


def fetch_series(series, state, data_path, end_date):
    cursor = cursor_for(state, series["id"])
    last_fetched = cursor["last_fetched_timestamp"]
    start_date = (
        date_for_timestamp(last_fetched)
        if last_fetched is not None
        else series["start_date"]
    )
    fetched = parse_measurements(get_csv(series, start_date, end_date), series)
    history = {
        item["ts"]: item
        for item in load_existing_series(data_path, series["id"])
    }
    for item in fetched:
        if last_fetched is None or item["ts"] > last_fetched:
            history[item["ts"]] = item

    ordered_history = [history[timestamp] for timestamp in sorted(history)]
    if not ordered_history:
        raise RuntimeError(
            f"No valid measurements returned for series {series['id']}"
        )
    cursor["last_fetched_timestamp"] = max(
        item["ts"] for item in ordered_history
    )
    state["series"][series["id"]] = cursor
    return {
        **series,
        "measurements": ordered_history,
    }


def upload_batch(endpoint, token, batch):
    telemetry = [
        {
            "ts": item["ts"],
            "values": {
                batch["telemetry_key"]: item["value"],
                "station_id": batch["station_id"],
                "station": batch["station_name"],
                "unit": batch["unit"],
            },
        }
        for item in batch["items"]
    ]
    request = Request(
        f"{endpoint}/api/v1/{token}/telemetry",
        data=json.dumps(telemetry, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(1, UPLOAD_RETRIES + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError(f"ThingsBoard returned HTTP {response.status}")
            return
        except HTTPError as error:
            if attempt == UPLOAD_RETRIES:
                raise RuntimeError(f"ThingsBoard returned HTTP {error.code}") from None
        except URLError as error:
            if attempt == UPLOAD_RETRIES:
                raise RuntimeError(
                    f"Could not reach ThingsBoard ({type(error.reason).__name__})"
                ) from None
        time.sleep(2 * attempt)


def save_history(data_path, series_data):
    save_json(
        data_path,
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "series": series_data,
        },
    )


def main():
    if len(sys.argv) != 5 or sys.argv[1] not in {"fetch", "upload"}:
        raise RuntimeError(
            "Usage: sync_groundwater.py <fetch|upload> "
            "<state-path> <data-path> <series-config-path>"
        )
    mode, state_path, data_path, config_path = sys.argv[1:]
    state_path = Path(state_path)
    data_path = Path(data_path)
    series_config = load_json(Path(config_path), [])
    if not series_config:
        raise RuntimeError("No measurement series configured")
    state = load_state(state_path)
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")

    if mode == "fetch":
        existing_data = load_json(data_path, {"series": []})
        existing_by_id = {item["id"]: item for item in existing_data.get("series", [])}
        for series in series_config:
            existing_by_id[series["id"]] = fetch_series(
                series, state, data_path, today
            )
        save_history(data_path, list(existing_by_id.values()))
        save_json(state_path, state)
        print(
            "Waterportal data saved for HTML: "
            + ", ".join(item["id"] for item in series_config)
        )
        return

    endpoint = os.environ.get("THINGSBOARD_URL", "").rstrip("/")
    if not endpoint.startswith(("https://", "http://")):
        raise RuntimeError("THINGSBOARD_URL is missing or invalid")
    data = load_json(data_path, {"series": []})
    data_by_id = {item["id"]: item for item in data.get("series", [])}
    for series in series_config:
        token = os.environ.get(series["token_env"], "")
        if not token:
            print(
                f"ThingsBoard upload skipped for {series['id']}: "
                f"{series['token_env']} is not set.",
                file=sys.stderr,
            )
            continue
        series_data = data_by_id[series["id"]]
        cursor = cursor_for(state, series["id"])
        pending = [
            item
            for item in series_data["measurements"]
            if cursor["last_uploaded_timestamp"] is None
            or item["ts"] > cursor["last_uploaded_timestamp"]
        ]
        pending = pending[:MAX_UPLOAD_ITEMS_PER_RUN]
        for offset in range(0, len(pending), BATCH_SIZE):
            batch = pending[offset : offset + BATCH_SIZE]
            try:
                upload_batch(
                    endpoint,
                    token,
                    {
                        **series,
                        "items": batch,
                    },
                )
            except RuntimeError as batch_error:
                stopped = False
                for item in batch:
                    try:
                        upload_batch(
                            endpoint,
                            token,
                            {
                                **series,
                                "items": [item],
                            },
                        )
                    except RuntimeError as item_error:
                        print(
                            f"ThingsBoard upload paused for {series['id']} at "
                            f"{cursor['last_uploaded_timestamp']}: {item_error}. "
                            "HTML data is already saved; this batch will be retried.",
                            file=sys.stderr,
                        )
                        stopped = True
                        break
                    cursor["last_uploaded_timestamp"] = item["ts"]
                    state["series"][series["id"]] = cursor
                    save_json(state_path, state)
                if stopped:
                    break
                continue
            cursor["last_uploaded_timestamp"] = batch[-1]["ts"]
            state["series"][series["id"]] = cursor
            save_json(state_path, state)
        else:
            if pending:
                print(
                    f"ThingsBoard upload complete for {series['id']}: "
                    f"{len(pending)} measurement(s)."
                )
            else:
                print(f"No ThingsBoard backlog for {series['id']}.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(f"Groundwater sync failed: {error}", file=sys.stderr)
        sys.exit(1)
