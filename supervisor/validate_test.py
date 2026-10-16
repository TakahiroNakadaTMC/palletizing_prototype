import json
import os
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from unittest.mock import mock_open, patch

from algorithm_programmer.models import BoxSpec, PalletSpec
from algorithm_programmer.palletizer import MIXED_LAYER_SEARCH_WIDTH, Palletizer
from supervisor.validate import (
    PalletizeValidator,
    get_footprint_bounds,
    load_box_db,
    load_lid_db,
    normalize_result_coordinates
)


class SmallEdgeOverhangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.box_db = load_box_db()
        cls.lid_db = load_lid_db()
        cls.validator = PalletizeValidator(cls.box_db, cls.lid_db)
        cls.no_lid_id = next(lid_id for lid_id, lid in cls.lid_db.items() if lid.get("type") == "NONE")

    def validate_boxes(self, box_specs, overhang_limit=30.0):
        boxes = []
        for order, spec in enumerate(box_specs, start=1):
            master = self.box_db[spec["box_id"]]
            rotation = spec.get("rotation", 0)
            lid_id = spec.get("lid_id", self.no_lid_id)
            lid = self.lid_db[lid_id]
            body_width, body_length = (
                (master["width"], master["length"])
                if rotation == 0 else (master["length"], master["width"])
            )
            lid_width, lid_length = (
                (lid["width"], lid["length"])
                if rotation == 0 else (lid["length"], lid["width"])
            )
            boxes.append({
                "order": order,
                "box_id": spec["box_id"],
                "position": {"x": spec["x"], "y": spec["y"], "z": spec.get("z", 0.0)},
                "dimensions": {
                    "width": body_width,
                    "length": body_length,
                    "height": master["height"] + lid["thickness"]
                },
                "rotation": rotation,
                "fitting_depth": master["fitting_depth"],
                "lid_id": lid_id,
                "lid_thickness": lid["thickness"],
                "lid_dimensions": {"width": lid_width, "length": lid_length},
                "lid_fit_type": lid["fit_type"]
            })

        data = {
            "test_name": "small_edge_overhang_test",
            "pallet": {
                "length": 1200.0,
                "width": 1000.0,
                "max_small_edge_overhang_mm": overhang_limit
            },
            "boxes": boxes
        }
        path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as output:
                json.dump(data, output)
                path = output.name
            return self.validator.validate_case(path)
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    @staticmethod
    def small_edge_violations(result):
        return [v for v in result["violations"] if "最下段小辺はみ出し違反" in v]

    def test_29_mm_is_allowed_and_30_mm_is_rejected(self):
        within_limit = self.validate_boxes([{"box_id": "TP-362", "x": -29.0, "y": 100.0}])
        at_limit = self.validate_boxes([{"box_id": "TP-362", "x": -30.0, "y": 100.0}])

        self.assertEqual(self.small_edge_violations(within_limit), [])
        self.assertEqual(len(self.small_edge_violations(at_limit)), 1)

    def test_rotated_long_edge_may_overhang(self):
        result = self.validate_boxes([{
            "box_id": "TP-362", "rotation": 90, "x": -30.0, "y": 100.0
        }])

        self.assertEqual(self.small_edge_violations(result), [])

    def test_upper_layer_is_exempt(self):
        result = self.validate_boxes([
            {"box_id": "TP-362", "x": 0.0, "y": 100.0},
            {"box_id": "TP-362", "x": -30.0, "y": 100.0, "z": 185.0}
        ])

        self.assertEqual(self.small_edge_violations(result), [])

    def test_external_lid_is_included_in_overhang(self):
        result = self.validate_boxes([{
            "box_id": "TP-331", "x": -25.6, "y": 100.0,
            "lid_id": "サンボックス330フタ"
        }])

        self.assertEqual(len(self.small_edge_violations(result)), 1)

    def test_overhang_limit_is_configurable(self):
        result = self.validate_boxes(
            [{"box_id": "TP-362", "x": -25.0, "y": 100.0}],
            overhang_limit=25.0
        )

        self.assertEqual(len(self.small_edge_violations(result)), 1)

    def test_off_center_load_is_rejected(self):
        result = self.validate_boxes([{"box_id": "TP-362", "x": 0.0, "y": 100.0}])

        self.assertTrue(any("荷姿センタリング違反" in v for v in result["violations"]))

    def test_new_position_reference_normalizes_xy_and_top_z(self):
        data = {
            "coordinate_reference": "combined_footprint_min_xy_top_z",
            "boxes": [{
                "position": {"x": 10.0, "y": 20.0, "z": 120.0},
                "dimensions": {"width": 100.0, "length": 200.0, "height": 120.0},
                "lid_dimensions": {"width": 140.0, "length": 220.0},
                "lid_fit_type": "外嵌め"
            }]
        }

        normalized = normalize_result_coordinates(data)
        box = normalized["boxes"][0]

        self.assertEqual(box["position"], {"x": 30.0, "y": 30.0, "z": 0.0})
        self.assertEqual(get_footprint_bounds(box), (10.0, 20.0, 150.0, 240.0))
        self.assertEqual(data["boxes"][0]["position"]["z"], 120.0)

    def test_legacy_position_reference_is_left_unchanged(self):
        data = {"boxes": [{"position": {"x": 10.0, "y": 20.0, "z": 30.0}}]}

        normalized = normalize_result_coordinates(data)

        self.assertIs(normalized, data)
        self.assertEqual(normalized["boxes"][0]["position"]["z"], 30.0)

    def test_external_lid_tp_column_allows_different_box_ids(self):
        result = self.validate_boxes([
            {"box_id": "TP-331", "x": 428.0, "y": 328.0,
             "lid_id": "サンボックス330フタ"},
            {"box_id": "TP-332", "x": 428.0, "y": 328.0, "z": 106.0,
             "lid_id": "サンボックス330フタ"}
        ])

        self.assertFalse(any("コラム積み条件違反" in v for v in result["violations"]))

    def test_external_lid_tp_column_rejects_different_lid(self):
        result = self.validate_boxes([
            {"box_id": "TP-331", "x": 428.0, "y": 328.0,
             "lid_id": "サンボックス330フタ"},
            {"box_id": "TP-332", "x": 428.0, "y": 328.0, "z": 106.0,
             "lid_id": "TP330フタ"}
        ])

        self.assertTrue(any("コラム積み条件違反" in v for v in result["violations"]))

    def test_external_lid_tp_column_rejects_offset_positions(self):
        result = self.validate_boxes([
            {"box_id": "TP-331", "x": 428.0, "y": 328.0,
             "lid_id": "サンボックス330フタ"},
            {"box_id": "TP-332", "x": 429.0, "y": 328.0, "z": 106.0,
             "lid_id": "サンボックス330フタ"}
        ])

        self.assertTrue(any("コラム積み条件違反" in v for v in result["violations"]))

    def test_palletizer_stacks_different_tp_ids_with_the_same_external_lid(self):
        box_specs = {
            box_id: BoxSpec.from_dict(data)
            for box_id, data in self.box_db.items()
        }
        palletizer = Palletizer(box_specs, PalletSpec())
        result = palletizer.run("external_lid_tp_column", [
            {"box_id": "TP-331", "count": 9, "lid_id": "サンボックス330フタ"},
            {"box_id": "TP-332", "count": 9, "lid_id": "サンボックス330フタ"}
        ], self.lid_db)

        result_data = result.to_dict()
        self.assertEqual(result_data["coordinate_reference"],
                         "combined_footprint_min_xy_top_z")
        for placed_box, result_box in zip(result.boxes, result_data["boxes"]):
            self.assertAlmostEqual(result_box["position"]["x"], placed_box.footprint_min_x)
            self.assertAlmostEqual(result_box["position"]["y"], placed_box.footprint_min_y)
            self.assertAlmostEqual(result_box["position"]["z"], placed_box.top_z)

        bottom_boxes = [box for box in result.boxes if box.box_id == "TP-331"]
        upper_boxes = [box for box in result.boxes if box.box_id == "TP-332" and box.z > 0.0]
        self.assertEqual(len(bottom_boxes), 9)
        self.assertEqual(len(upper_boxes), 9)
        for upper in upper_boxes:
            self.assertTrue(any(
                abs(lower.footprint_min_x - upper.footprint_min_x) <= 0.01
                and abs(lower.footprint_min_y - upper.footprint_min_y) <= 0.01
                and abs(lower.max_x - upper.max_x) <= 0.01
                and abs(lower.max_y - upper.max_y) <= 0.01
                for lower in bottom_boxes
            ))
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as output:
            json.dump(result.to_dict(), output)
            result_path = output.name
        try:
            validation = self.validator.validate_case(result_path)
        finally:
            os.unlink(result_path)
        self.assertTrue(validation["is_pass"], validation["violations"])

    def test_palletizer_does_not_stack_external_lid_tp_on_a_different_lid(self):
        box_specs = {
            box_id: BoxSpec.from_dict(data)
            for box_id, data in self.box_db.items()
        }
        palletizer = Palletizer(box_specs, PalletSpec())
        result = palletizer.run("external_lid_tp_different_lids", [
            {"box_id": "TP-331", "count": 9, "lid_id": "サンボックス330フタ"},
            {"box_id": "TP-332", "count": 9, "lid_id": "TP330フタ"}
        ], self.lid_db)

        self.assertFalse(any(box.box_id == "TP-332" and box.z > 0.0 for box in result.boxes))


class MixedLayerSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.box_db = load_box_db()
        cls.lid_db = load_lid_db()
        testcase_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                     "test_programmer", "test_cases", "outer_cover_test.json")
        with open(testcase_path, encoding="utf-8") as source:
            cls.testcase = json.load(source)
        cls.validator = PalletizeValidator(cls.box_db, cls.lid_db)

    def make_engine_and_pool(self):
        engine = Palletizer(
            {box_id: BoxSpec.from_dict(data) for box_id, data in self.box_db.items()},
            PalletSpec.from_dict(self.testcase["pallet"])
        )
        pool = []
        for entry in self.testcase["box_list"]:
            lid = self.lid_db[entry["lid_id"]]
            spec = replace(engine.box_db[entry["box_id"]],
                           lid_id=entry["lid_id"], lid_width=lid["width"],
                           lid_length=lid["length"], lid_thickness=lid["thickness"],
                           lid_fit_type=lid["fit_type"])
            pool.extend([spec] * entry["count"])
        return engine, pool

    def test_mixed_depth_combination_is_retained(self):
        engine, pool = self.make_engine_and_pool()
        envelope = engine._determine_mixed_envelope(pool)
        self.assertGreaterEqual(envelope["y_span"], 1034.0)
        layer_pool = [box for box in pool if box.height + box.lid_thickness == 116.0]
        candidates = engine._mixed_layer_candidates(layer_pool, 0.0, 0, [], envelope)
        proposed = [boxes for boxes, _ in candidates
                    if Counter(box.box_id for box in boxes) == {"TP-341": 4, "TP-331": 3}]
        self.assertTrue(proposed)
        for boxes in proposed:
            self.assertAlmostEqual(max(box.max_x for box in boxes)
                                   - min(box.footprint_min_x for box in boxes), 1032.0)
            self.assertAlmostEqual(max(box.max_y for box in boxes)
                                   - min(box.footprint_min_y for box in boxes), 1034.0)

    def test_candidate_limit_inventory_and_input_are_preserved(self):
        engine, pool = self.make_engine_and_pool()
        layer_pool = [box for box in pool if box.height + box.lid_thickness == 116.0]
        original_specs = [dict(box.__dict__) for box in layer_pool]
        original_counts = Counter(box.pool_key for box in layer_pool)
        candidates = engine._mixed_layer_candidates(
            layer_pool, 0.0, 0, [], engine._determine_mixed_envelope(pool)
        )
        self.assertLessEqual(len(candidates), MIXED_LAYER_SEARCH_WIDTH)
        for boxes, remaining in candidates:
            counts = Counter((box.box_id, box.lid_id) for box in boxes)
            counts.update(box.pool_key for box in remaining)
            self.assertEqual(counts, original_counts)
        self.assertEqual([dict(box.__dict__) for box in layer_pool], original_specs)

    def test_tighter_depth_limit_is_respected(self):
        engine, pool = self.make_engine_and_pool()
        engine.pallet.max_y_span = 1034.0
        envelope = engine._determine_mixed_envelope(pool)
        layer_pool = [box for box in pool if box.height + box.lid_thickness == 116.0]
        candidates = engine._mixed_layer_candidates(layer_pool, 0.0, 0, [], envelope)
        self.assertTrue(candidates)
        for boxes, _ in candidates:
            self.assertLessEqual(max(box.max_y for box in boxes), envelope["y_span"] + 1e-3)

    def test_final_layout_improves_loading_and_passes_validation(self):
        engine, _ = self.make_engine_and_pool()
        result = engine.run(self.testcase["name"], self.testcase["box_list"], self.lid_db)
        self.assertGreaterEqual(len(result.boxes), 48)
        bottom_ids = {box.box_id for box in result.boxes if box.z == 0.0}
        self.assertEqual(bottom_ids, {"TP-331", "TP-341"})
        counts = Counter(box.box_id for box in result.boxes)
        for entry in result.unplaced_boxes:
            counts[entry["box_id"]] += entry["count"]
        self.assertEqual(counts, Counter({entry["box_id"]: entry["count"]
                                         for entry in self.testcase["box_list"]}))
        with patch("builtins.open", mock_open(read_data=json.dumps(result.to_dict()))):
            validation = self.validator.validate_case("outer_cover_test.json")
        self.assertTrue(validation["is_pass"], validation["violations"])


if __name__ == "__main__":
    unittest.main()