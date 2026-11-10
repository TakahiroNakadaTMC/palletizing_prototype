import json
import unittest
from dataclasses import asdict, replace
from unittest.mock import mock_open, patch

from algorithm_programmer.models import BoxSpec, PalletSpec, PlacedBox
from algorithm_programmer.palletizer import Palletizer, calculate_max_layers
from supervisor.validate import PalletizeValidator


class PalletDimensionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = BoxSpec("A", "A", "TP", 620.0, 520.0, 200.0, 10.0, 22.0)

    def assert_validated(self, result, specs, lids=None) -> None:
        validator = PalletizeValidator(
            {key: asdict(spec) for key, spec in specs.items()},
            lids or {"": {"type": "NONE", "fit_type": "なし"}}
        )
        with patch("builtins.open", mock_open(read_data=json.dumps(result.to_dict()))):
            report = validator.validate_case("dimensions.json")
        self.assertEqual(report["violations"], [], report)
        self.assertEqual(report["overhang_mm"], result.summary["overhang_mm"])

    def test_six_defaults_and_retired_settings_ignored(self) -> None:
        expected = dict(length=1200, width=1000, height=130,
                        max_x_span=1360, max_y_span=1100, max_height=1200)
        self.assertEqual(asdict(PalletSpec.from_dict({})), expected)
        retired = dict(min_x_span=800, min_y_span=800, max_overhang_x_mm=0,
                       max_overhang_y_mm=0, max_small_edge_overhang_mm=30)
        self.assertEqual(asdict(PalletSpec.from_dict(retired)), expected)
        swapped = PalletSpec.from_dict(dict(length=900, width=1100, height=150))
        self.assertEqual((swapped.length, swapped.width, swapped.height), (1100, 900, 150))

    def test_dimensions_must_be_positive_finite_numbers(self) -> None:
        for field in asdict(PalletSpec()):
            for value in (0, -1, float("nan"), float("inf"), None, "", "bad", True):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, field):
                        PalletSpec.from_dict({field: value})
        with self.assertRaises(ValueError):
            PalletSpec(max_x_span=900, max_y_span=1000)

    def test_decimal_roundoff_does_not_remove_equal_boundary(self) -> None:
        self.assertEqual(calculate_max_layers(100.1, 0, 300.3), 3)
        engine = Palletizer({}, PalletSpec(max_x_span=1200.3, max_y_span=1000))
        patterns = engine._generate_single_2d_patterns(400.1, 500)
        self.assertTrue(any(len(pattern["boxes"]) == 6 and
                            abs(pattern["x_span"] - 1200.3) < 1e-9 and
                            pattern["y_span"] == 1000 for pattern in patterns))

    def test_overhang_is_information_not_a_constraint(self) -> None:
        engine = Palletizer({"A": self.spec})
        result = engine.run("overhang", [{"box_id": "A", "count": 12}])
        self.assertEqual(len(result.boxes), 12)
        self.assertTrue(result.summary["is_valid"], result.summary)
        self.assertEqual(result.summary["overhang_mm"],
                         dict(left=20, right=20, front=20, back=20))
        self.assertTrue(result.summary["warnings"])
        self.assert_validated(result, {"A": self.spec})

    def test_small_single_box_rejected_by_upper_support_rules(self) -> None:
        spec = replace(self.spec, width=300, length=300, height=100)
        result = Palletizer({"A": spec}).run("small", [{"box_id": "A", "count": 1}])
        self.assertEqual(result.boxes, [])
        self.assertEqual(sum(b["count"] for b in result.unplaced_boxes), 1)
        self.assertEqual(result.summary["warnings"], [])
        self.assertFalse(result.summary["is_valid"])

    def test_exact_fractional_lwh_maxima_and_over_limit(self) -> None:
        spec = replace(self.spec, width=1360.5, length=1100.5, height=1250)
        pallet = PalletSpec(length=1400, width=1200, height=200,
                            max_x_span=1360.5, max_y_span=1100.5, max_height=1250)
        result = Palletizer({"A": spec}, pallet).run("limit", [{"box_id": "A", "count": 1}])
        self.assertEqual(len(result.boxes), 1)
        self.assertTrue(result.summary["is_valid"], result.summary)
        self.assertEqual(result.summary["total_height"], 1450)
        self.assert_validated(result, {"A": spec})
        for axis in ("max_x_span", "max_y_span", "max_height"):
            with self.subTest(axis=axis):
                smaller = replace(pallet, **{axis: getattr(pallet, axis) - 0.01})
                rejected = Palletizer({"A": spec}, smaller).run(
                    "over_limit", [{"box_id": "A", "count": 1}])
                self.assertEqual(rejected.boxes, [])
                self.assertFalse(rejected.summary["is_valid"])
                self.assertEqual(sum(item["count"] for item in rejected.unplaced_boxes), 1)

    def test_physical_height_does_not_change_cargo_placement(self) -> None:
        items = [{"box_id": "A", "count": 12}]
        first = Palletizer({"A": self.spec}, PalletSpec(height=130)).run("height", items)
        second = Palletizer({"A": self.spec}, PalletSpec(height=200)).run("height", items)
        self.assertEqual(first.boxes, second.boxes)
        self.assertEqual(second.summary["total_height"] - first.summary["total_height"], 70)

    def test_pallet_support_is_real_intersection_including_boundary(self) -> None:
        engine = Palletizer({"A": self.spec}, PalletSpec(length=850, width=850))
        self.assertAlmostEqual(engine._support_ratio(0, 0, 1000, 850, 0, 0, []), .85)
        self.assertTrue(engine._pallet_support_is_valid([
            PlacedBox(1, "A", 0, 0, 0, 1000, 850, 200, 0, 22, 0)]))
        self.assertLess(engine._support_ratio(-.01, 0, 1000, 1000, 0, 0, []), .85)
        spec = replace(self.spec, width=1300, length=1000)
        result = Palletizer({"A": spec}, PalletSpec(length=800, width=800)).run(
            "unsupported", [{"box_id": "A", "count": 1}])
        self.assertEqual(result.boxes, [])
        self.assertFalse(result.summary["is_valid"])

    def test_lid_footprint_counts_for_maxima_and_warnings(self) -> None:
        spec = replace(self.spec, width=800, length=700, lid_id="L",
                       lid_width=840, lid_length=740, lid_thickness=5,
                       lid_fit_type="外嵌め")
        lids = {"L": dict(width=840, length=740, thickness=5, fit_type="外嵌め")}
        pallet = PalletSpec(length=800, width=700, max_x_span=840, max_y_span=740)
        result = Palletizer({("A", "L"): spec}, pallet).run(
            "lid", [{"box_id": "A", "count": 1, "lid_id": "L"}])
        self.assertEqual(result.summary["overhang_mm"],
                         dict(left=20, right=20, front=20, back=20))
        self.assert_validated(result, {"A": spec}, lids)
        rejected = Palletizer({("A", "L"): spec}, replace(pallet, max_x_span=839)).run(
            "lid_limit", [{"box_id": "A", "count": 1, "lid_id": "L"}])
        self.assertEqual(rejected.boxes, [])

    def test_mixed_envelope_uses_inclusive_case_maxima(self) -> None:
        spec = replace(self.spec, width=500, length=500, height=100)
        specs = {"A": spec, "B": replace(spec, id="B")}
        engine = Palletizer(specs, PalletSpec(max_x_span=1000, max_y_span=1000, max_height=100))
        self.assertEqual(engine._determine_mixed_envelope(list(specs.values())),
                         dict(x_span=1000, y_span=1000))
        result = engine.run("mixed_limit", [{"box_id": key, "count": 2} for key in specs])
        self.assertEqual(len(result.boxes), 4)
        self.assertEqual(result.summary["bounding_box"]["x_span"], 1000)
        self.assertEqual(result.summary["bounding_box"]["y_span"], 1000)
        self.assert_validated(result, specs)

    def test_mixed_candidate_does_not_use_collision_tolerance_for_maximum(self) -> None:
        spec = replace(self.spec, width=500, length=500)
        engine = Palletizer({"A": spec})
        self.assertIsNotNone(engine._try_place_at(0, 0, spec, 0, [], 500, 500, 0, 0, []))
        for larger in (replace(spec, width=500.0001), replace(spec, length=500.0001)):
            self.assertIsNone(engine._try_place_at(0, 0, larger, 0, [], 500, 500, 0, 0, []))

    def test_empty_result_has_complete_invalid_summary(self) -> None:
        result = Palletizer({}).run("unknown", [{"box_id": "UNKNOWN", "count": 1}])
        self.assertFalse(result.summary["is_valid"])
        self.assertEqual(result.summary["total_boxes"], 0)
        self.assertEqual(result.to_dict()["unplaced_boxes_count"], 1)
        self.assertIn("bounding_box", result.summary)


if __name__ == "__main__":
    unittest.main()
