"""
Focused Unit Tests for Map Routing and Facility Visualization Fixes:
1. Reroute starts at current truck, not dispatch origin.
2. Reroute cannot anchor upstream of current truck.
3. Reroute ends at destination.
4. TRK-102 coordinate ordering is correct.
5. find_relevant_facility reads recommended_action.
6. transfer_to_storage uses the planner-selected facility.
7. No unrelated facility is selected as a fallback.
8. transfer_to_storage does not render the reroute overlay.
9. wait does not render a fabricated reroute.
10. no_feasible_action does not render a recommended route.
"""

import unittest
from unittest.mock import patch, MagicMock

from ui.map_view import (
    find_relevant_facility,
    find_geographic_bypass_anchors,
    find_affected_area_bypass_anchors,
    render_leaflet_map,
    haversine_km,
)


class TestMapRoutingAndFacilities(unittest.TestCase):

    def setUp(self):
        self.facilities_data = [
            {
                "facility_id": "FAC-JAI-01",
                "name": "Jaipur Agri Cold Storage & Logistics Hub",
                "type": "cold_storage",
                "latitude": 26.850,
                "longitude": 75.780,
                "location_name": "Jaipur Industrial Zone, RJ",
                "supports_perishable_cargo": True,
            },
            {
                "facility_id": "FAC-KLY-01",
                "name": "Kalyan Regional Logistics Depot",
                "type": "warehouse",
                "latitude": 19.240,
                "longitude": 73.130,
                "location_name": "Bhiwandi-Kalyan Logistics Park, MH",
                "supports_perishable_cargo": False,
            },
            {
                "facility_id": "FAC-THN-01",
                "name": "Thane Bio-Pharma Cold Storage Park",
                "type": "cold_storage",
                "latitude": 19.210,
                "longitude": 73.080,
                "location_name": "Thane Trans-Thane Creek Zone, MH",
                "supports_perishable_cargo": True,
            },
        ]

    # Test 1: Reroute starts at current truck, not dispatch origin
    # Test 2: Reroute cannot anchor upstream of current truck
    # Test 3: Reroute ends at destination
    # Test 4: TRK-102 coordinate ordering is correct
    @patch("ui.map_view.st_folium")
    @patch("ui.map_view.fetch_osrm_route_geometry")
    def test_trk102_reroute_starts_at_truck_and_ends_at_destination(self, mock_osrm, mock_st_folium):
        # TRK-102 coordinates:
        # Truck / Disruption: (19.218, 73.102)
        # Origin: Mumbai (19.076, 72.8777)
        # Destination: Nashik (19.9975, 73.7898)
        truck_pos = [19.218, 73.102]
        origin_pos = [19.076, 72.8777]
        dest_pos = [19.9975, 73.7898]

        # Mock OSRM route legs
        def mock_fetch(start, end, timeout=2.0):
            # Format: (lat, lng)
            return [[start[0], start[1]], [end[0], end[1]]]

        mock_osrm.side_effect = mock_fetch

        fleet_data = [
            {
                "truck_id": "TRK-102",
                "shipment_id": "SHP-102",
                "lat": truck_pos[0],
                "lng": truck_pos[1],
                "origin": {"lat": origin_pos[0], "lng": origin_pos[1], "name": "Mumbai Port"},
                "destination": "Nashik Freight Hub",
                "destination_location": {"lat": dest_pos[0], "lng": dest_pos[1], "name": "Nashik Freight Hub"},
                "cargo_type": "perishable_produce",
            }
        ]

        disruptions_data = {
            "TRK-102": {
                "disruption_type": "flood",
                "severity": "HIGH",
                "location": {"lat": truck_pos[0], "lng": truck_pos[1]},
            }
        }

        pipeline_result = {
            "dispatch_output": {"escalate": True},
            "plan_data": {
                "recommended_action": "reroute",
                "reasoning": "Rerouting via alternate highway around Kalyan flood",
            },
        }

        render_leaflet_map(
            fleet_data=fleet_data,
            disruptions_data=disruptions_data,
            facilities_data=self.facilities_data,
            selected_truck_id="TRK-102",
            pipeline_result=pipeline_result,
        )

        self.assertTrue(mock_st_folium.called)
        folium_map = mock_st_folium.call_args[0][0]

        # Extract green polyline added for AI reroute
        polylines = []
        for child in folium_map._children.values():
            if hasattr(child, "_children"):
                for subchild in child._children.values():
                    if "AI RECOMMENDED REROUTE" in str(getattr(subchild, "text", "")):
                        polylines.append(child)

        self.assertGreater(len(polylines), 0, "AI Recommended Reroute polyline should be rendered")
        reroute_coords = polylines[0].locations

        first_coord = reroute_coords[0]
        last_coord = reroute_coords[-1]

        # Test 1 & 4: First coordinate must be current truck position (19.218, 73.102)
        dist_first_to_truck = haversine_km((first_coord[0], first_coord[1]), (truck_pos[0], truck_pos[1]))
        self.assertAlmostEqual(dist_first_to_truck, 0.0, delta=0.01)

        # Test 2: First coordinate is NOT dispatch origin (Mumbai 19.076)
        dist_first_to_origin = haversine_km((first_coord[0], first_coord[1]), (origin_pos[0], origin_pos[1]))
        self.assertGreater(dist_first_to_origin, 10.0)

        # Test 3 & 4: Last coordinate must be destination (Nashik 19.9975, 73.7898)
        dist_last_to_dest = haversine_km((last_coord[0], last_coord[1]), (dest_pos[0], dest_pos[1]))
        self.assertAlmostEqual(dist_last_to_dest, 0.0, delta=0.01)

    # Test 2 detail: Upstream anchor lower bound enforcement
    def test_anchor_cannot_go_upstream_of_truck(self):
        route = [
            [19.076, 72.8777],  # 0: Origin (Mumbai)
            [19.150, 72.9500],  # 1: Midpoint
            [19.218, 73.1020],  # 2: Truck & Incident (Kalyan)
            [19.500, 73.4000],  # 3: Post-incident 1
            [19.9975, 73.7898], # 4: Destination (Nashik)
        ]
        dis_coords = (19.218, 73.1020)
        truck_idx = 2

        s_idx, e_idx = find_geographic_bypass_anchors(route, dis_coords, target_dist_km=5.0, min_start_idx=truck_idx)
        self.assertGreaterEqual(s_idx, truck_idx, "Start anchor index must be >= truck_idx")

        s_idx_aff, e_idx_aff = find_affected_area_bypass_anchors(route, dis_coords, min_clearance_km=15.0, min_start_idx=truck_idx)
        self.assertGreaterEqual(s_idx_aff, truck_idx, "Start anchor index for affected area must be >= truck_idx")

    # Test 5: find_relevant_facility reads recommended_action
    def test_find_relevant_facility_reads_recommended_action(self):
        truck = {"truck_id": "TRK-105", "lat": 19.218, "lng": 73.102, "cargo_type": "electronics"}
        # Legacy pipeline result using "action" should NOT trigger facility match
        legacy_res = {"plan_data": {"action": "transfer_to_storage"}}
        fac_legacy = find_relevant_facility(truck, self.facilities_data, legacy_res)
        self.assertIsNone(fac_legacy, "find_relevant_facility must not read action field")

        # Correct pipeline result using Contract 4 "recommended_action"
        correct_res = {"plan_data": {"recommended_action": "transfer_to_storage"}}
        fac_correct = find_relevant_facility(truck, self.facilities_data, correct_res)
        self.assertIsNotNone(fac_correct)

    # Test 6 & 7: transfer_to_storage uses planner-selected facility and no unrelated fallback
    def test_transfer_to_storage_selects_authoritative_facility_for_trk105(self):
        truck = {
            "truck_id": "TRK-105",
            "lat": 19.218,
            "lng": 73.102,
            "cargo_type": "electronics",
            "is_temp_sensitive": False,
        }

        # Case A: Plan explicitly specifies selected_facility ID FAC-KLY-01
        plan_explicit = {
            "plan_data": {
                "recommended_action": "transfer_to_storage",
                "selected_facility": "FAC-KLY-01",
            }
        }
        fac_explicit = find_relevant_facility(truck, self.facilities_data, plan_explicit)
        self.assertEqual(fac_explicit["facility_id"], "FAC-KLY-01")

        # Case B: Plan specifies reasoning mentioning FAC-KLY-01 / Kalyan Depot
        plan_reasoning = {
            "plan_data": {
                "recommended_action": "transfer_to_storage",
                "reasoning": "Diverting electronics to FAC-KLY-01 Kalyan Regional Logistics Depot",
            }
        }
        fac_reasoning = find_relevant_facility(truck, self.facilities_data, plan_reasoning)
        self.assertEqual(fac_reasoning["facility_id"], "FAC-KLY-01")

        # Case C: Plan without explicit facility field matches closest non-perishable warehouse to Thane (FAC-KLY-01)
        plan_implicit = {
            "plan_data": {
                "recommended_action": "transfer_to_storage",
                "reasoning": "Diverting cargo to local logistics warehouse",
            }
        }
        fac_implicit = find_relevant_facility(truck, self.facilities_data, plan_implicit)
        self.assertEqual(fac_implicit["facility_id"], "FAC-KLY-01")
        self.assertNotEqual(fac_implicit["facility_id"], "FAC-JAI-01", "Must not select Jaipur facility for Thane truck")

    # Test 8: transfer_to_storage does not render reroute overlay, renders storage journey legs
    @patch("ui.map_view.st_folium")
    @patch("ui.map_view.fetch_osrm_route_geometry")
    def test_transfer_to_storage_renders_storage_journey_not_reroute(self, mock_osrm, mock_st_folium):
        mock_osrm.side_effect = lambda s, e, timeout=2.0: [[s[0], s[1]], [e[0], e[1]]]

        fleet_data = [
            {
                "truck_id": "TRK-105",
                "lat": 19.218,
                "lng": 73.102,
                "cargo_type": "electronics",
                "origin": {"lat": 19.076, "lng": 72.877, "name": "Mumbai Port"},
                "destination": "Delhi Hub",
                "destination_location": {"lat": 28.6139, "lng": 77.2090, "name": "Delhi Hub"},
            }
        ]

        pipeline_result = {
            "dispatch_output": {"escalate": True},
            "plan_data": {
                "recommended_action": "transfer_to_storage",
                "selected_facility": "FAC-KLY-01",
                "reasoning": "Diverting electronics to FAC-KLY-01",
            },
        }

        render_leaflet_map(
            fleet_data=fleet_data,
            disruptions_data={},
            facilities_data=self.facilities_data,
            selected_truck_id="TRK-105",
            pipeline_result=pipeline_result,
        )

        folium_map = mock_st_folium.call_args[0][0]
        html_repr = folium_map._repr_html_()

        # Should render facility marker FAC-KLY-01
        self.assertIn("FAC-KLY-01", html_repr)
        self.assertIn("Kalyan Regional Logistics Depot", html_repr)

        # Tooltips should include storage diversion legs
        self.assertIn("STORAGE DIVERSION LEG 1", html_repr)

        # Must NOT render green reroute overlay line
        self.assertNotIn("🟢 AI RECOMMENDED REROUTE", html_repr)

    # Test 9: wait does not render a fabricated reroute
    @patch("ui.map_view.st_folium")
    def test_wait_action_does_not_render_reroute(self, mock_st_folium):
        fleet_data = [
            {
                "truck_id": "TRK-104",
                "lat": 27.60,
                "lng": 76.00,
                "origin": {"lat": 28.61, "lng": 77.20, "name": "Delhi"},
                "destination_location": {"lat": 26.91, "lng": 75.78, "name": "Jaipur"},
            }
        ]
        disruptions = {
            "TRK-104": {
                "disruption_type": "protest",
                "severity": "MEDIUM",
                "location": {"lat": 27.60, "lng": 76.00},
            }
        }
        pipeline_result = {
            "dispatch_output": {"escalate": True},
            "plan_data": {
                "recommended_action": "wait",
                "reasoning": "Disruption is temporary (~1.5h). Waiting at site.",
            },
        }

        render_leaflet_map(
            fleet_data=fleet_data,
            disruptions_data=disruptions,
            facilities_data=self.facilities_data,
            selected_truck_id="TRK-104",
            pipeline_result=pipeline_result,
        )

        folium_map = mock_st_folium.call_args[0][0]
        html_repr = folium_map._repr_html_()
        self.assertNotIn("🟢 AI RECOMMENDED REROUTE", html_repr)
        self.assertNotIn("STORAGE DIVERSION LEG", html_repr)

    # Test 10: no_feasible_action does not render a recommended route
    @patch("ui.map_view.st_folium")
    def test_no_feasible_action_does_not_render_recommended_route(self, mock_st_folium):
        fleet_data = [
            {
                "truck_id": "TRK-107",
                "lat": 26.91,
                "lng": 75.78,
                "origin": {"lat": 27.60, "lng": 75.13, "name": "Sikar"},
                "destination_location": {"lat": 19.07, "lng": 72.87, "name": "Mumbai"},
            }
        ]
        disruptions = {
            "TRK-107": {
                "disruption_type": "flood",
                "severity": "CRITICAL",
                "location": {"lat": 26.91, "lng": 75.78},
            }
        }
        pipeline_result = {
            "dispatch_output": {"escalate": True},
            "plan_data": {
                "recommended_action": "no_feasible_action",
                "reasoning": "Baseline travel time exceeds delivery deadline and remaining shelf life.",
            },
        }

        render_leaflet_map(
            fleet_data=fleet_data,
            disruptions_data=disruptions,
            facilities_data=self.facilities_data,
            selected_truck_id="TRK-107",
            pipeline_result=pipeline_result,
        )

        folium_map = mock_st_folium.call_args[0][0]
        html_repr = folium_map._repr_html_()
        self.assertNotIn("🟢 AI RECOMMENDED REROUTE", html_repr)
        self.assertNotIn("STORAGE DIVERSION LEG", html_repr)


if __name__ == "__main__":
    unittest.main()
