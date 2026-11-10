import json
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from typing import Dict, List, Tuple
from unittest.mock import mock_open, patch

from algorithm_programmer.cli import resolve_box_specs
from algorithm_programmer.models import BoxSpec, PalletSpec, PlacedBox
from algorithm_programmer.palletizer import (
    Palletizer, _generate_pinwheel_pattern, intersects_2d
)
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
        result = engine.run("single_split", [{"box_id": self.box.id, "count": 15}])
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
        lids = {"": {"type": "NONE", "fit_type": "なし"}}
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
                item = {"box_id": box.id, "count": 15}
                if fit_type != "なし":
                    box = replace(box, width=380.0, length=580.0)
                    item["lid_id"] = "LID"
                    box = replace(box, lid_id="LID", lid_width=400.0, lid_length=600.0,
                                  lid_thickness=5.0, lid_fit_type=fit_type)
                    specs = {(box.id, "LID"): box}
                    lids = {"LID": {"width": 400.0, "length": 600.0,
                                    "thickness": 5.0, "fit_type": fit_type}}
                else:
                    specs = {box.id: box}
                    lids = {"": {"type": "NONE", "fit_type": "なし"}}
                result = Palletizer(specs).run("single_variant", [item])
                if fit_type == "内嵌め":
                    self.assertEqual(result.unplaced_boxes, [{
                        "box_id": box.id, "count": 10,
                        "reason": "下段隅の被覆条件を満たせず上段に配置できません"
                    }])
                    self.assert_identical_layers(result.boxes, 5, 1)
                else:
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

    def test_stable_remainder_creates_only_final_partial_layer(self) -> None:
        engine = Palletizer({self.box.id: self.box})
        for count, per_layer in ((5, 5), (7, 3), (10, 5), (12, 4)):
            with self.subTest(count=count):
                result = engine.run("single_remainder", [{"box_id": self.box.id, "count": count}])
                if count == 7:
                    base = [b for b in result.boxes if b.layer_index == 0]
                    top = [b for b in result.boxes if b.layer_index == 1]
                    self.assertEqual((len(base), len(top)), (5, 0))
                    self.assertTrue({(b.x, b.y, b.rotation) for b in top}.issubset(
                        {(b.x, b.y, b.rotation) for b in base}))
                else:
                    self.assert_identical_layers(result.boxes, per_layer, count // per_layer)
                if count == 7:
                    self.assertEqual(sum(b["count"] for b in result.unplaced_boxes), 2)
                else:
                    self.assertEqual(result.unplaced_boxes, [])
                self.assertTrue(result.summary["is_valid"])

    def test_tp341_total_count_then_height_and_constraints(self) -> None:
        db_path = Path(__file__).resolve().parents[1] / "box_research" / "box_db.json"
        raw = json.loads(db_path.read_text(encoding="utf-8"))["TP341"]
        box = BoxSpec.from_dict(raw)
        lids = {"": {"type": "NONE", "fit_type": "なし"}}
        cases = (
            (15, 1200.0, 7, 2, 195.0),
            (14, 1200.0, 7, 2, 195.0),
            (30, 1200.0, 6, 5, 472.5),
            (16, 1200.0, 6, 3, 287.5),
            (15, 287.4, 7, 2, 195.0),
            (15, 287.5, 7, 2, 195.0),
        )
        for count, limit, per_layer, layers, height in cases:
            with self.subTest(count=count, limit=limit):
                engine = Palletizer({box.id: box}, PalletSpec(max_height=limit))
                result = engine.run("tp341_selection", [{"box_id": box.id, "count": count}])
                if count == 16:
                    self.assertEqual([sum(b.layer_index == i for b in result.boxes)
                                      for i in range(layers)], [6, 6, 4])
                    self.assert_identical_layers(result.boxes[:12], 6, 2)
                else:
                    self.assert_identical_layers(result.boxes, per_layer, layers)
                self.assertEqual(max(item.top_z for item in result.boxes), height)
                self.assertEqual(sum(item["count"] for item in result.unplaced_boxes),
                                 max(0, count - per_layer * layers))
                self.assertTrue(result.summary["is_valid"])
                validator = PalletizeValidator({box.id: raw}, lids)
                with patch("builtins.open", mock_open(read_data=json.dumps(result.to_dict()))):
                    validation = validator.validate_case("tp341_selection.json")
                self.assertEqual(validation["violations"], [])
                self.assertEqual(result.to_dict(), engine.run(
                    "tp341_selection", [{"box_id": box.id, "count": count}]).to_dict())

    def test_reduced_layers_with_lids_and_non_tp(self) -> None:
        for box_type, fit_type in (("NON_TP", "なし"), ("TP", "外嵌め"), ("TP", "内嵌め")):
            box = replace(self.box, type=box_type, width=335.0, length=502.5, height=102.5)
            thickness = 0.0 if fit_type == "なし" else 5.0
            lids = {"TEST-LID": {"width": 335.0, "length": 502.5,
                                 "thickness": thickness, "fit_type": fit_type}}
            item = {"box_id": box.id, "count": 15, "lid_id": "TEST-LID"}
            box = replace(box, lid_id="TEST-LID", lid_width=335.0, lid_length=502.5,
                          lid_thickness=thickness, lid_fit_type=fit_type)
            full_height = 287.5 + 3 * thickness
            for limit, per_layer, layers in ((full_height, 7, 2), (full_height - 0.1, 7, 2)):
                with self.subTest(box_type=box_type, fit_type=fit_type, limit=limit):
                    engine = Palletizer({(box.id, "TEST-LID"): box},
                                        PalletSpec(max_height=limit))
                    result = engine.run("single_reduced_variant", [item])
                    self.assert_identical_layers(result.boxes, per_layer, layers)
                    self.assertEqual(max(b.top_z for b in result.boxes),
                                     102.5 + thickness + (layers - 1) * (92.5 + thickness))
                    validator = PalletizeValidator({box.id: asdict(box)}, lids)
                    with patch("builtins.open", mock_open(read_data=json.dumps(result.to_dict()))):
                        validation = validator.validate_case("single_reduced_variant.json")
                    self.assertEqual(validation["violations"], [])

    def test_reduced_split_patterns_are_generated_without_duplicates(self) -> None:
        engine = Palletizer({self.box.id: self.box})
        patterns = engine._generate_single_2d_patterns(335.0, 502.5)
        for x_span, y_span in ((837.5, 1005.0), (1005.0, 837.5)):
            with self.subTest(x_span=x_span, y_span=y_span):
                self.assertTrue(any(len(pattern["boxes"]) == 5
                                    and pattern["x_span"] == x_span
                                    and pattern["y_span"] == y_span for pattern in patterns))
        keys = [tuple(sorted((b["x"], b["y"], b["w"], b["l"], b["rot"])
                             for b in pattern["boxes"])) for pattern in patterns]
        self.assertEqual(len(keys), len(set(keys)))

    def test_missing_corner_pattern_without_opposing_support_is_rejected(self) -> None:
        engine = Palletizer({self.box.id: self.box})
        full = next(pattern for pattern in engine._generate_single_2d_patterns(400.0, 600.0)
                    if len(pattern["boxes"]) == 5)
        missing_corner = dict(full, boxes=full["boxes"][:-1])
        with patch.object(engine, "_generate_single_2d_patterns",
                          return_value=[missing_corner, full]), patch(
                              "algorithm_programmer.palletizer._generate_pinwheel_pattern",
                              return_value=None):
            placed, unplaced = engine.palletize_single([self.box] * 12)
        self.assertEqual(len(placed), 10)
        self.assertEqual([sum(b.layer_index == i for b in placed) for i in range(2)], [5, 5])
        self.assertEqual(sum(b["count"] for b in unplaced), 2)
        support = engine.calculate_summary(placed)["top_support"]
        self.assertTrue(support["is_valid"])
        self.assertFalse(support["long_edge_exception"])
        self.assertEqual(support["corners_supported"], [True] * 4)

    def test_no_placement_when_height_or_footprint_cannot_fit(self) -> None:
        for box, pallet in ((self.box, PalletSpec(max_height=199.0)),
                            (replace(self.box, width=1400.0), PalletSpec())):
            with self.subTest(box=box, pallet=pallet):
                result = Palletizer({box.id: box}, pallet).run(
                    "single_impossible", [{"box_id": box.id, "count": 15}])
                self.assertEqual(result.boxes, [])
                self.assertEqual(sum(item["count"] for item in result.unplaced_boxes), 15)
                self.assertFalse(result.summary["is_valid"])

    def test_small_input_rejected_by_support_area_and_short_side(self) -> None:
        engine = Palletizer({self.box.id: self.box})
        placed, unplaced = engine.palletize_single([self.box] * 2)
        self.assertEqual(placed, [])
        self.assertFalse(engine.calculate_summary(placed)["is_valid"])
        self.assertEqual(sum(item["count"] for item in unplaced), 2)

    def test_height_limit_keeps_complete_layers(self) -> None:
        for limit, layers in ((579.0, 2), (580.0, 3), (1200.0, 6)):
            with self.subTest(limit=limit):
                engine = Palletizer({self.box.id: self.box}, PalletSpec(max_height=limit))
                placed, unplaced = engine.palletize_single([self.box] * 40)
                self.assert_identical_layers(placed, 5, layers)
                self.assertLessEqual(max(box.top_z for box in placed), limit)
                self.assertEqual(unplaced, [{"box_id": self.box.id, "count": 40 - 5 * layers,
                                            "reason": "最大積載高さの上限に達しました"}])

    def test_real_cases_repeat_and_pass_top_support_validation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        raw_boxes = json.loads((root / "box_research" / "box_db.json").read_text(encoding="utf-8"))
        lids = json.loads((root / "box_research" / "lid_db.json").read_text(encoding="utf-8"))
        validator = PalletizeValidator(raw_boxes, lids)
        for name, per_layer, layers, x_span, y_span, height, unplaced in (
                ("aisin_10", 4, 1, 1005.0, 1005.0, 395.0, 0),
                ("aisin_9", 4, 2, 1005.0, 1005.0, 780.0, 0),
                ("nittan", 4, 2, 1107.0, 1107.0, 311.0, 0),
                ("nittan_2", 3, 3, 1107.0, 846.0, 462.0, 0)):
            with self.subTest(name=name):
                case = json.loads((root / "test_programmer" / "test_cases" /
                                   (name + ".json")).read_text(encoding="utf-8"))
                box_specs, box_list = resolve_box_specs(case["box_list"], raw_boxes, lids)
                engine = Palletizer(box_specs, PalletSpec.from_dict(case["pallet"]))
                result = engine.run(name, box_list)
                self.assert_identical_layers(result.boxes, per_layer, layers)
                bounds = result.summary["bounding_box"]
                self.assertEqual((bounds["x_span"], bounds["y_span"]), (x_span, y_span))
                self.assertEqual(bounds["max_z"], height)
                self.assertEqual(sum(row["count"] for row in result.unplaced_boxes), unplaced)
                base = [box for box in result.boxes if box.layer_index == 0]
                center_x = engine.pallet.length / 2.0
                center_y = engine.pallet.width / 2.0
                self.assertTrue(result.summary["top_support"]["is_valid"])
                for index, box in enumerate(base):
                    if name == "nittan":
                        self.assertFalse(box.footprint_min_x < center_x < box.max_x and
                                         box.footprint_min_y < center_y < box.max_y)
                    for other in base[index + 1:]:
                        self.assertFalse(intersects_2d(
                            box.footprint_min_x, box.footprint_min_y,
                            box.footprint_width, box.footprint_length,
                            other.footprint_min_x, other.footprint_min_y,
                            other.footprint_width, other.footprint_length))
                for box in result.boxes:
                    if box.layer_index > 0:
                        self.assertEqual(len(box.supported_by), 1)
                        self.assertLess(box.supported_by[0], box.order)
                self.assertEqual(result.input_boxes_count, len(result.boxes) + unplaced)
                with patch("builtins.open", mock_open(read_data=json.dumps(result.to_dict()))):
                    validation = validator.validate_case(name + ".json")
                self.assertEqual(validation["violations"], [])

    def test_occupancy_uses_lid_footprint_and_same_column_positions(self) -> None:
        box = replace(self.box, type="NON_TP", width=300.0, length=600.0,
                      lid_id="LID", lid_width=335.0, lid_length=670.0,
                      lid_thickness=15.0, lid_fit_type="外嵌め")
        engine = Palletizer({box.id: box}, PalletSpec(max_x_span=1340.0, max_y_span=1005.0))
        placed, unplaced = engine.palletize_single([box] * 8)
        self.assert_identical_layers(placed, 4, 2)
        self.assertEqual(unplaced, [])
        summary = engine.calculate_summary(placed)
        self.assertEqual(summary["bounding_box"]["x_span"], 1005.0)
        self.assertEqual(summary["bounding_box"]["y_span"], 1005.0)
        self.assertTrue(summary["is_valid"])

    def test_more_boxes_outrank_higher_occupancy(self) -> None:
        box = replace(self.box, width=335.0, length=335.0, height=102.5)
        result = Palletizer({box.id: box}, PalletSpec(
            max_x_span=1005.0, max_y_span=1005.0)).run(
                "count_first", [{"box_id": box.id, "count": 10}])
        self.assert_identical_layers(result.boxes, 5, 2)
        self.assertEqual(result.unplaced_boxes, [])
        self.assertEqual(result.summary["top_support"]["corners_supported"], [True] * 4)

    def test_lower_height_outranks_higher_occupancy(self) -> None:
        box = replace(self.box, width=335.0, length=670.0)
        result = Palletizer({box.id: box}, PalletSpec(
            max_x_span=1340.0, max_y_span=1005.0)).run(
                "height_first", [{"box_id": box.id, "count": 6}])
        self.assert_identical_layers(result.boxes, 6, 1)
        self.assertEqual(result.summary["bounding_box"]["x_span"], 1340.0)
        self.assertEqual(result.summary["bounding_box"]["y_span"], 1005.0)

    def test_score_occupancy_tie_prefers_x_long_independent_of_candidate_order(self) -> None:
        box = replace(self.box, width=335.0, length=335.0)
        engine = Palletizer({box.id: box}, PalletSpec(max_x_span=1005.0, max_y_span=1005.0))
        patterns = [pattern for pattern in engine._generate_single_2d_patterns(335.0, 335.0)
                    if len(pattern["boxes"]) == 2]
        for candidates in (patterns, list(reversed(patterns))):
            with self.subTest(first=candidates[0]["boxes"]):
                layouts = [engine._single_pattern_boxes(box, p) for p in candidates]
                placed = max(layouts, key=engine._layout_score)
                expected = next(p for p in candidates if p["x_span"] >= p["y_span"])
                bounds = engine.calculate_summary(placed)["bounding_box"]
                self.assertEqual((bounds["x_span"], bounds["y_span"]),
                                 (expected["x_span"], expected["y_span"]))

    def test_invalid_support_rejects_wider_pinwheel(self) -> None:
        box = replace(self.box, width=335.0, length=670.0)
        engine = Palletizer({box.id: box}, PalletSpec(
            length=800.0, width=800.0, max_x_span=1005.0, max_y_span=1005.0))
        result = engine.run("support_first", [{"box_id": box.id, "count": 4}])
        self.assertEqual(result.boxes, [])
        self.assertFalse(result.summary["is_valid"])
        self.assertLess(800 * 800 / (1005 * 1005), 0.65)

    def test_pinwheel_limit_inclusive_and_below_limit_rejected(self) -> None:
        box = replace(self.box, width=335.0, length=670.0)
        for x_limit, y_limit, placed_count in ((1005.0, 1005.0, 4),
                                              (1005.0, 1004.99, 3),
                                              (1004.99, 1004.99, 0)):
            with self.subTest(x_limit=x_limit, y_limit=y_limit):
                engine = Palletizer({box.id: box}, PalletSpec(
                    max_x_span=x_limit, max_y_span=y_limit))
                result = engine.run("pinwheel_boundary", [{"box_id": box.id, "count": 4}])
                self.assertEqual(len(result.boxes), placed_count)
                self.assertEqual(result.summary["is_valid"], placed_count > 0)
                if placed_count:
                    self.assert_identical_layers(result.boxes, placed_count, 1)

    def test_pinwheel_geometry_handles_both_footprint_orientations(self) -> None:
        for w, l in ((335.0, 670.0), (670.0, 335.0)):
            with self.subTest(w=w, l=l):
                pattern = _generate_pinwheel_pattern(w, l, 1005.0, 1005.0)
                self.assertIsNotNone(pattern)
                if pattern is None:
                    self.fail("A rectangular footprint must produce one pinwheel")
                self.assertEqual(len(pattern["boxes"]), 4)
                self.assertEqual(pattern["x_span"], 1005.0)
                self.assertEqual(pattern["y_span"], 1005.0)
                for item in pattern["boxes"]:
                    self.assertEqual((item["w"], item["l"]),
                                     (w, l) if item["rot"] == 0 else (l, w))
        self.assertIsNone(_generate_pinwheel_pattern(335.0, 335.0, 1005.0, 1005.0))
        self.assertIsNone(_generate_pinwheel_pattern(335.0, 670.0, 1004.99, 1005.0))
        self.assertIsNone(_generate_pinwheel_pattern(335.0, 670.0, 1005.0, 1004.99))

    def test_small_input_does_not_generate_pinwheel(self) -> None:
        box = replace(self.box, length=800.0)
        engine = Palletizer({box.id: box}, PalletSpec(max_x_span=1200, max_y_span=800))
        with patch("algorithm_programmer.palletizer._generate_pinwheel_pattern") as generate:
            placed, unplaced = engine.palletize_single([box] * 3)
        generate.assert_not_called()
        self.assert_identical_layers(placed, 3, 1)
        self.assertEqual(unplaced, [])

    def test_dominated_pinwheel_skips_detailed_support_evaluation(self) -> None:
        box = replace(self.box, width=335.0, length=670.0)
        engine = Palletizer({box.id: box}, PalletSpec(
            max_x_span=1340.0, max_y_span=1005.0))
        with patch.object(engine, "_pallet_support_is_valid",
                          wraps=engine._pallet_support_is_valid) as support:
            placed, unplaced = engine.palletize_single([box] * 6)
        self.assert_identical_layers(placed, 6, 1)
        self.assertEqual(unplaced, [])
        self.assertNotIn(4, [len(call.args[0]) for call in support.call_args_list])

    def test_mixed_pinwheel_retains_geometry_inventory_and_upper_layer(self) -> None:
        other = replace(self.box, id="OTHER")
        engine = Palletizer({self.box.id: self.box, other.id: other})
        envelope = {"x_span": 1000.0, "y_span": 1000.0}
        candidates = engine._pinwheel_layer_candidates(
            [self.box] * 5 + [other], 0.0, 0, [], envelope)
        self.assertEqual(len(candidates), 1)
        layer, remaining = candidates[0]
        self.assertEqual([(box.x, box.y, box.rotation) for box in layer],
                         [(0.0, 0.0, 90), (600.0, 0.0, 0),
                          (400.0, 600.0, 90), (0.0, 400.0, 0)])
        self.assertEqual(remaining, [self.box, other])
        upper_candidates = engine._pinwheel_layer_candidates(
            [self.box] * 4, 190.0, 1, layer, envelope)
        self.assertEqual(len(upper_candidates), 1)
        upper, remaining = upper_candidates[0]
        self.assertEqual(remaining, [])
        self.assertEqual([(box.x, box.y, box.rotation) for box in upper],
                         [(box.x, box.y, box.rotation) for box in layer])
        self.assertEqual({box.z for box in upper}, {190.0})


if __name__ == "__main__":
    unittest.main()
