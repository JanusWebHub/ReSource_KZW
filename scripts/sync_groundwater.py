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


def check_api_access(endpoint, api_key):
    if not api_key:
        raise RuntimeError("THINGSBOARD_API_KEY is missing")

    request = Request(
        f"{endpoint}/api/auth/user",
        headers={"X-Authorization": f"ApiKey {api_key}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"ThingsBoard REST API returned HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(
            f"ThingsBoard REST API authentication failed with HTTP {error.code}"
        ) from None
    except URLError as error:
        raise RuntimeError(
            f"Could not reach ThingsBoard REST API ({type(error.reason).__name__})"
        ) from None

    authority = payload.get("authority", "unknown")
    print(f"ThingsBoard REST API authentication successful (authority: {authority}).")


def find_device(endpoint, api_key, device_name):
    parameters = urlencode({"pageSize": 100, "page": 0, "textSearch": device_name})
    request = Request(
        f"{endpoint}/api/tenant/devices?{parameters}",
        headers={"X-Authorization": f"ApiKey {api_key}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"ThingsBoard device lookup returned HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(f"ThingsBoard device lookup failed with HTTP {error.code}") from None
    except URLError as error:
        raise RuntimeError(f"Could not reach ThingsBoard device API ({type(error.reason).__name__})") from None

    matches = []
    for item in payload.get("data", []):
        name = item.get("name", "")
        if device_name.lower() in name.lower() or "reinickendorf" in name.lower():
            entity_id = item.get("id", {}).get("id")
            matches.append({"name": name, "id": entity_id})

    print(
        f"ThingsBoard device lookup found {len(matches)} matching device(s): "
        + (", ".join(item["name"] for item in matches) if matches else "none")
    )
    return matches


def find_dashboards(endpoint, api_key, search_text=""):
    parameters = urlencode({"pageSize": 100, "page": 0, "textSearch": search_text})
    request = Request(
        f"{endpoint}/api/tenant/dashboards?{parameters}",
        headers={"X-Authorization": f"ApiKey {api_key}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"ThingsBoard dashboard lookup returned HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(f"ThingsBoard dashboard lookup failed with HTTP {error.code}") from None
    except URLError as error:
        raise RuntimeError(f"Could not reach ThingsBoard dashboard API ({type(error.reason).__name__})") from None

    matches = [
        {"title": item.get("title", ""), "id": item.get("id", {}).get("id")}
        for item in payload.get("data", [])
        if not search_text or search_text.lower() in item.get("title", "").lower()
    ]
    print(
        "ThingsBoard dashboard lookup found "
        f"{len(matches)} matching dashboard(s): "
        + (", ".join(item["title"] for item in matches) if matches else "none")
    )
    for item in matches:
        print(f"Dashboard: {item['title']} ({item['id']})")
    return matches


def inspect_device_telemetry(endpoint, api_key, device):
    device_id = device["id"]
    headers = {"X-Authorization": f"ApiKey {api_key}"}

    keys_request = Request(
        f"{endpoint}/api/plugins/telemetry/DEVICE/{device_id}/keys/timeseries",
        headers=headers,
        method="GET",
    )
    latest_request = Request(
        f"{endpoint}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries?keys=groundwater_level",
        headers=headers,
        method="GET",
    )
    try:
        with urlopen(keys_request, timeout=REQUEST_TIMEOUT) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"ThingsBoard telemetry-key lookup returned HTTP {response.status}")
            keys = json.loads(response.read().decode("utf-8"))
        with urlopen(latest_request, timeout=REQUEST_TIMEOUT) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"ThingsBoard latest-value lookup returned HTTP {response.status}")
            latest = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(f"ThingsBoard telemetry lookup failed with HTTP {error.code}") from None
    except URLError as error:
        raise RuntimeError(f"Could not reach ThingsBoard telemetry API ({type(error.reason).__name__})") from None

    values = latest.get("groundwater_level", [])
    print(f"Confirmed device: {device['name']} ({device_id})")
    print(f"ThingsBoard telemetry keys: {', '.join(keys) if keys else 'none'}")
    if values:
        print(f"Latest groundwater_level: {values[0]['value']} at timestamp {values[0]['ts']} ms")
    else:
        print("Latest groundwater_level: not present")


def inspect_dashboard(endpoint, api_key, dashboard_id):
    request = Request(
        f"{endpoint}/api/dashboard/{dashboard_id}",
        headers={"X-Authorization": f"ApiKey {api_key}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"ThingsBoard dashboard lookup returned HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(f"ThingsBoard dashboard lookup failed with HTTP {error.code}") from None
    except URLError as error:
        raise RuntimeError(f"Could not reach ThingsBoard dashboard API ({type(error.reason).__name__})") from None

    print(f"Confirmed dashboard: {payload.get('title', 'unknown')} ({dashboard_id})")

    configuration = payload.get("configuration", {})
    widgets = configuration.get("widgets", {})
    aliases = configuration.get("entityAliases", {})

    print(f"Dashboard widgets: {len(widgets) if isinstance(widgets, dict) else 0}")
    if aliases:
        alias_names = []
        for alias_id, alias in aliases.items():
            alias_names.append(alias.get("alias", alias_id))
            for filter_item in alias.get("filter", {}).get("entityFilters", []):
                entity = filter_item.get("entity")
                if isinstance(entity, dict) and entity.get("id"):
                    alias_names.append(str(entity.get("id")))
        print("Dashboard entity aliases: " + ", ".join(dict.fromkeys(alias_names)))
    else:
        print("Dashboard entity aliases: none")

    serialized = json.dumps(configuration, ensure_ascii=False)
    print("Dashboard contains groundwater_level: " + ("yes" if "groundwater_level" in serialized else "no"))
    print("Dashboard contains expected device ID: " + ("yes" if "c1a4ed80-e1ce-11f1-abc4-373280129aee" in serialized else "no"))
    return payload


def save_history(data_path, series_data):
    save_json(
        data_path,
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "series": series_data,
        },
    )


def main():
    if len(sys.argv) != 5 or sys.argv[1] not in {"fetch", "upload", "check-api"}:
        raise RuntimeError(
            "Usage: sync_groundwater.py <fetch|upload|check-api> "
            "<state-path> <data-path> <series-config-path>"
        )
    mode, state_path, data_path, config_path = sys.argv[1:]

    if mode == "check-api":
        endpoint = os.environ.get("THINGSBOARD_URL", "").rstrip("/")
        if not endpoint.startswith(("https://", "http://")):
            raise RuntimeError("THINGSBOARD_URL is missing or invalid")
        api_key = os.environ.get("THINGSBOARD_API_KEY", "")
        check_api_access(endpoint, api_key)
        reinickendorf_matches = find_device(endpoint, api_key, "Reinickendorf")
        exact_matches = [
            item for item in reinickendorf_matches
            if item["name"].lower() == "messstelle 1 (reinickendorf)"
        ]
        if len(exact_matches) == 1:
            inspect_device_telemetry(endpoint, api_key, exact_matches[0])
        elif not exact_matches:
            print("Could not confirm exact device Messstelle 1 (Reinickendorf).")
        else:
            print("Multiple exact devices named Messstelle 1 (Reinickendorf) found.")
        find_dashboards(endpoint, api_key, "Messstelle 1")
        find_dashboards(endpoint, api_key, "Reinickendorf")
        inspect_dashboard(endpoint, api_key, "9ba9c130-e284-11f1-a2b8-99b86090d117")
        return

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
