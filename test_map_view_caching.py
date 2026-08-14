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


if __name__ == "__main__":
    unittest.main()
