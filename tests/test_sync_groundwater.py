import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.sync_groundwater import load_history, parse_measurements, persist_sync


class ParseMeasurementsTests(unittest.TestCase):
    def test_parses_german_decimal_values_and_uses_measurement_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "measurements.csv"
            csv_path.write_text(
                "Datum;Wert\n01.11.2025;33,41\n02.11.2025;33.52\n",
                encoding="utf-8",
            )

            measurements = parse_measurements(csv_path)

        self.assertEqual(len(measurements), 2)
        self.assertEqual(
            measurements[0]["ts"],
            int(datetime(2025, 11, 1, tzinfo=timezone.utc).timestamp() * 1000),
        )
        self.assertEqual(measurements[0]["values"]["groundwater_level"], 33.41)
        self.assertEqual(measurements[1]["values"]["groundwater_level"], 33.52)
        self.assertEqual(measurements[0]["values"]["station_id"], 1)

    def test_skips_invalid_values_and_replaces_duplicate_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "measurements.csv"
            csv_path.write_text(
                "Datum;Wert\n"
                "01.11.2025;33,41\n"
                "01.11.2025;33,42\n"
                "02.11.2025;not-a-value\n"
                "03.11.2025;2000\n",
                encoding="utf-8",
            )

            measurements = parse_measurements(csv_path)

        self.assertEqual(len(measurements), 1)
        self.assertEqual(measurements[0]["values"]["groundwater_level"], 33.42)

    def test_persists_full_history_for_html_and_sync_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "groundwater-data.json"
            state_path = Path(directory) / "groundwater-sync-state.json"
            timestamp = 1761955200000
            history = [{"ts": timestamp, "groundwater_level": 33.41}]

            persist_sync(data_path, state_path, history, timestamp)

            data = json.loads(data_path.read_text(encoding="utf-8"))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(data["measurements"], history)
            self.assertEqual(data["station_id"], 1)
            self.assertIn("updated_at", data)
            self.assertEqual(
                load_history(data_path, timestamp - 1),
                history,
            )
            self.assertEqual(state["last_measurement_timestamp"], timestamp)


if __name__ == "__main__":
    unittest.main()
