import json
import unittest
from dataclasses import asdict, replace
from unittest.mock import mock_open, patch

from algorithm_programmer.models import BoxSpec, PalletSpec, PlacedBox
from algorithm_programmer.palletizer import Palletizer
from supervisor.validate import PalletizeValidator


class OverhangTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = BoxSpec("A", "A", "TP", 620.0, 520.0, 200.0, 10.0, 22.0)
        self.engine = Palletizer({"A": self.spec})

    def placed(self, **changes) -> PlacedBox:
        box = PlacedBox(1, "A", -20.0, -20.0, 0.0, 620.0, 520.0,
                        200.0, 10.0, 22.0, 0)
        return replace(box, **changes)

    def assert_validated(self, result, specs, lids=None) -> None:
        validator = PalletizeValidator(
            {key: asdict(spec) for key, spec in specs.items()},
            lids or {"": {"type": "NONE", "fit_type": "なし"}}
        )
        with patch("builtins.open", mock_open(read_data=json.dumps(result.to_dict()))):
            report = validator.validate_case("overhang.json")
        self.assertEqual(report["violations"], [])

    def test_normal_twenty_mm_inclusive_all_layers(self) -> None:
        result = self.engine.run("normal", [{"box_id": "A", "count": 12}])
        self.assertEqual(len(result.boxes), 12)
        self.assertEqual(result.summary["bounding_box"]["x_span"], 1240)
        self.assertEqual(result.summary["bounding_box"]["y_span"], 1040)
        self.assertEqual({box.layer_index for box in result.boxes}, {0, 1, 2})
        self.assert_validated(result, {"A": self.spec})
        for layer in (0, 1):
            for axis in ("x", "y"):
                with self.subTest(layer=layer, axis=axis):
                    self.assertFalse(self.engine._overhang_is_valid([
                        self.placed(layer_index=layer, **{axis: -20.01})]))
                    self.assertTrue(self.engine._overhang_is_valid([
                        self.placed(layer_index=layer)]))
        self.assertFalse(self.engine._overhang_is_valid([self.placed(x=600.01)]))
        self.assertFalse(self.engine._overhang_is_valid([self.placed(y=500.01)]))

    def test_xy_settings_are_independent_and_zero_is_valid(self) -> None:
        self.engine.pallet = PalletSpec(max_overhang_x_mm=5, max_overhang_y_mm=25)
        self.assertTrue(self.engine._overhang_is_valid([self.placed(x=-5, y=-25)]))
        self.assertFalse(self.engine._overhang_is_valid([self.placed(x=-5.01, y=-25)]))
        self.assertFalse(self.engine._overhang_is_valid([self.placed(x=-5, y=-25.01)]))
        self.engine.pallet = PalletSpec(max_overhang_x_mm=0, max_overhang_y_mm=0)
        self.assertTrue(self.engine._overhang_is_valid([self.placed(x=0, y=0)]))
        self.assertFalse(self.engine._overhang_is_valid([self.placed(x=-0.01, y=0)]))

    def test_exception_only_rotated_body_axis_at_670(self) -> None:
        self.engine._single_load_variant = ("A", "")
        for rotation in (0, 90):
            box = (self.placed(width=670, length=335, x=-70, y=0)
                   if rotation == 0 else
                   self.placed(width=335, length=670, x=0, y=-40, rotation=90))
            self.assertTrue(self.engine._overhang_is_valid([box]))
            self.assertFalse(self.engine._overhang_is_valid([
                replace(box, **({"width": 669.99} if rotation == 0 else {"length": 669.99}))]))
            self.assertFalse(self.engine._overhang_is_valid([
                replace(box, **({"y": -20.01} if rotation == 0 else {"x": -20.01}))]))

    def test_lid_counts_for_bounds_not_exception_qualification(self) -> None:
        self.engine._single_load_variant = ("A", "L")
        box = self.placed(x=-10, lid_id="L", lid_width=640, lid_length=520, lid_fit_type="外嵌め")
        self.assertTrue(self.engine._overhang_is_valid([box]))
        self.assertFalse(self.engine._overhang_is_valid([replace(box, lid_width=640.02)]))
        self.assertFalse(self.engine._overhang_is_valid([replace(box, lid_width=670)]))

    def test_exception_roundtrip_and_original_input_provenance(self) -> None:
        spec = replace(self.spec, width=670, length=335)
        engine = Palletizer({"A": spec})
        items = [{"box_id": "A", "count": 6}, {"box_id": "A", "count": 6}]
        result = engine.run("exception", items)
        self.assertEqual(len(result.boxes), 12)
        self.assertEqual(result.summary["bounding_box"]["x_span"], 1340)
        self.assertEqual(result.to_dict()["input_box_variants"], [{"box_id": "A", "lid_id": ""}])
        self.assert_validated(result, {"A": spec})
        mixed = engine.run("unknown_mixed", items + [{"box_id": "UNKNOWN", "count": 1}])
        self.assertEqual(len(mixed.input_box_variants), 2)
        self.assertIsNone(engine._single_load_variant)
        self.assertTrue(engine._overhang_is_valid(mixed.boxes))
        zero = engine.run("zero", items + [{"box_id": "UNKNOWN", "count": 0}])
        self.assertEqual(len(zero.boxes), 12)

    def test_mixed_input_with_unplaceable_type_stays_normal(self) -> None:
        tall = replace(self.spec, id="TALL", height=2000)
        engine = Palletizer({"A": self.spec, "TALL": tall})
        result = engine.run("mixed", [{"box_id": "A", "count": 12},
                                      {"box_id": "TALL", "count": 1}])
        self.assertEqual(len(result.boxes), 12)
        self.assertEqual({box.box_id for box in result.boxes}, {"A"})
        self.assertEqual(len(result.input_box_variants), 2)
        self.assertIsNone(engine._single_load_variant)
        self.assertTrue(engine._overhang_is_valid(result.boxes))
        self.assert_validated(result, {"A": self.spec, "TALL": tall})

    def test_lid_variants_are_not_single_input(self) -> None:
        spec = replace(self.spec, width=670, length=335)
        engine = Palletizer({"A": spec})
        result = engine.run("lids", [{"box_id": "A", "count": 6},
                                     {"box_id": "A", "lid_id": "L", "count": 6}],
                            {"NONE": {"type": "NONE"}, "L": {"fit_type": "なし"}})
        self.assertEqual(result.input_box_variants,
                         [{"box_id": "A", "lid_id": "L"}, {"box_id": "A", "lid_id": "NONE"}])
        self.assertIsNone(engine._single_load_variant)
        self.assertTrue(engine._overhang_is_valid(result.boxes))

    def test_mixed_large_rectangles_cover_corners_without_exception(self) -> None:
        for covered in (False, True):
            with self.subTest(covered=covered):
                a = replace(self.spec, width=670, length=335)
                b = replace(a, id="B", height=250)
                specs = {"A": a, "B": b}
                lids = {"L": {"width": 670, "length": 335, "thickness": 5,
                              "fit_type": "外嵌め"}} if covered else {"": {"type": "NONE"}}
                items = [{"box_id": key, "count": 12, "lid_id": "L" if covered else ""}
                         for key in specs]
                engine = Palletizer(specs)
                result = engine.run("mixed_pinwheel", items, lids)
                self.assertGreater(len(result.boxes), 0)
                self.assertTrue(result.summary["is_valid"], result.summary)
                self.assertEqual(result.summary["bounding_box"]["x_span"], 1005)
                self.assertEqual(result.summary["bounding_box"]["y_span"], 1005)
                self.assertTrue(engine._overhang_is_valid(result.boxes))
                self.assert_validated(result, specs, lids)

    def test_missing_corner_is_not_reported_as_valid(self) -> None:
        boxes = [self.placed(x=x + 97.5, y=y - 2.5, width=w, length=l)
                 for x, y, w, l in [(0, 0, 670, 335), (670, 0, 335, 670),
                                    (0, 335, 335, 670), (335, 335, 335, 670)]]
        summary = self.engine.calculate_summary(boxes)
        self.assertFalse(summary["is_valid"])
        self.assertIn("Top 4-corners coverage is incomplete", summary["violations"])

    def test_global_span_caps_remain_strict(self) -> None:
        engine = Palletizer({"A": self.spec}, PalletSpec(max_overhang_x_mm=100, max_overhang_y_mm=100))
        engine._single_load_variant = ("A", "")
        for width, length in ((1360, 1000), (1200, 1100)):
            box = self.placed(width=width, length=length,
                              x=(1200 - width) / 2, y=(1000 - length) / 2)
            self.assertFalse(engine.calculate_summary([box])["is_valid"])


class OverhangSettingsTests(unittest.TestCase):
    def test_defaults_and_serialization(self) -> None:
        pallet = PalletSpec.from_dict({})
        self.assertEqual(pallet.max_overhang_x_mm, 20)
        self.assertEqual(pallet.max_overhang_y_mm, 20)
        self.assertNotIn("max_small_edge_overhang_mm", asdict(pallet))
        custom = PalletSpec.from_dict({"max_overhang_x_mm": 0, "max_overhang_y_mm": 12.5})
        self.assertEqual((custom.max_overhang_x_mm, custom.max_overhang_y_mm), (0, 12.5))

    def test_retired_key_is_not_silently_ignored(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_overhang_x_mm"):
            PalletSpec.from_dict({"max_small_edge_overhang_mm": 30})

    def test_invalid_settings_are_rejected(self) -> None:
        for axis in ("x", "y"):
            for value in (-1, float("nan"), float("inf")):
                with self.subTest(axis=axis, value=value):
                    with self.assertRaises(ValueError):
                        PalletSpec.from_dict({f"max_overhang_{axis}_mm": value})


if __name__ == "__main__":
    unittest.main()
