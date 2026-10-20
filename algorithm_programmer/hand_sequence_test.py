import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from algorithm_programmer.hand_collision import check_static_hand, _prepare_result
from algorithm_programmer.hand_collision_test import box, fixture, profile
from algorithm_programmer.hand_sequence import generate_hand_sequence
from algorithm_programmer.hand_profile import CORNERS
from algorithm_programmer.palletizer import Palletizer
from algorithm_programmer.hand_sequence import HandSequenceError


class HandSequenceTests(unittest.TestCase):
    def setUp(self):
        self.data, self.profile = fixture(), profile()

    def generate(self):
        return generate_hand_sequence(self.data, self.profile)

    def test_x_then_y_descending_priority_and_inverse_loading(self):
        self.data["boxes"] = [
            box(1, 100, 100), box(2, 100, 500),
            box(3, 500, 100), box(4, 500, 500),
        ]
        result = self.generate()
        self.assertEqual(result["status"], "complete")
        self.assertEqual([e["original_order"] for e in result["depalletizing"]], [4, 3, 2, 1])
        self.assertEqual([e["original_order"] for e in result["palletizing"]], [1, 2, 3, 4])
        self.assertTrue(result["reverse_verified"])

    def test_supported_upper_removed_before_lower_even_when_lower_has_priority(self):
        self.data["boxes"] = [
            box(1, 100, 100, length=160), box(2, 100, 100, top=190, length=160),
        ]
        self.data["boxes"][0].update(fitting_depth=10, supported_by=[])
        self.data["boxes"][1].update(fitting_depth=10, supported_by=[1], layer_index=1)
        result = self.generate()
        self.assertEqual([e["original_order"] for e in result["depalletizing"]], [2, 1])
        self.assertEqual(result["palletizing"][1]["supported_by"], [1])
        self.assertEqual(result["palletizing"][1]["original_supported_by"], [1])
        self.assertEqual(result["depalletizing"][0]["selected"]["checked_orders"], [1])

    def test_grasp_corner_not_box_minimum_sets_x_and_y_priority(self):
        for positions, expected in (
                ([(100, 100, 600, 100), (500, 500, 100, 100)], 1),
                ([(100, 100, 100, 600)], 1)):
            with self.subTest(positions=positions):
                self.data["boxes"] = [
                    box(index, x, y, width=width, length=length)
                    for index, (x, y, width, length) in enumerate(positions, 1)
                ]
                self.profile["parameters"].update(body_u_length=800, body_v_length=800)
                result = self.generate()
                first = result["depalletizing"][0]
                self.assertEqual(first["original_order"], expected)
                self.assertEqual(first["selected"]["corner_id"], "X_MAX_Y_MAX")

    def test_every_step_selects_highest_clear_grasp_and_preserves_reverse_pose(self):
        self.data["boxes"] = [box(7, 100, 100), box(2, 200, 100, rotation=90),
                              box(4, 100, 200)]
        self.data["boxes"][2].update(lid_dimensions={"width": 120, "length": 140},
                                     lid_thickness=10, lid_fit_type="外嵌め")
        result = self.generate()
        self.assertEqual(result["status"], "complete")
        remaining = {source["order"] for source in self.data["boxes"]}
        loading = {entry["original_order"]: entry for entry in result["palletizing"]}
        for entry in result["depalletizing"]:
            candidates = []
            for source in self.data["boxes"]:
                if source["order"] not in remaining:
                    continue
                # Public checker sees the exact residual set by assigning the target last.
                residual = copy.deepcopy(self.data)
                residual["boxes"] = [item for item in residual["boxes"] if item["order"] in remaining]
                target_order = max(remaining) + 1
                for item in residual["boxes"]:
                    if item["order"] == source["order"]:
                        item["order"] = target_order
                for index, corner in enumerate(CORNERS):
                    check = check_static_hand(residual, self.profile, target_order, corner)
                    if not check["has_interference"]:
                        x, y, _ = check["reference_position"]
                        candidates.append(((-x, -y, source["order"], index), source["order"], corner))
            _, order, corner = min(candidates)
            self.assertEqual((entry["original_order"], entry["selected"]["corner_id"]), (order, corner))
            inverse = loading[order]["selected"]
            for field in ("corner_id", "reference_position", "hand_yaw_deg"):
                self.assertEqual(inverse[field], entry["selected"][field])
            remaining.remove(order)

    def test_equal_grasp_xy_uses_original_order_then_corner_priority(self):
        self.data["boxes"] = [box(7, 100, 100), box(2, 500, 500)]

        def tied_check(boxes, pallet_x, pallet_y, profile, target, corner, obstacle_orders):
            return {"reference_position": [900, 900, 100], "corner_id": corner,
                    "has_interference": False, "checked_orders": sorted(obstacle_orders)}

        with patch("algorithm_programmer.hand_sequence._check_pose", side_effect=tied_check):
            result = self.generate()
        self.assertEqual([entry["original_order"] for entry in result["depalletizing"]], [2, 7])
        self.assertTrue(all(entry["selected"]["corner_id"] == CORNERS[0]
                            for entry in result["depalletizing"]))

    def test_support_can_be_derived_when_metadata_missing(self):
        self.data["boxes"] = [box(1, 100, 100), box(2, 100, 100, top=200)]
        self.data["boxes"][1]["layer_index"] = 1
        self.assertEqual(self.generate()["palletizing"][1]["supported_by"], [1])

    def test_multiple_direct_supports_are_retained_and_renumbered(self):
        self.data["boxes"] = [
            box(1, 100, 100), box(2, 200, 100),
            box(3, 100, 100, top=200, width=200),
        ]
        self.data["boxes"][2]["supported_by"] = [1, 2]
        self.data["boxes"][2]["layer_index"] = 1
        result = self.generate()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["depalletizing"][0]["original_order"], 3)
        self.assertEqual(result["palletizing"][-1]["supported_by"], [1, 2])

    def test_original_identity_is_not_used_as_obstacle_time(self):
        self.data["boxes"] = [box(7, 100, 100), box(2, 500, 500)]
        result = self.generate()
        self.assertEqual(result["depalletizing"][0]["original_order"], 2)
        self.assertEqual(result["depalletizing"][0]["selected"]["checked_orders"], [7])
        self.assertEqual(result["palletizing"][1]["original_order"], 2)
        self.assertEqual(result["palletizing"][1]["selected"]["checked_orders"], [7])

    def test_reverse_removal_resolves_box_blocked_in_original_loading_order(self):
        positions = [(x, y) for x in (100, 200, 300) for y in (100, 200, 300)
                     if (x, y) != (200, 200)] + [(200, 200)]
        self.data["boxes"] = [box(index, x, y) for index, (x, y) in enumerate(positions, 1)]
        from algorithm_programmer.hand_profile import CORNERS

        self.assertTrue(all(check_static_hand(self.data, self.profile, 9, corner)["has_interference"]
                            for corner in CORNERS))
        result = self.generate()
        self.assertEqual(result["status"], "complete")
        self.assertTrue(result["reverse_verified"])
        self.assertNotEqual(result["palletizing"][-1]["original_order"], 9)

    def test_legacy_coordinates_and_current_coordinates_generate_same_plan(self):
        modern = self.generate()
        del self.data["coordinate_reference"]
        for source in self.data["boxes"]:
            source["position"]["z"] -= source["dimensions"]["height"]
        self.assertEqual(self.generate(), modern)

    def test_generated_plan_passes_public_loading_checker_after_renumbering(self):
        self.data["boxes"].reverse()
        result = self.generate()
        by_original = {source["order"]: source for source in self.data["boxes"]}
        rebuilt = copy.deepcopy(self.data)
        rebuilt["boxes"] = []
        for entry in result["palletizing"]:
            source = copy.deepcopy(by_original[entry["original_order"]])
            source["order"] = entry["step"]
            source["supported_by"] = entry["supported_by"]
            rebuilt["boxes"].append(source)
        for entry in result["palletizing"]:
            check = check_static_hand(rebuilt, self.profile, entry["step"], entry["selected"]["corner_id"])
            self.assertFalse(check["has_interference"])
            self.assertEqual(check["reference_position"], entry["selected"]["reference_position"])
            self.assertEqual(check["hand_yaw_deg"], entry["selected"]["hand_yaw_deg"])

    def test_range_failure_returns_partial_removal_but_no_loading_plan(self):
        self.data["boxes"] = [box(1, 500, 500), box(2, 100, 100, width=20, length=20)]
        result = self.generate()
        self.assertEqual(result["status"], "stalled")
        self.assertEqual(result["summary"], {"total": 2, "removed": 1, "remaining": 1})
        self.assertEqual(result["palletizing"], [])
        self.assertFalse(result["reverse_verified"])
        self.assertEqual(result["remaining"][0]["status"], "out_of_range")
        self.assertEqual(len(result["remaining"][0]["candidates"]), 4)

    def test_blocked_high_x_candidate_does_not_prevent_other_removals(self):
        self.data["boxes"] = [
            box(1, 100, 100), box(2, 500, 500, top=10, height=10),
        ]
        result = self.generate()
        self.assertEqual([entry["original_order"] for entry in result["depalletizing"]], [1])
        self.assertEqual(result["remaining"][0]["original_order"], 2)
        self.assertEqual(result["remaining"][0]["status"], "blocked")
        self.assertEqual(result["palletizing"], [])

    def test_blocked_leaf_keeps_supporting_lower_box_in_remaining_reasons(self):
        self.data["boxes"] = [box(1, 100, 100), box(2, 100, 100, top=200)]
        self.data["boxes"][1]["supported_by"] = [1]
        self.data["boxes"][1]["layer_index"] = 1
        self.profile["parameters"]["finger_depth"] = 250
        result = self.generate()
        self.assertEqual(result["status"], "stalled")
        self.assertEqual(result["remaining"][0]["status"], "layer_waiting")
        self.assertEqual(result["remaining"][1]["status"], "blocked")
        self.assertEqual(result["palletizing"], [])

    def test_layer_boundary_precedes_xy_priority_and_preserves_all_obstacles(self):
        self.data["boxes"] = [
            box(1, 100, 100), box(2, 500, 500),
            box(3, 100, 100, top=200), box(4, 500, 500, top=200),
        ]
        for source in self.data["boxes"][2:]:
            source["layer_index"] = 1
        result = self.generate()
        self.assertEqual([entry["original_order"] for entry in result["depalletizing"]], [4, 3, 2, 1])
        self.assertEqual([entry["layer_index"] for entry in result["palletizing"]], [0, 0, 1, 1])
        self.assertEqual(result["depalletizing"][1]["selected"]["checked_orders"], [1, 2])
        self.assertTrue(result["reverse_verified"])

    def test_stalled_upper_layer_does_not_remove_independent_lower_box(self):
        self.data["boxes"] = [
            box(1, 100, 100), box(2, 500, 500),
            box(3, 100, 100, top=200, width=20, length=20),
        ]
        self.data["boxes"][2]["layer_index"] = 1
        result = self.generate()
        self.assertEqual(result["depalletizing"], [])
        self.assertEqual(result["palletizing"], [])
        reasons = {entry["original_order"]: entry["status"] for entry in result["remaining"]}
        self.assertEqual(reasons, {1: "layer_waiting", 2: "layer_waiting", 3: "out_of_range"})

    def test_missing_invalid_or_support_inconsistent_layers_are_errors(self):
        for layer in (None, True, -1, 1.5, "0"):
            self.data = fixture()
            self.data["boxes"][0]["layer_index"] = layer
            with self.assertRaisesRegex(ValueError, "layer_index"):
                self.generate()
        del self.data["boxes"][0]["layer_index"]
        with self.assertRaisesRegex(ValueError, "layer_index"):
            self.generate()
        self.data["boxes"] = [box(1, 100, 100), box(2, 100, 100, top=200)]
        with self.assertRaisesRegex(ValueError, "layer_index"):
            self.generate()

    def test_invalid_support_metadata_or_floating_boxes_are_explicit_errors(self):
        for reported in ([1], [999], [True], [2, 2]):
            self.data = fixture()
            self.data["boxes"][1]["supported_by"] = reported
            with self.assertRaises(ValueError):
                self.generate()
        self.data = fixture()
        self.data["boxes"][1]["position"]["z"] = 500
        with self.assertRaises(ValueError):
            self.generate()

    def test_deterministic_read_only_and_profile_snapshot(self):
        before = copy.deepcopy((self.data, self.profile))
        first = self.generate()
        self.assertEqual(first, self.generate())
        self.assertEqual((self.data, self.profile), before)
        self.assertFalse(first["positions_changed"])
        self.assertFalse(first["source_modified"])
        self.assertFalse(first["trajectory_checked"])
        self.profile["name"] = "later"
        self.assertEqual(first["profile"], before[1])


class IntegratedHandOrderTests(unittest.TestCase):
    def test_engine_assigns_official_order_supports_and_serialized_grasps(self):
        data = fixture()
        data["boxes"] = [box(1, 100, 100), box(2, 500, 500),
                          box(3, 100, 100, top=200)]
        data["boxes"][2]["layer_index"] = 1
        boxes, _, _ = _prepare_result(data)
        for placed, source in zip(boxes, data["boxes"]):
            placed.layer_index = source["layer_index"]
        hand = profile()
        expected = generate_hand_sequence(data, hand)
        engine = Palletizer({}, hand_profile=hand)
        before = [(b.x, b.y, b.z, b.rotation, b.layer_index) for b in boxes]
        actual = engine.assign_loading_orders(boxes)
        self.assertEqual([b.order for b in actual], [1, 2, 3])
        self.assertEqual([(b.x, b.y, b.z, b.rotation, b.layer_index) for b in boxes], before)
        by_original = {index: b for index, b in enumerate(boxes, 1)}
        for entry, b in zip(expected["palletizing"], actual):
            self.assertIs(b, by_original[entry["original_order"]])
            self.assertEqual(b.supported_by, entry["supported_by"])
            self.assertEqual(b.to_dict()["hand_grasp"]["corner_id"], entry["selected"]["corner_id"])
            self.assertEqual(b.to_dict()["hand_grasp"]["envelope"], entry["selected"]["envelope"])
            self.assertFalse(check_static_hand({
                **data, "boxes": [item.to_dict() for item in actual],
            }, hand, b.order, b.hand_grasp["corner_id"])["has_interference"])

    def test_engine_failure_has_reasons_and_does_not_mutate_input_orders(self):
        data = fixture()
        data["boxes"] = [box(7, 100, 100, width=20, length=20)]
        boxes, _, _ = _prepare_result(data)
        before = copy.deepcopy(boxes)
        with self.assertRaises(HandSequenceError) as error:
            Palletizer({}, hand_profile=profile()).assign_loading_orders(boxes)
        self.assertEqual(error.exception.result["status"], "stalled")
        self.assertIn("設定範囲外", str(error.exception))
        self.assertEqual(boxes, before)

    def test_cli_outputs_only_verified_order_and_preserves_output_on_failure(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            settings = Path(directory) / "hand.json"
            hand = profile()
            hand["parameters"].update(body_u_length=1000, body_v_length=1000)
            settings.write_text(json.dumps({"schema_version": 1, "profiles": [hand]}), encoding="utf-8")
            command = [sys.executable, str(root / "algorithm_programmer" / "cli.py"),
                       str(root / "test_programmer" / "test_cases" / "boundary_height_limit_with_lids.json"),
                       "--hand-profiles", str(settings), "-o", str(output)]
            process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(result["hand_sequence"]["reverse_verified"])
            self.assertEqual(result["hand_sequence"]["profile"], hand)
            self.assertFalse(result["hand_sequence"]["trajectory_checked"])
            self.assertEqual([b["order"] for b in result["boxes"]], list(range(1, len(result["boxes"]) + 1)))
            self.assertEqual([b["layer_index"] for b in result["boxes"]],
                             sorted(b["layer_index"] for b in result["boxes"]))
            for b in result["boxes"]:
                self.assertTrue(b["hand_grasp"]["static_verified"])
                self.assertTrue(b["hand_grasp"]["envelope"])
                self.assertTrue(all(lower < b["order"] for lower in b["supported_by"]))
                self.assertFalse(check_static_hand(result, hand, b["order"],
                                                   b["hand_grasp"]["corner_id"])["has_interference"])
            before = output.read_bytes()
            hand["parameters"]["u_end_distance"] = 10000
            settings.write_text(json.dumps({"schema_version": 1, "profiles": [hand]}), encoding="utf-8")
            process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("HandSequenceError", process.stderr)
            self.assertEqual(output.read_bytes(), before)
            output.unlink()
            process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(process.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
