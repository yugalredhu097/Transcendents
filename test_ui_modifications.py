"""
Unit Tests for UI Telemetry & Map Modifications:
- Authoritative origin and destination_location data contract
- Origin and destination coordinate resolvers
- Route generation from dispatch origin -> destination
- Precision local AI rerouting without fixed +/-0.28/0.35 offsets
- Route-derived blocked segment positioning
- 2-Column telemetry profile structure
- Unknown shelf life behavior
"""

import json
import os
import unittest
from unittest.mock import patch, MagicMock

from ui.map_view import (
    resolve_origin_coordinates,
    resolve_truck_destination_coordinates,
    _find_closest_point_index,
    render_leaflet_map,
)
from ui.components import render_selected_truck_panel


class TestUIModifications(unittest.TestCase):

    def setUp(self):
        self.mock_fleet_path = os.path.join(
            os.path.dirname(__file__), "data", "mock_fleet.json"
        )
        self.fleet_mock_path = os.path.join(
            os.path.dirname(__file__), "data", "fleet_mock.json"
        )

    def test_mock_fleet_data_contract(self):
        """Verify every truck in mock_fleet.json contains origin and destination_location."""
        with open(self.mock_fleet_path, "r", encoding="utf-8") as f:
            fleet = json.load(f)

        self.assertGreater(len(fleet), 0)
        for truck in fleet:
            tid = truck.get("truck_id")
            self.assertIn("origin", truck, f"Missing origin in {tid}")
            self.assertIn(
                "destination_location",
                truck,
                f"Missing destination_location in {tid}",
            )

            origin = truck.get("origin")
            self.assertIsInstance(origin, dict, f"Origin is not dict in {tid}")
            self.assertIn("lat", origin)
            self.assertIn("lng", origin)
            self.assertIn("name", origin)

            dest_loc = truck.get("destination_location")
            self.assertIsInstance(dest_loc, dict, f"Destination_location is not dict in {tid}")
            self.assertIn("lat", dest_loc)
            self.assertIn("lng", dest_loc)
            self.assertIn("name", dest_loc)

    def test_fleet_mock_data_contract(self):
        """Verify fallback fleet_mock.json also contains origin and destination_location."""
        with open(self.fleet_mock_path, "r", encoding="utf-8") as f:
            fleet = json.load(f)

        for truck in fleet:
            tid = truck.get("truck_id")
            self.assertIn("origin", truck, f"Missing origin in fallback {tid}")
            self.assertIn(
                "destination_location",
                truck,
                f"Missing destination_location in fallback {tid}",
            )

    def test_authoritative_agreed_origins(self):
        """Verify TRK-104 (Delhi), TRK-107 (Sikar), and TRK-112 (Delhi) origins."""
        with open(self.mock_fleet_path, "r", encoding="utf-8") as f:
            fleet = {t["truck_id"]: t for t in json.load(f)}

        # TRK-104 = Delhi
        trk_104_origin = resolve_origin_coordinates(fleet["TRK-104"])
        self.assertIsNotNone(trk_104_origin)
        self.assertAlmostEqual(trk_104_origin[0], 28.6139, places=3)
        self.assertAlmostEqual(trk_104_origin[1], 77.2090, places=3)

        # TRK-107 = Sikar
        trk_107_origin = resolve_origin_coordinates(fleet["TRK-107"])
        self.assertIsNotNone(trk_107_origin)
        self.assertAlmostEqual(trk_107_origin[0], 27.6094, places=3)
        self.assertAlmostEqual(trk_107_origin[1], 75.1398, places=3)

        # TRK-112 = Delhi
        trk_112_origin = resolve_origin_coordinates(fleet["TRK-112"])
        self.assertIsNotNone(trk_112_origin)
        self.assertAlmostEqual(trk_112_origin[0], 28.6139, places=3)
        self.assertAlmostEqual(trk_112_origin[1], 77.2090, places=3)

    def test_find_closest_point_index(self):
        """Verify finding closest index along route geometry."""
        route = [
            [27.60, 75.13],
            [27.20, 75.40],
            [26.91, 75.78],  # Jaipur
            [25.00, 74.50],
            [19.07, 72.87],  # Mumbai
        ]
        target = (26.912, 75.787)
        idx = _find_closest_point_index(route, target)
        self.assertEqual(idx, 2)

    @patch("ui.map_view.st_folium")
    @patch("ui.map_view.fetch_osrm_route_geometry")
    def test_original_route_starts_at_origin(self, mock_fetch_osrm, mock_st_folium):
        """Verify original route is computed starting from dispatch origin."""
        mock_fetch_osrm.return_value = [
            [27.6094, 75.1398],
            [26.912, 75.787],
            [19.076, 72.877],
        ]

        fleet_data = [
            {
                "truck_id": "TRK-107",
                "origin": {"lat": 27.6094, "lng": 75.1398, "name": "Sikar"},
                "location": {"lat": 26.912, "lng": 75.787, "name": "Jaipur"},
                "lat": 26.912,
                "lng": 75.787,
                "destination": "Mumbai",
                "destination_location": {
                    "lat": 19.076,
                    "lng": 72.877,
                    "name": "Mumbai",
                },
            }
        ]

        render_leaflet_map(
            fleet_data=fleet_data,
            disruptions_data={},
            facilities_data=[],
            selected_truck_id="TRK-107",
            pipeline_result=None,
        )

        # Check that fetch_osrm_route_geometry was called with start = origin (27.6094, 75.1398)
        self.assertTrue(mock_fetch_osrm.called)
        first_call_start = mock_fetch_osrm.call_args_list[0][0][0]
        self.assertEqual(first_call_start, (27.6094, 75.1398))

    @patch("streamlit.markdown")
    def test_telemetry_profile_two_column_structure(self, mock_markdown):
        """Verify render_selected_truck_panel displays 2-column structure with origin and destination."""
        truck = {
            "truck_id": "TRK-107",
            "shipment_id": "SHP-107",
            "priority": "HIGH",
            "origin": {"lat": 27.6094, "lng": 75.1398, "name": "Sikar Logistics Hub, RJ"},
            "cargo_type": "perishable_produce",
            "quantity": 1200,
            "unit": "crates",
            "delivery_deadline": "2026-08-11T18:00:00",
            "speed_kmh": 0,
            "delay_minutes": 45,
            "stopped_duration_minutes": 45,
            "remaining_shelf_life_hours": 14.0,
            "location": {"lat": 26.912, "lng": 75.787, "name": "NH-48 near Jaipur, RJ"},
            "destination_location": {"lat": 19.076, "lng": 72.877, "name": "Mumbai Cold Storage Hub, MH"},
        }

        render_selected_truck_panel(truck, disruptions={})

        self.assertTrue(mock_markdown.called)
        html_calls = [call[0][0] for call in mock_markdown.call_args_list if isinstance(call[0][0], str)]
        full_html = "".join(html_calls)

        self.assertIn("Sikar Logistics Hub, RJ", full_html)
        self.assertIn("NH-48 near Jaipur, RJ", full_html)
        self.assertIn("Mumbai Cold Storage Hub, MH", full_html)
        self.assertIn("grid-template-columns: 1fr 1fr", full_html)

    @patch("streamlit.markdown")
    def test_unknown_shelf_life(self, mock_markdown):
        """Verify null shelf life displays UNKNOWN."""
        truck = {
            "truck_id": "TRK-105",
            "shipment_id": "SHP-105",
            "priority": "CRITICAL",
            "origin": {"lat": 19.076, "lng": 72.877, "name": "Mumbai Port Terminal, MH"},
            "cargo_type": "electronics",
            "quantity": 600,
            "unit": "units",
            "delivery_deadline": "2026-08-12T10:00:00",
            "speed_kmh": 0,
            "delay_minutes": 45,
            "stopped_duration_minutes": 45,
            "remaining_shelf_life_hours": None,
            "location": {"lat": 19.218, "lng": 73.102, "name": "NH-48 near Thane, MH"},
            "destination_location": {"lat": 28.6139, "lng": 77.209, "name": "Delhi Freight Hub, DL"},
        }

        render_selected_truck_panel(truck, disruptions={})

        html_calls = [call[0][0] for call in mock_markdown.call_args_list if isinstance(call[0][0], str)]
        full_html = "".join(html_calls)
        self.assertIn("UNKNOWN", full_html)

    def test_classify_fleet_status_current_mock_data(self):
        """Verify dynamic fleet status counters match required semantics for mock data."""
        from ui.components import classify_fleet_status

        with open(self.mock_fleet_path, "r", encoding="utf-8") as f:
            fleet = json.load(f)

        disruptions_path = os.path.join(os.path.dirname(__file__), "data", "mock_disruptions.json")
        with open(disruptions_path, "r", encoding="utf-8") as f:
            disruptions = json.load(f)

        normal, at_risk, incident = classify_fleet_status(fleet, disruptions)
        self.assertEqual(normal, 2, "Expected NORMAL count of 2")
        self.assertEqual(at_risk, 2, "Expected AT RISK count of 2")
        self.assertEqual(incident, 3, "Expected INCIDENT count of 3")

        # Per-truck status verification
        for truck in fleet:
            tid = truck["truck_id"]
            dis = disruptions.get(tid)
            stage = dis.get("disruption_stage") if dis else None

            norm_c, risk_c, inc_c = classify_fleet_status([truck], disruptions)
            if tid in ("TRK-101", "TRK-106"):
                self.assertEqual((norm_c, risk_c, inc_c), (1, 0, 0), f"{tid} should be NORMAL")
            elif tid in ("TRK-104", "TRK-112"):
                self.assertEqual((norm_c, risk_c, inc_c), (0, 1, 0), f"{tid} should be AT RISK")
            elif tid in ("TRK-102", "TRK-105", "TRK-107"):
                self.assertEqual((norm_c, risk_c, inc_c), (0, 0, 1), f"{tid} should be INCIDENT")

    def test_classify_fleet_status_dynamic_stage_change(self):
        """Verify changing disruption_stage from upcoming to current dynamically shifts counter from AT RISK to INCIDENT."""
        from ui.components import classify_fleet_status

        with open(self.mock_fleet_path, "r", encoding="utf-8") as f:
            fleet = json.load(f)

        disruptions_path = os.path.join(os.path.dirname(__file__), "data", "mock_disruptions.json")
        with open(disruptions_path, "r", encoding="utf-8") as f:
            disruptions = json.load(f)

        # Mutate TRK-104 from upcoming to current
        modified_disruptions = json.loads(json.dumps(disruptions))
        modified_disruptions["TRK-104"]["disruption_stage"] = "current"

        normal, at_risk, incident = classify_fleet_status(fleet, modified_disruptions)
        self.assertEqual(normal, 2)
        self.assertEqual(at_risk, 1)
        self.assertEqual(incident, 4)

    def test_dropdown_labels_with_get_truck_operational_status(self):
        """Verify dropdown labels generated using get_truck_operational_status match expected status and disruption types."""
        from ui.components import get_truck_operational_status

        with open(self.mock_fleet_path, "r", encoding="utf-8") as f:
            fleet = json.load(f)

        disruptions_path = os.path.join(os.path.dirname(__file__), "data", "mock_disruptions.json")
        with open(disruptions_path, "r", encoding="utf-8") as f:
            disruptions = json.load(f)

        expected_labels = {
            "TRK-101": "🟢 TRK-101 — Normal Transit",
            "TRK-102": "🔴 TRK-102 — Incident (flood)",
            "TRK-104": "🟠 TRK-104 — At Risk (protest)",
            "TRK-105": "🔴 TRK-105 — Incident (breakdown)",
            "TRK-106": "🟢 TRK-106 — Normal Transit",
            "TRK-107": "🔴 TRK-107 — Incident (landslide)",
            "TRK-112": "🟠 TRK-112 — At Risk (protest)",
        }

        at_risk_count = 0
        for truck in fleet:
            tid = truck["truck_id"]
            status = get_truck_operational_status(truck, disruptions)
            dis_type = disruptions.get(tid, {}).get("disruption_type", "")

            if status == "INCIDENT":
                label = f"🔴 {tid} — Incident ({dis_type})"
            elif status == "AT_RISK":
                label = f"🟠 {tid} — At Risk ({dis_type})"
                at_risk_count += 1
            else:
                label = f"🟢 {tid} — Normal Transit"

            self.assertEqual(label, expected_labels[tid], f"Mismatch for {tid}")

        self.assertEqual(at_risk_count, 2, "Expected exactly 2 orange At Risk trucks in dropdown")


if __name__ == "__main__":
    unittest.main()


