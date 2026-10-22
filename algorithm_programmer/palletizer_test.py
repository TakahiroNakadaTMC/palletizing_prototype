import json
import unittest
from dataclasses import asdict, replace
from typing import Dict, List, Tuple
from unittest.mock import mock_open, patch

from algorithm_programmer.models import BoxSpec, PalletSpec, PlacedBox
from algorithm_programmer.palletizer import Palletizer
from supervisor.validate import PalletizeValidator


class SingleLayerPatternTests(unittest.TestCase):
    def setUp(self) -> None:
        self.box = BoxSpec(
            id="SINGLE-TEST", name="単載回帰テスト", type="TP",
            width=400.0, length=600.0, height=200.0,
            fitting_depth=10.0, rib_thickness=22.0
        )

    def assert_identical_layers(self, boxes: List[PlacedBox], count: int,
                                layers: int) -> None:
        patterns: Dict[int, List[Tuple[float, float, int]]] = {}
        for box in boxes:
            patterns.setdefault(box.layer_index, []).append((box.x, box.y, box.rotation))
        self.assertEqual(sorted(patterns), list(range(layers)))
        for pattern in patterns.values():
            self.assertEqual(len(pattern), count)
            self.assertEqual(sorted(pattern), sorted(patterns[0]))

    def test_asymmetric_split_repeats_through_public_run(self) -> None:
        engine = Palletizer({self.box.id: self.box})
        lids = {"NONE": {"type": "NONE", "width": 0.0, "length": 0.0,
                         "thickness": 0.0, "fit_type": "なし"}}
        result = engine.run("single_split", [{"box_id": self.box.id, "count": 15}], lids)
        self.assertEqual(result.unplaced_boxes, [])
        base = [box for box in result.boxes if box.layer_index == 0]
        self.assertEqual({box.rotation for box in base}, {0, 90})
        original = {(box.x, box.y, box.rotation) for box in base}
        reflected = {(1200 - box.x - box.width, 1000 - box.y - box.length, box.rotation)
                     for box in base}
        self.assertNotEqual(original, reflected)
        self.assert_identical_layers(result.boxes, 5, 3)
        self.assertEqual({box.z for box in result.boxes}, {0.0, 190.0, 380.0})
        self.assertEqual([box.order for box in result.boxes], list(range(1, 16)))
        for box in result.boxes:
            if box.layer_index > 0:
                self.assertEqual(len(box.supported_by), 1)
                self.assertLess(box.supported_by[0], box.order)
        validator = PalletizeValidator({self.box.id: asdict(self.box)}, lids)
        with patch("builtins.open", mock_open(read_data=json.dumps(result.to_dict()))):
            validation = validator.validate_case("single_split.json")
        self.assertEqual(validation["violations"], [])

    def test_grid_retains_positions_and_height(self) -> None:
        box = replace(self.box, width=335.0, length=335.0)
        engine = Palletizer({box.id: box})
        placed, unplaced = engine.palletize_single([box] * 18)
        self.assertEqual(unplaced, [])
        self.assert_identical_layers(placed, 9, 2)
        self.assertEqual({item.x for item in placed}, {97.5, 432.5, 767.5})
        self.assertEqual({item.y for item in placed}, {-2.5, 332.5, 667.5})
        self.assertEqual(max(item.top_z for item in placed), 390.0)

    def test_column_variants_repeat_and_pass_validation(self) -> None:
        for box_type, fit_type in (("NON_TP", "なし"), ("TP", "外嵌め"), ("TP", "内嵌め")):
            with self.subTest(box_type=box_type, fit_type=fit_type):
                box = replace(self.box, type=box_type)
                lids = {"NONE": {"type": "NONE", "width": 0.0, "length": 0.0,
                                 "thickness": 0.0, "fit_type": "なし"}}
                item = {"box_id": box.id, "count": 15}
                if fit_type != "なし":
                    box = replace(box, width=380.0, length=580.0)
                    lids = {"LID": {"width": 400.0, "length": 600.0,
                                    "thickness": 5.0, "fit_type": fit_type}}
                    item["lid_id"] = "LID"
                result = Palletizer({box.id: box}).run("single_variant", [item], lids)
                self.assertEqual(result.unplaced_boxes, [])
                self.assert_identical_layers(result.boxes, 5, 3)
                effective_height = 205.0 if fit_type != "なし" else 200.0
                for placed in result.boxes:
                    self.assertEqual(placed.z, placed.layer_index * (effective_height - 10.0))
                    self.assertEqual(placed.height, effective_height)
                    if fit_type != "なし":
                        self.assertEqual(placed.x - placed.footprint_min_x, 10.0)
                        self.assertEqual(placed.y - placed.footprint_min_y, 10.0)
                validator = PalletizeValidator({box.id: asdict(box)}, lids)
                with patch("builtins.open", mock_open(read_data=json.dumps(result.to_dict()))):
                    validation = validator.validate_case("single_variant.json")
                self.assertEqual(validation["violations"], [])

    def test_remainder_does_not_create_upper_layer(self) -> None:
        engine = Palletizer({self.box.id: self.box})
        for count in (5, 7, 10, 12):
            with self.subTest(count=count):
                result = engine.run("single_remainder", [{"box_id": self.box.id, "count": count}])
                self.assert_identical_layers(result.boxes, 5, count // 5)
                expected = [{"box_id": self.box.id, "count": count % 5,
                             "reason": "最上段を一層分そろえられず、四隅高さ一致を保てません"}] if count % 5 else []
                self.assertEqual(result.unplaced_boxes, expected)

    def test_partial_first_layer_is_preserved(self) -> None:
        engine = Palletizer({self.box.id: self.box})
        full, _ = engine.palletize_single([self.box] * 5)
        placed, unplaced = engine.palletize_single([self.box] * 2)
        self.assertEqual(placed, full[:2])
        self.assertEqual(unplaced, [])

    def test_height_limit_keeps_complete_layers(self) -> None:
        for limit, layers in ((579.0, 2), (580.0, 3), (1200.0, 6)):
            with self.subTest(limit=limit):
                engine = Palletizer({self.box.id: self.box}, PalletSpec(max_height=limit))
                placed, unplaced = engine.palletize_single([self.box] * 40)
                self.assert_identical_layers(placed, 5, layers)
                self.assertLessEqual(max(box.top_z for box in placed), limit)
                self.assertEqual(unplaced, [{"box_id": self.box.id, "count": 40 - 5 * layers,
                                            "reason": "最大積載高さの上限に達しました"}])


if __name__ == "__main__":
    unittest.main()
