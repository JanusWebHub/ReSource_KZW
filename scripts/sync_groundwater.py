import csv
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BATCH_SIZE = 100


def parse_value(text):
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
    if not -100 <= number <= 1000:
        raise ValueError("measurement outside plausible range")
    return number


def parse_measurements(csv_path):
    measurements = {}
    with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as source:
        for row in csv.reader(source, delimiter=";"):
            if len(row) < 2:
                continue
            date_text = row[0].strip().strip('"')
            value_text = row[1].strip().strip('"')
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
                value = parse_value(value_text)
            except ValueError:
                continue

            timestamp = int(measurement_date.replace(tzinfo=timezone.utc).timestamp() * 1000)
            measurements[timestamp] = {
                "groundwater_level": value,
                "station_id": 1,
                "station": "Reinickendorf",
                "unit": "m u. NHN",
            }
    return [
        {"ts": timestamp, "values": values}
        for timestamp, values in sorted(measurements.items())
    ]


def send_batch(endpoint, token, measurements):
    payload = json.dumps(measurements, separators=(",", ":")).encode("utf-8")
    request = Request(
        f"{endpoint}/api/v1/{token}/telemetry",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"ThingsBoard returned HTTP {response.status}")
    except HTTPError as error:
        details = error.read(1000).decode("utf-8", errors="replace").strip()
        details = details.replace(token, "[redacted]")
        raise RuntimeError(
            f"ThingsBoard returned HTTP {error.code}: {details or 'no response details'}"
        ) from None
    except URLError as error:
        raise RuntimeError(
            f"Could not reach ThingsBoard ({type(error.reason).__name__})"
        ) from None


def load_history(data_path, last_timestamp):
    if not data_path.exists():
        if last_timestamp is not None:
            raise RuntimeError(
                "Groundwater history file is missing although sync state exists"
            )
        return []

    try:
        history_data = json.loads(data_path.read_text(encoding="utf-8"))
        history = history_data["measurements"]
        if not isinstance(history, list):
            raise ValueError("measurements must be a list")
        for item in history:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("ts"), int)
                or not isinstance(item.get("groundwater_level"), (int, float))
            ):
                raise ValueError("invalid measurement entry")
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as error:
        raise RuntimeError(f"Could not read groundwater history: {error}") from None
    return history


def save_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary:
        json.dump(content, temporary, ensure_ascii=False, separators=(",", ":"))
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def persist_sync(data_path, state_path, history, timestamp):
    data = {
        "station_id": 1,
        "station": "Reinickendorf",
        "unit": "m ü. NHN",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "measurements": history,
    }
    save_json(data_path, data)
    save_json(state_path, {"last_measurement_timestamp": timestamp})


def main():
    if len(sys.argv) != 4:
        raise RuntimeError(
            "Usage: sync_groundwater.py <csv-path> <state-path> <data-path>"
        )

    csv_path = Path(sys.argv[1])
    state_path = Path(sys.argv[2])
    data_path = Path(sys.argv[3])
    endpoint = os.environ.get("THINGSBOARD_URL", "").rstrip("/")
    token = os.environ.get("THINGSBOARD_TOKEN", "")
    if not endpoint.startswith(("https://", "http://")) or not token:
        raise RuntimeError("THINGSBOARD_URL or THINGSBOARD_TOKEN is missing")

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read sync state: {error}") from None
    last_timestamp = state.get("last_measurement_timestamp")
    if last_timestamp is not None and (
        not isinstance(last_timestamp, int) or last_timestamp < 0
    ):
        raise RuntimeError("Invalid last_measurement_timestamp in sync state")

    history = load_history(data_path, last_timestamp)
    history_by_timestamp = {item["ts"]: item for item in history}
    new_measurements = [
        item
        for item in parse_measurements(csv_path)
        if item["ts"] not in history_by_timestamp
        and (last_timestamp is None or item["ts"] > last_timestamp)
    ]
    for measurement in new_measurements:
        history_by_timestamp[measurement["ts"]] = {
            "ts": measurement["ts"],
            "groundwater_level": measurement["values"]["groundwater_level"],
        }
    updated_history = [
        history_by_timestamp[timestamp]
        for timestamp in sorted(history_by_timestamp)
    ]

    if new_measurements:
        send_batch(endpoint, token, new_measurements[0])
        for offset in range(1, len(new_measurements), BATCH_SIZE):
            batch = new_measurements[offset : offset + BATCH_SIZE]
            try:
                send_batch(endpoint, token, batch)
            except RuntimeError as error:
                print(
                    f"Batch upload failed ({error}); retrying its measurements "
                    "individually.",
                    file=sys.stderr,
                )
                for measurement in batch:
                    send_batch(endpoint, token, measurement)

        newest_timestamp = new_measurements[-1]["ts"]
        persist_sync(data_path, state_path, updated_history, newest_timestamp)
        newest_date = datetime.fromtimestamp(
            newest_timestamp / 1000, timezone.utc
        ).strftime("%Y-%m-%d")
        print(
            f"Sent {len(new_measurements)} new measurement(s); "
            f"history now contains {len(updated_history)} measurement(s), "
            f"sync cursor is now {newest_date}."
        )
    elif not data_path.exists():
        raise RuntimeError("No measurements found; cannot create history data file")
    else:
        history_timestamp = updated_history[-1]["ts"] if updated_history else None
        if history_timestamp is not None and (
            last_timestamp is None or history_timestamp > last_timestamp
        ):
            save_json(
                state_path,
                {"last_measurement_timestamp": history_timestamp},
            )
        print(f"No new measurements found; history contains {len(updated_history)}.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(f"Groundwater sync failed: {error}", file=sys.stderr)
        sys.exit(1)
