import json
import unittest
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from scripts.sync_groundwater import (
    check_api_access,
    find_device,
    find_dashboards,
    get_csv,
    inspect_device_telemetry,
    inspect_dashboard,
    parse_measurements,
    save_history,
    upload_batch,
)


class ParseMeasurementsTests(unittest.TestCase):
    def test_parses_waterportal_metadata_and_measurement_rows(self):
        csv_text = (
            'Messstellennummer;1\n'
            'Bezirk;Reinickendorf\n'
            ';\n'
            'Datum;"GW-Stand (m ü. NHN)"\n'
            '01.11.2025;33,41\n'
            '02.11.2025;33.52\n'
        )

        measurements = parse_measurements(
            csv_text,
            {"minimum_value": -100, "maximum_value": 1000},
        )

        self.assertEqual(len(measurements), 2)
        self.assertEqual(
            measurements[0]["ts"],
            int(datetime(2025, 11, 1, tzinfo=timezone.utc).timestamp() * 1000),
        )
        self.assertEqual(measurements[0]["value"], 33.41)
        self.assertEqual(measurements[1]["value"], 33.52)

    def test_skips_invalid_values_and_replaces_duplicate_timestamps(self):
        csv_text = (
            "Datum;Wert\n"
            "01.11.2025;33,41\n"
            "01.11.2025;33,42\n"
            "02.11.2025;not-a-value\n"
            "03.11.2025;2000\n"
        )

        measurements = parse_measurements(
            csv_text,
            {"minimum_value": -100, "maximum_value": 1000},
        )

        self.assertEqual(len(measurements), 1)
        self.assertEqual(measurements[0]["value"], 33.42)

    def test_supports_configured_columns_and_unbounded_finite_pollutant_values(self):
        csv_text = (
            "Datum;GW-Stand;Nitrat\n"
            "01.11.2025;33,41;1234,5678\n"
        )

        measurements = parse_measurements(
            csv_text,
            {"value_column": 2},
        )

        self.assertEqual(measurements[0]["value"], 1234.5678)

    @patch("scripts.sync_groundwater.urlopen")
    def test_fetch_uses_waterportal_documented_get_parameters(self, mock_urlopen):
        response = Mock()
        response.__enter__ = Mock(return_value=BytesIO(b"Datum;Wert\n"))
        response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = response
        series = {
            "station_id": 1,
            "topic": "gws",
            "series": "ew",
            "export_topic": "gw",
            "substance_id": 0,
            "substance_id_2": 0,
        }

        get_csv(series, "01.11.1953", "21.11.2026")

        request = mock_urlopen.call_args.args[0]
        query = parse_qs(urlparse(request.full_url).query)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(query["anzeige"], ["d"])
        self.assertEqual(query["station"], ["1"])
        self.assertEqual(query["thema"], ["gws"])
        self.assertEqual(query["sdatum"], ["01.11.1953"])
        self.assertEqual(query["senddatum"], ["21.11.2026"])

    @patch("scripts.sync_groundwater.urlopen")
    def test_upload_sends_historical_timestamps_and_configured_key(self, mock_urlopen):
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(status=200))
        response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = response
        series = {
            "telemetry_key": "groundwater_level",
            "station_id": 1,
            "station_name": "Reinickendorf",
            "unit": "m ü. NHN",
            "items": [{"ts": 1761955200000, "value": 33.41}],
        }

        upload_batch("https://thingsboard.example", "token", series)

        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload[0]["ts"], 1761955200000)
        self.assertEqual(payload[0]["values"]["groundwater_level"], 33.41)

    def test_saves_series_schema_for_html_backup(self):
        series = [{
            "id": "station-1-groundwater-level",
            "station_id": 1,
            "station_name": "Reinickendorf",
            "topic": "gws",
            "parameter_name": "Grundwasserstand",
            "unit": "m ü. NHN",
            "measurements": [{"ts": 1761955200000, "value": 33.41}],
        }]

        with unittest.mock.patch("scripts.sync_groundwater.save_json") as save_json_mock:
            save_history(Path("groundwater-data.json"), series)

        saved = save_json_mock.call_args.args[1]
        self.assertEqual(saved["series"], series)
        self.assertIn("updated_at", saved)

    @patch("scripts.sync_groundwater.urlopen")
    def test_check_api_access_sends_api_key_header(self, mock_urlopen):
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(status=200, read=Mock(return_value=b'{"authority":"TENANT_ADMIN"}')))
        response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = response

        check_api_access("https://api.example.com", "my-secret-api-key")

        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIn("X-authorization", request.headers)
        self.assertEqual(request.headers["X-authorization"], "ApiKey my-secret-api-key")

    @patch("scripts.sync_groundwater.urlopen")
    def test_check_api_access_does_not_expose_api_key_in_url(self, mock_urlopen):
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(status=200, read=Mock(return_value=b'{"authority":"TENANT_ADMIN"}')))
        response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = response

        check_api_access("https://api.example.com", "my-secret-api-key")

        request = mock_urlopen.call_args.args[0]
        self.assertNotIn("my-secret-api-key", request.full_url)

    @patch("scripts.sync_groundwater.urlopen")
    def test_checks_thingsboard_rest_api_without_printing_key(self, mock_urlopen):
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(status=200, read=Mock(return_value=b'{"authority":"TENANT_ADMIN"}')))
        response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = response

        check_api_access("https://eu.thingsboard.cloud", "secret-api-key")

        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://eu.thingsboard.cloud/api/auth/user")
        self.assertEqual(request.headers["X-authorization"], "ApiKey secret-api-key")

    @patch("scripts.sync_groundwater.urlopen")
    def test_finds_matching_device_read_only(self, mock_urlopen):
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(
            status=200,
            read=Mock(return_value=b'{"data":[{"name":"Messstelle 1 (Reinickendorf)","id":{"id":"device-123"}}]}'),
        ))
        response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = response

        matches = find_device(
            "https://eu.thingsboard.cloud",
            "secret-api-key",
            "Messstelle 1",
        )

        request = mock_urlopen.call_args.args[0]
        self.assertEqual(matches, [{"name": "Messstelle 1 (Reinickendorf)", "id": "device-123"}])
        self.assertIn("/api/tenant/devices?", request.full_url)
        self.assertIn("textSearch=Messstelle+1", request.full_url)
        self.assertEqual(request.headers["X-authorization"], "ApiKey secret-api-key")

    @patch("scripts.sync_groundwater.urlopen")
    def test_inspects_device_telemetry_read_only(self, mock_urlopen):
        keys_response = Mock(status=200, read=Mock(return_value=b'["groundwater_level","station_id"]'))
        latest_response = Mock(status=200, read=Mock(return_value=b'{"groundwater_level":[{"ts":1762646400000,"value":33.41}]}'))
        mock_urlopen.side_effect = [
            Mock(__enter__=Mock(return_value=keys_response), __exit__=Mock(return_value=False)),
            Mock(__enter__=Mock(return_value=latest_response), __exit__=Mock(return_value=False)),
        ]

        inspect_device_telemetry(
            "https://eu.thingsboard.cloud",
            "secret-api-key",
            {"name": "Messstelle 1 (Reinickendorf)", "id": "device-123"},
        )

        keys_request, latest_request = [call.args[0] for call in mock_urlopen.call_args_list]
        self.assertIn("/keys/timeseries", keys_request.full_url)
        self.assertIn("keys=groundwater_level", latest_request.full_url)
        self.assertEqual(keys_request.headers["X-authorization"], "ApiKey secret-api-key")

    @patch("scripts.sync_groundwater.urlopen")
    def test_finds_matching_dashboards_read_only(self, mock_urlopen):
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(
            status=200,
            read=Mock(return_value=b'{"data":[{"title":"Messstelle 1 - Reinickendorf","id":{"id":"dashboard-123"}}]}'),
        ))
        response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = response

        matches = find_dashboards(
            "https://eu.thingsboard.cloud",
            "secret-api-key",
            "Messstelle 1",
        )

        request = mock_urlopen.call_args.args[0]
        self.assertEqual(matches, [{"title": "Messstelle 1 - Reinickendorf", "id": "dashboard-123"}])
        self.assertIn("/api/tenant/dashboards?", request.full_url)
        self.assertIn("textSearch=Messstelle+1", request.full_url)
        self.assertEqual(request.headers["X-authorization"], "ApiKey secret-api-key")

    @patch("scripts.sync_groundwater.urlopen")
    def test_inspects_known_dashboard_read_only(self, mock_urlopen):
        payload = {
            "title": "Grundwasser_Berlin",
            "id": {"id": "9ba9c130-e284-11f1-a2b8-99b86090d117"},
            "configuration": {
                "widgets": {
                    "w1": {
                        "config": {
                            "datasources": [{
                                "type": "entity",
                                "dataKeys": [{"name": "groundwater_level"}],
                                "entityAliasId": "a1",
                            }]
                        }
                    }
                },
                "entityAliases": {
                    "a1": {
                        "alias": "Messstelle 1",
                        "filter": {
                            "entityFilters": [{
                                "entity": {"id": "c1a4ed80-e1ce-11f1-abc4-373280129aee"}
                            }]
                        },
                    }
                },
            },
        }
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(
            status=200,
            read=Mock(return_value=json.dumps(payload).encode("utf-8")),
        ))
        response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = response

        dashboard = inspect_dashboard(
            "https://eu.thingsboard.cloud",
            "secret-api-key",
            "9ba9c130-e284-11f1-a2b8-99b86090d117",
        )

        request = mock_urlopen.call_args.args[0]
        self.assertEqual(dashboard["title"], "Grundwasser_Berlin")
        self.assertIn("/api/dashboard/9ba9c130-e284-11f1-a2b8-99b86090d117", request.full_url)
        self.assertEqual(request.headers["X-authorization"], "ApiKey secret-api-key")


if __name__ == "__main__":
    unittest.main()
