import copy
import unittest

from algorithm_programmer.hand_collision import check_static_hand
from algorithm_programmer.hand_profile import CORNERS, sample_profile
from algorithm_programmer.models import POSITION_REFERENCE


def profile():
    result = sample_profile()
    result["parameters"].update({
        "body_u_length": 200, "body_v_length": 200,
        "finger_length": 20, "finger_thickness": 10, "finger_depth": 20,
        "u_end_distance": 30, "v_end_distance": 30, "clearance": 0,
    })
    return result


def box(order, x, y, top=100, width=100, length=100, height=100, rotation=0):
    return {
        "order": order, "box_id": "TEST-{}".format(order),
        "position": {"x": x, "y": y, "z": top},
        "dimensions": {"width": width, "length": length, "height": height},
        "rotation": rotation, "layer_index": 0,
    }


def fixture():
    return {
        "test_name": "static_hand_fixture", "coordinate_reference": POSITION_REFERENCE,
        "pallet": {"length": 1200, "width": 1000},
        "boxes": [box(1, 100, 0), box(2, 100, 100, length=160)],
    }


class StaticHandTests(unittest.TestCase):
    def setUp(self):
        self.data, self.profile = fixture(), profile()

    def check(self, order=2, corner=CORNERS[0]):
        return check_static_hand(self.data, self.profile, order, corner)

    def test_adjacent_earlier_box_collides_but_opposite_corner_is_clear(self):
        hit = self.check()
        self.assertTrue(hit["has_interference"])
        self.assertEqual(hit["checked_orders"], [1])
        self.assertEqual(hit["collisions"][0]["obstacle"]["order"], 1)
        self.assertEqual(hit["collisions"][0]["overlap"],
                         {"min": [160, 90, 80], "max": [180, 100, 100]})
        self.assertFalse(self.check(corner=CORNERS[2])["has_interference"])

    def test_later_boxes_are_not_obstacles_and_source_is_unchanged(self):
        self.data["boxes"][0]["order"] = 3
        before = copy.deepcopy(self.data)
        result = self.check()
        self.assertEqual(result["checked_orders"], [])
        self.assertFalse(result["has_interference"])
        self.assertFalse(result["trajectory_checked"])
        self.assertFalse(result["order_changed"])
        self.assertEqual(self.data, before)

    def test_support_below_hand_is_not_a_collision(self):
        self.data["boxes"][0] = box(1, 100, 100)
        self.data["boxes"][1]["position"]["z"] = 200
        self.assertFalse(self.check()["has_interference"])

    def test_target_tangency_is_allowed_even_with_clearance(self):
        self.data["boxes"] = [box(1, 100, 100)]
        self.profile["parameters"]["clearance"] = 2
        result = self.check(order=1)
        self.assertFalse(result["has_interference"])
        self.assertTrue(result["target_contacts"])

    def test_uncovered_box_zero_lid_dimensions_match_omitted_lid(self):
        expected = self.check()
        for entry in self.data["boxes"]:
            entry.update(lid_id="無蓋", lid_fit_type="なし", lid_thickness=0,
                         lid_dimensions={"width": 0, "length": 0})
        self.assertEqual(self.check(), expected)
        self.data.pop("coordinate_reference")
        for entry in self.data["boxes"]:
            entry["position"]["z"] -= entry["dimensions"]["height"]
        self.assertEqual(self.check(), expected)

    def test_real_lid_zero_dimensions_are_rejected(self):
        self.data["boxes"][0].update(
            lid_id="LID", lid_fit_type="外嵌め", lid_thickness=10,
            lid_dimensions={"width": 0, "length": 0})
        with self.assertRaises(ValueError):
            self.check()

    def test_target_lid_contact_is_not_reported_as_penetration(self):
        self.data["boxes"] = [box(1, 100, 100)]
        self.profile["parameters"]["body_bottom"] = -10
        target = self.data["boxes"][0]
        target.update(lid_fit_type="外嵌め", lid_thickness=10,
                      lid_dimensions={"width": 120, "length": 120})
        self.assertFalse(self.check(order=1)["has_interference"])
        target["lid_dimensions"] = {"width": 80, "length": 80}
        self.assertFalse(self.check(order=1)["has_interference"])

    def test_pallet_penetration_and_contact(self):
        self.data["boxes"] = [box(1, 100, 100, top=20, height=20)]
        self.assertFalse(self.check(order=1)["has_interference"])
        self.profile["parameters"]["clearance"] = 2
        result = self.check(order=1)
        self.assertTrue(result["has_interference"])
        self.assertTrue(all(h["obstacle"]["kind"] == "pallet" for h in result["collisions"]))
        self.assertTrue(all(h["clearance_only"] for h in result["collisions"]))
        self.profile["parameters"]["finger_depth"] = 21
        self.assertTrue(any(not h["clearance_only"] for h in self.check(order=1)["collisions"]))

    def test_exact_gap_and_clearance_threshold(self):
        self.data["boxes"][0]["position"]["y"] = -12  # Prior maxY=88, hand minY=90.
        self.profile["parameters"]["clearance"] = 2
        self.assertFalse(self.check()["has_interference"])
        self.profile["parameters"]["clearance"] = 2.01
        result = self.check()
        self.assertTrue(result["has_interference"])
        self.assertTrue(all(hit["clearance_only"] for hit in result["collisions"]))

    def test_lid_overhang_detected_without_false_full_height_solid(self):
        prior = self.data["boxes"][0]
        prior.update(lid_fit_type="外嵌め", lid_thickness=10,
                     lid_dimensions={"width": 120, "length": 140})
        prior["position"] = {"x": 90, "y": -40, "z": 100}
        # Body ends at Y=80; only the lid reaches the hand at Y=90..100.
        hits = self.check()["collisions"]
        self.assertTrue(hits)
        self.assertTrue(all(hit["obstacle"]["kind"] == "lid" for hit in hits))
        prior["position"]["z"] = 300
        prior["dimensions"]["height"] = 300
        self.assertFalse(self.check()["has_interference"])

    def test_current_and_legacy_lid_coordinates_match_all_corners(self):
        target = self.data["boxes"][1]
        target.update(rotation=90, lid_fit_type="外嵌め", lid_thickness=10,
                      lid_dimensions={"width": 120, "length": 180})
        modern = copy.deepcopy(self.data)
        legacy = copy.deepcopy(modern)
        del legacy["coordinate_reference"]
        for entry in legacy["boxes"]:
            pos, dims = entry["position"], entry["dimensions"]
            lid = entry.get("lid_dimensions", {})
            pos["x"] += (max(dims["width"], lid.get("width", 0)) - dims["width"]) / 2
            pos["y"] += (max(dims["length"], lid.get("length", 0)) - dims["length"]) / 2
            pos["z"] -= dims["height"]
        for corner in CORNERS:
            with self.subTest(corner=corner):
                self.assertEqual(check_static_hand(modern, self.profile, 2, corner),
                                 check_static_hand(legacy, self.profile, 2, corner))
        result = check_static_hand(modern, self.profile, 2, CORNERS[0])
        self.assertEqual(result["reference_position"], [220, 100, 100])
        self.assertEqual(result["hand_yaw_deg"], 90)

    def test_invalid_result_is_not_a_clear_result(self):
        for change in (
                lambda d: d.update(coordinate_reference="unknown"),
                lambda d: d["boxes"][0].update(order=2),
                lambda d: d["boxes"][0].update(rotation=45),
                lambda d: d["boxes"][0]["position"].update(x=float("nan")),
                lambda d: d["boxes"][0]["dimensions"].update(height=0)):
            data = copy.deepcopy(self.data)
            change(data)
            with self.assertRaises(ValueError):
                check_static_hand(data, self.profile, 2, CORNERS[0])
        with self.assertRaises(ValueError):
            self.check(order=999)


if __name__ == "__main__":
    unittest.main()
