import copy
import unittest

from algorithm_programmer.hand_collision import check_static_hand, select_static_corners
from algorithm_programmer.hand_collision_test import box, fixture, profile
from algorithm_programmer.hand_profile import CORNERS


class StaticCornerSelectionTests(unittest.TestCase):
    def setUp(self):
        self.data, self.profile = fixture(), profile()

    def select(self):
        return select_static_corners(self.data, self.profile)

    def test_four_candidates_match_manual_checks_and_first_clear_is_selected(self):
        result = self.select()
        self.assertEqual(result["corner_priority"], list(CORNERS))
        self.assertEqual(result["summary"], {"total": 2, "selected": 2, "blocked": 0, "out_of_range": 0})
        self.assertTrue(result["all_corners_selected"])
        for entry in result["boxes"]:
            checks = []
            self.assertEqual([c["corner_id"] for c in entry["candidates"]], list(CORNERS))
            for candidate in entry["candidates"]:
                check = check_static_hand(self.data, self.profile, entry["order"], candidate["corner_id"])
                self.assertEqual(candidate["check"], check)
                checks.append(check)
            first_clear = next(check for check in checks if not check["has_interference"])
            self.assertEqual(entry["selected"], first_clear)
        self.assertNotEqual(result["boxes"][1]["selected"]["corner_id"], CORNERS[0])

    def test_all_interfering_is_not_selected(self):
        self.data["boxes"] = [box(1, 100, 100, top=10, height=10)]
        result = self.select()
        entry = result["boxes"][0]
        self.assertEqual(entry["status"], "blocked")
        self.assertIsNone(entry["selected"])
        self.assertTrue(all(c["status"] == "blocked" for c in entry["candidates"]))
        self.assertFalse(result["all_corners_selected"])
        self.assertEqual(result["summary"]["blocked"], 1)

    def test_out_of_range_is_explicit_and_does_not_abort_other_boxes(self):
        self.data["boxes"].append(box(3, 500, 500, width=20, length=20))
        result = self.select()
        self.assertEqual(result["summary"], {"total": 3, "selected": 2, "blocked": 0, "out_of_range": 1})
        entry = result["boxes"][2]
        self.assertIsNone(entry["selected"])
        self.assertEqual(entry["status"], "out_of_range")
        for candidate in entry["candidates"]:
            self.assertIsNone(candidate["check"])
            self.assertTrue(candidate["reason"])
        self.assertFalse(result["all_corners_selected"])

    def test_corner_specific_range_errors_do_not_hide_valid_corners(self):
        self.profile["parameters"]["body_u_length"] = 110
        result = self.select()
        entry = result["boxes"][1]
        self.assertEqual([c["status"] for c in entry["candidates"]],
                         ["blocked", "out_of_range", "clear", "out_of_range"])
        self.assertEqual(entry["selected"]["corner_id"], CORNERS[2])
        self.data["boxes"][1]["position"]["z"] = 10
        self.data["boxes"][1]["dimensions"]["height"] = 10
        entry = self.select()["boxes"][1]
        self.assertEqual(entry["status"], "blocked")
        self.assertIsNone(entry["selected"])

    def test_unresolved_prior_box_stays_an_obstacle(self):
        self.data["boxes"][0]["position"]["z"] = 10
        self.data["boxes"][0]["dimensions"]["height"] = 10
        self.data["boxes"][1]["position"]["z"] = 20
        self.data["boxes"][1]["dimensions"]["height"] = 20
        result = self.select()
        self.assertEqual(result["boxes"][0]["status"], "blocked")
        for candidate in result["boxes"][1]["candidates"]:
            self.assertEqual(candidate["check"]["checked_orders"], [1])

    def test_deterministic_sorted_read_only_and_profile_snapshot(self):
        self.data["boxes"].reverse()
        before = copy.deepcopy((self.data, self.profile))
        first = self.select()
        self.assertEqual(first, self.select())
        self.assertEqual((self.data, self.profile), before)
        self.assertEqual([b["order"] for b in first["boxes"]], [1, 2])
        self.assertFalse(first["trajectory_checked"])
        self.assertFalse(first["order_changed"])
        self.assertFalse(first["positions_changed"])
        self.profile["name"] = "Changed later"
        self.assertEqual(first["profile"], before[1])

    def test_invalid_input_is_not_misclassified_as_unsupported_geometry(self):
        self.data["boxes"][1]["rotation"] = 45
        with self.assertRaises(ValueError):
            self.select()
        self.data = fixture()
        self.profile["parameters"]["finger_depth"] = -1
        with self.assertRaises(ValueError):
            self.select()
        self.profile = profile()
        self.data["boxes"][1]["dimensions"].pop("width")
        with self.assertRaises(KeyError):
            self.select()


if __name__ == "__main__":
    unittest.main()
