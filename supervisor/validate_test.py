import json
import os
import tempfile
import unittest

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
                "width": 1200.0,
                "length": 1000.0,
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


if __name__ == "__main__":
    unittest.main()