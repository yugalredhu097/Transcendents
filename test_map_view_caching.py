"""
Unit Test for Map View Caching and Leaflet Controls in Phase 6
"""

import unittest
from unittest.mock import patch, MagicMock
from ui.map_view import (
    fetch_osrm_route_geometry,
    render_leaflet_map,
    build_legend_html,
    LeafletPaneManager,
    MapLegendControl,
    resolve_truck_destination_coordinates,
    find_affected_area_bypass_anchors,
    find_geographic_bypass_anchors,
    generate_local_bypass_candidates,
    validate_local_bypass_candidate,
    find_best_valid_local_bypass,
    haversine_km,
    validate_reroute_separation,
)


class TestMapViewPhase6(unittest.TestCase):

    @patch("urllib.request.urlopen")
    def test_osrm_route_geometry_fetch_and_fallback(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"code": "Ok", "routes": [{"geometry": {"coordinates": [[75.7873, 26.9124], [77.2090, 28.6139]]}}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        start = (26.9124, 75.7873)
        end = (28.6139, 77.2090)
        coords = fetch_osrm_route_geometry(start, end)
        self.assertIsInstance(coords, list)
        self.assertEqual(len(coords), 2)
        self.assertEqual(coords[0], [26.9124, 75.7873])
        self.assertEqual(coords[-1], [28.6139, 77.2090])

    def test_legend_html_pre_and_post_analysis(self):
        pre_html = build_legend_html(is_post_analysis=False)
        self.assertIn("MAP LEGEND", pre_html)
        self.assertIn("LIVE TRACK", pre_html)
        self.assertIn("Pending Analysis", pre_html)

        post_html = build_legend_html(is_post_analysis=True)
        self.assertIn("POST-ANALYSIS", post_html)
        self.assertIn("AI Recommended Reroute", post_html)
        self.assertIn("Blocked Route Segment", post_html)

    @patch("ui.map_view.st_folium")
    def test_render_leaflet_map_includes_panes_and_controls(self, mock_st_folium):
        fleet_data = [
            {
                "truck_id": "TRK-107",
                "shipment_id": "SHP-1007",
                "lat": 26.9124,
                "lng": 75.7873,
                "destination": "Delhi Hub",
                "cargo_type": "Perishable",
                "speed_kmh": 45,
                "delay_minutes": 40,
                "status": "abnormal_stop",
            }
        ]
        disruptions_data = {
            "TRK-107": {
                "disruption_type": "flood",
                "severity": "HIGH",
                "description": "Heavy monsoon flooding",
                "location": {"lat": 27.5, "lng": 76.5},
            }
        }
        facilities_data = [
            {
                "facility_id": "FAC-01",
                "name": "Delhi Cold Storage",
                "latitude": 28.6139,
                "longitude": 77.2090,
                "type": "cold_storage",
                "supports_perishable_cargo": True,
            }
        ]

        render_leaflet_map(
            fleet_data=fleet_data,
            disruptions_data=disruptions_data,
            facilities_data=facilities_data,
            selected_truck_id="TRK-107",
            pipeline_result=None,
        )

        self.assertTrue(mock_st_folium.called)
        call_args = mock_st_folium.call_args
        folium_map = call_args[0][0]
        html_repr = folium_map._repr_html_()

        # Check Leaflet Pane creation
        self.assertIn("disruption_pane", html_repr)
        self.assertIn("route_pane", html_repr)
        self.assertIn("hazard_marker_pane", html_repr)
        self.assertIn("truck_pane", html_repr)

        # Check Legend Control
        self.assertIn("lic-map-legend-control", html_repr)

        # Check returned_objects=[] parameter
        self.assertEqual(call_args[1].get("returned_objects"), [])

    def test_destination_resolution_uses_destination_location(self):
        truck = {
            "truck_id": "TRK-107",
            "destination": "Random City",
            "destination_location": {"lat": 28.7041, "lng": 77.1025, "name": "Delhi Terminal"},
        }
        facilities_data = [
            {"facility_id": "FAC-99", "name": "Unrelated Hub", "latitude": 19.0760, "longitude": 72.8777}
        ]
        coords = resolve_truck_destination_coordinates(truck, facilities_data)
        self.assertEqual(coords, (28.7041, 77.1025))

    def test_destination_resolution_does_not_override_with_unrelated_facility(self):
        truck = {"truck_id": "TRK-112", "destination": "Jaipur Logistics Hub"}
        facilities_data = [
            {"facility_id": "FAC-01", "name": "Cold Hub Jaipur", "latitude": 26.9124, "longitude": 75.7873}
        ]
        coords = resolve_truck_destination_coordinates(truck, facilities_data)
        self.assertEqual(coords, (26.9124, 75.7873))

        # Unknown destination should return None, NOT force first facility
        truck_unknown = {"truck_id": "TRK-999", "destination": "Unknown City Target"}
        coords_unknown = resolve_truck_destination_coordinates(truck_unknown, facilities_data)
        self.assertIsNone(coords_unknown)

    def test_clearance_anchors_outside_15km(self):
        dis_coords = (27.5000, 76.5000)
        # Create route passing through dis_coords
        route = [[27.0 + i * 0.05, 76.0 + i * 0.05] for i in range(21)]
        s_idx, e_idx = find_affected_area_bypass_anchors(route, dis_coords, min_clearance_km=15.0)

        start_pt = (route[s_idx][0], route[s_idx][1])
        end_pt = (route[e_idx][0], route[e_idx][1])

        self.assertGreaterEqual(haversine_km(start_pt, dis_coords), 14.9)
        self.assertGreaterEqual(haversine_km(end_pt, dis_coords), 14.9)

    def test_validate_reroute_separation_rejects_inside_affected_radius(self):
        dis_coords = (27.5000, 76.5000)
        corridor = [[27.5, 76.5], [27.6, 76.6]]
        # Candidate inside 14km radius (27.51, 76.51 is ~1.4 km from 27.5, 76.5)
        bad_cand = [[27.51, 76.51], [28.0, 77.0]]

        isValid = validate_reroute_separation(bad_cand, corridor, dis_coords)
        self.assertFalse(isValid)

    @patch("ui.map_view.st_folium")
    def test_render_post_analysis_trk107_and_trk112(self, mock_st_folium):
        fleet_data = [
            {
                "truck_id": "TRK-107",
                "shipment_id": "SHP-1007",
                "lat": 26.9124,
                "lng": 75.7873,
                "destination": "Delhi Hub",
                "destination_location": {"lat": 28.6139, "lng": 77.2090, "name": "Delhi Hub Terminal"},
                "cargo_type": "Pharmaceuticals",
                "speed_kmh": 45,
                "delay_minutes": 40,
                "status": "abnormal_stop",
                "origin": {"lat": 26.9124, "lng": 75.7873, "name": "Jaipur Depot"},
            }
        ]
        disruptions_data = {
            "TRK-107": {
                "disruption_type": "flood",
                "severity": "HIGH",
                "description": "Monsoon flooding",
                "location": {"lat": 27.5, "lng": 76.5},
            }
        }
        facilities_data = [
            {
                "facility_id": "FAC-01",
                "name": "Delhi Logistics Hub",
                "latitude": 28.6139,
                "longitude": 77.2090,
            }
        ]
        pipeline_result = {
            "dispatch_output": {"escalate": True},
            "plan_data": {"action": "reroute", "new_route": "Bypass NH48"},
        }

        render_leaflet_map(
            fleet_data=fleet_data,
            disruptions_data=disruptions_data,
            facilities_data=facilities_data,
            selected_truck_id="TRK-107",
            pipeline_result=pipeline_result,
        )

        self.assertTrue(mock_st_folium.called)
        folium_map = mock_st_folium.call_args[0][0]
        html_repr = folium_map._repr_html_()

        # Flag-checkered destination marker icon check
        self.assertIn("flag-checkered", html_repr)
        # Check purple destination color
        self.assertIn("purple", html_repr)
        # Check route polyline colors present
        self.assertIn("#00BFFF", html_repr)  # Original route blue
        self.assertIn("#FF0055", html_repr)  # Blocked segment red
        self.assertIn("#00FF66", html_repr)  # AI Reroute green

    def test_geographic_anchor_distance_calculation(self):
        dis_coords = (27.5000, 76.5000)
        route = [[27.0 + i * 0.005, 76.0 + i * 0.005] for i in range(200)]
        s_idx, e_idx = find_geographic_bypass_anchors(route, dis_coords, target_dist_km=4.0)

        start_pt = (route[s_idx][0], route[s_idx][1])
        end_pt = (route[e_idx][0], route[e_idx][1])

        self.assertGreaterEqual(haversine_km(start_pt, dis_coords), 3.8)
        self.assertGreaterEqual(haversine_km(end_pt, dis_coords), 3.8)

    def test_validate_local_bypass_candidate_rejects_coincident_route(self):
        dis_coords = (27.5000, 76.5000)
        corridor = [[27.4 + i * 0.01, 76.4 + i * 0.01] for i in range(20)]
        coincident_cand = [[pt[0] + 0.001, pt[1] + 0.001] for pt in corridor]

        isValid = validate_local_bypass_candidate(coincident_cand, corridor, dis_coords)
        self.assertFalse(isValid)

    def test_validate_local_bypass_candidate_rejects_disruption_center_crossing(self):
        dis_coords = (27.5000, 76.5000)
        corridor = [[27.0, 76.0], [28.0, 77.0]]
        crossing_cand = [[27.0, 76.0], [27.5001, 76.5001], [28.0, 77.0]]

        isValid = validate_local_bypass_candidate(crossing_cand, corridor, dis_coords)
        self.assertFalse(isValid)

    def test_validate_local_bypass_candidate_accepts_valid_detour(self):
        dis_coords = (27.5000, 76.5000)
        corridor = [[27.4 + i * 0.01, 76.4 + i * 0.01] for i in range(20)]
        valid_detour = [[pt[0] + 0.02, pt[1] - 0.02] for pt in corridor]

        isValid = validate_local_bypass_candidate(valid_detour, corridor, dis_coords)
        self.assertTrue(isValid)

    @patch("ui.map_view.fetch_osrm_route_geometry")
    def test_find_best_valid_local_bypass_returns_none_if_all_fail(self, mock_osrm):
        # Mock OSRM returning points on original corridor (snapping back to blocked road)
        mock_osrm.side_effect = lambda s, e: [[27.40, 76.40], [27.50, 76.50], [27.60, 76.60]]
        bypass_start = [27.40, 76.40]
        bypass_end = [27.60, 76.60]
        dis_coords = (27.50, 76.50)
        corridor = [[27.40, 76.40], [27.50, 76.50], [27.60, 76.60]]

        result = find_best_valid_local_bypass(bypass_start, bypass_end, dis_coords, corridor)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()


