import json
import os
import tempfile
import unittest

from algorithm_programmer.models import BoxSpec, PalletSpec
from algorithm_programmer.palletizer import Palletizer
from supervisor.validate import PalletizeValidator, load_box_db, load_lid_db


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


if __name__ == "__main__":
    unittest.main()