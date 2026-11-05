"""Upper pallet support geometry and engine/validator integration tests."""

from dataclasses import asdict
import json
from pathlib import Path
import unittest
from unittest.mock import mock_open, patch

from algorithm_programmer.models import BoxSpec, PalletSpec, PlacedBox
from algorithm_programmer.palletizer import Palletizer
from constraints.top_support import TopSurface, evaluate_top_support, required_support_points
from supervisor.validate import PalletizeValidator


def surface(rect, top=100.0, box_id="OTHER", order=1, bottom=0.0, points=None):
    return TopSurface(order, box_id, rect, bottom, top,
                      required_support_points(box_id, {}) if points is None else points)


def four_corners(box_id="OTHER", delta=0.0):
    return [surface(rect, 100.0 - (delta if i == 0 else 0.0), box_id, i + 1)
            for i, rect in enumerate(((200, 100, 400, 300), (800, 100, 1000, 300),
                                      (200, 700, 400, 900), (800, 700, 1000, 900)))]


class TopSupportTest(unittest.TestCase):
    def check(self, surfaces):
        return evaluate_top_support(surfaces, 1200.0, 1000.0, 800.0, 800.0)

    def test_hollow_four_corners_allowed(self):
        result = self.check(four_corners())
        self.assertTrue(result["is_valid"])
        self.assertFalse(result["center_supported"])
        self.assertEqual(result["corners_supported"], [True] * 4)
        self.assertFalse(result["long_edge_exception"])
        self.assertLess(max(result["opposing_edge_lengths_mm"].values()), 670)

    def test_tp331_needs_center_including_mixed_and_alias(self):
        for box_id in ("TP331", "TP-331"):
            boxes = four_corners()
            boxes[0] = surface(boxes[0].bounds, box_id=box_id)
            self.assertFalse(self.check(boxes)["is_valid"])
            boxes.append(surface((500, 400, 700, 600), order=5))
            self.assertTrue(self.check(boxes)["is_valid"])

    def test_lower_center_cannot_supply_fifth_point(self):
        boxes = four_corners("TP331")
        boxes.append(surface((500, 400, 700, 600), top=96.99, order=5))
        self.assertFalse(self.check(boxes)["center_supported"])
        boxes[-1] = surface((500, 400, 700, 600), top=97.0, order=5)
        self.assertTrue(self.check(boxes)["is_valid"])

    def test_height_boundary_and_single_high_box(self):
        self.assertTrue(self.check(four_corners(delta=3.0))["is_valid"])
        self.assertFalse(self.check(four_corners(delta=3.01))["is_valid"])
        boxes = four_corners() + [surface((500, 400, 700, 600), top=104.0)]
        self.assertFalse(self.check(boxes)["is_valid"])

    def test_continuous_670_exception(self):
        # The two low corners define the load envelope but cannot support the top pallet.
        lower = [surface((100, 100, 200, 200), top=50),
                 surface((1000, 800, 1100, 900), top=50)]
        boxes = lower + [surface((265, 165, 600, 835)),
                         surface((600, 165, 935, 835))]
        result = self.check(boxes)
        self.assertTrue(result["is_valid"])
        self.assertTrue(result["long_edge_exception"])
        self.assertEqual(result["continuous_support_x_mm"], 670.0)
        self.assertEqual(result["opposing_edge_lengths_mm"]["front"], 670.0)
        self.assertEqual(result["opposing_edge_lengths_mm"]["back"], 670.0)
        self.assertEqual(result["opposing_support_axis"], "XY")
        self.assertEqual(result["opposing_edge_lengths_mm"]["left"], 670.0)
        self.assertEqual(result["opposing_edge_lengths_mm"]["right"], 670.0)
        boxes[-1] = surface((600, 165, 934.99, 835))
        self.assertFalse(self.check(boxes)["is_valid"])
        boxes[-1] = surface((600.01, 165, 935.01, 835))
        self.assertFalse(self.check(boxes)["is_valid"])

    def test_long_support_does_not_allow_tipping_or_boundary_center(self):
        for rect in ((0, 100, 670, 300), (0, 100, 670, 500)):
            result = self.check([surface(rect)])
            self.assertFalse(result["is_valid"])
            self.assertFalse(result["balanced"])

    def test_occluded_lower_surface_is_not_support(self):
        for bottom in (90, 99):
            boxes = [surface((200, 100, 1000, 900), top=99, box_id="TP331"),
                     surface((200, 100, 1000, 900), bottom=bottom, top=100, order=2)]
            result = self.check(boxes)
            self.assertEqual([b["order"] for b in result["support_boxes"]], [2])
            self.assertEqual(result["required_points"], 4)

    def test_vertical_continuous_exception(self):
        boxes = [surface((100, 100, 200, 200), top=50),
                 surface((1000, 800, 1100, 900), top=50),
                 surface((265, 165, 935, 500)), surface((265, 500, 935, 835))]
        result = self.check(boxes)
        self.assertTrue(result["is_valid"])
        self.assertTrue(result["long_edge_exception"])
        self.assertEqual(result["continuous_support_y_mm"], 670)
        self.assertEqual(result["opposing_support_axis"], "XY")

    def test_short_sides_need_continuous_670_in_both_orientations(self):
        lower = [surface((100, 100, 200, 200), top=50),
                 surface((1000, 800, 1100, 900), top=50)]
        for width, length in ((1000, 669.99), (669.99, 800), (1000, 200)):
            with self.subTest(width=width, length=length):
                rect = (600 - width / 2, 500 - length / 2,
                        600 + width / 2, 500 + length / 2)
                result = self.check(lower + [surface(rect)])
                self.assertTrue(result["balanced"])
                self.assertFalse(result["is_valid"])
                self.assertFalse(result["long_edge_exception"])
                self.assertTrue(any("short sides" in v for v in result["violations"]))

    def test_contact_span_does_not_replace_short_side_continuity(self):
        lower = [surface((100, 100, 200, 200), top=50),
                 surface((1000, 800, 1100, 900), top=50)]
        result = self.check(lower + [surface((265, 165, 935, 400)),
                                    surface((265, 600, 935, 835))])
        self.assertEqual(result["opposing_edge_lengths_mm"]["front"], 670)
        self.assertEqual(result["opposing_edge_lengths_mm"]["back"], 670)
        self.assertEqual(result["opposing_edge_lengths_mm"]["left"], 235)
        self.assertTrue(result["balanced"])
        self.assertFalse(result["is_valid"])

    def test_opposing_edges_need_670_on_both_sides(self):
        lower = [surface((100, 100, 200, 200), top=50),
                 surface((1000, 800, 1100, 900), top=50)]
        boxes = lower + [surface((265, 165, 935, 500)), surface((265, 500, 934.99, 835))]
        result = self.check(boxes)
        self.assertTrue(result["balanced"])
        self.assertFalse(result["is_valid"])
        self.assertFalse(result["long_edge_exception"])
        self.assertEqual(result["opposing_edge_lengths_mm"]["front"], 670)
        self.assertAlmostEqual(result["opposing_edge_lengths_mm"]["back"], 669.99)

    def test_opposing_edges_do_not_sum_across_gaps(self):
        lower = [surface((100, 100, 200, 200), top=50),
                 surface((1000, 800, 1100, 900), top=50)]
        boxes = lower + [surface((265, 200, 935, 300)),
                         surface((265, 700, 600, 800)), surface((600.01, 700, 935.01, 800))]
        result = self.check(boxes)
        self.assertFalse(result["is_valid"])
        self.assertAlmostEqual(result["opposing_edge_lengths_mm"]["back"], 335)

    def test_interior_long_line_does_not_replace_short_outer_edges(self):
        boxes = [surface((200, 100, 400, 900)),
                 surface((400, 400, 1000, 600))]
        result = self.check(boxes)
        self.assertTrue(result["balanced"])
        self.assertEqual(result["continuous_support_x_mm"], 800)
        self.assertEqual(result["opposing_edge_lengths_mm"]["front"], 200)
        self.assertEqual(result["opposing_edge_lengths_mm"]["right"], 200)
        self.assertFalse(result["is_valid"])

    def test_previously_accepted_asymmetric_tops_are_rejected(self):
        shapes = (
            ((97.5, -2.5, 432.5, 500), (432.5, -2.5, 767.5, 500),
             (767.5, -2.5, 1102.5, 500), (97.5, 500, 432.5, 1002.5)),
            ((73.5, -12, 424.5, 500), (424.5, -12, 775.5, 500),
             (775.5, -12, 1126.5, 500), (73.5, 500, 424.5, 1012)),
            ((97.5, -2.5, 432.5, 332.5), (432.5, -2.5, 767.5, 332.5),
             (767.5, -2.5, 1102.5, 332.5), (97.5, 332.5, 432.5, 667.5),
             (97.5, 667.5, 432.5, 1002.5)),
            ((181.25, -2.5, 516.25, 500), (516.25, -2.5, 1018.75, 332.5),
             (516.25, 332.5, 1018.75, 667.5), (181.25, 500, 516.25, 1002.5)),
        )
        for shape in shapes:
            with self.subTest(shape=shape):
                result = self.check([surface(rect) for rect in shape])
                self.assertTrue(result["balanced"])
                self.assertFalse(result["is_valid"])

    def test_opposing_lengths_are_clipped_to_pallet(self):
        lower = [surface((0, 0, 100, 100), top=50),
                 surface((1100, 900, 1200, 1000), top=50)]
        boxes = lower + [surface((-100, 100, 650, 200)), surface((-100, 800, 650, 900))]
        result = self.check(boxes)
        self.assertEqual(result["opposing_edge_lengths_mm"]["front"], 650)
        self.assertFalse(result["is_valid"])

    def test_aisin_four_four_three_top_fails_new_support_rule(self):
        rectangles = ((-70, -2.5, 600, 500), (600, -2.5, 1270, 500),
                      (-70, 500, 600, 1002.5), (600, 500, 1270, 1002.5))
        boxes = [surface(r, top=780) for r in rectangles]
        boxes += [surface(r, top=1165, bottom=770) for r in rectangles[:3]]
        result = self.check(boxes)
        self.assertTrue(result["balanced"])
        self.assertEqual(result["opposing_edge_lengths_mm"],
                         {"front": 1200, "back": 600, "left": 1000, "right": 500})
        self.assertFalse(result["is_valid"])

    def test_exception_does_not_waive_fifth_point(self):
        boxes = [surface((100, 100, 200, 200), top=50),
                 surface((1000, 800, 1100, 900), top=50),
                 surface((265, 165, 465, 835), box_id="TP331"),
                 surface((735, 165, 935, 835)),
                 surface((465, 165, 735, 365)),
                 surface((465, 635, 735, 835))]
        result = self.check(boxes)
        self.assertTrue(result["balanced"])
        self.assertTrue(result["long_edge_exception"])
        self.assertFalse(result["is_valid"])
        self.assertFalse(result["center_supported"])

    def test_empty_support_has_complete_failure_report(self):
        result = self.check([])
        self.assertFalse(result["is_valid"])
        self.assertFalse(result["balanced"])
        self.assertEqual(result["continuous_support_x_mm"], 0)

    def test_lid_contact_and_upper_coordinates(self):
        spec = BoxSpec("OTHER", "OTHER", "NON_TP", 300, 300, 100, 0, 0)
        box = PlacedBox(1, spec.id, 450, 350, 0, 300, 300, 105, 0, 0, 90,
                        lid_id="LID", lid_thickness=5, lid_width=700,
                        lid_length=400, lid_fit_type="外嵌め")
        engine = Palletizer({spec.id: spec})
        expected = engine.calculate_summary([box])["top_support"]
        self.assertEqual(expected["support_regions"], [(250, 300, 950, 700)])
        data = {"coordinate_reference": "combined_footprint_min_xy_top_z",
                "boxes": [box.to_dict()], "pallet": asdict(engine.pallet)}
        validator = PalletizeValidator({spec.id: asdict(spec)}, {
            "LID": {"width": 400, "length": 700, "thickness": 5, "fit_type": "外嵌め"}})
        with patch("builtins.open", mock_open(read_data=json.dumps(data))):
            actual = validator.validate_case("lid.json")
        self.assertEqual(actual["top_support"], expected)

    def test_leveling_keeps_valid_missing_corner_exception(self):
        spec = BoxSpec("OTHER", "OTHER", "TP", 200, 200, 100, 0, 0)
        engine = Palletizer({spec.id: spec}, PalletSpec(max_x_span=800, max_y_span=800))
        boxes = [PlacedBox(1, spec.id, 100, 100, 0, 200, 200, 50, 0, 0, 0),
                 PlacedBox(2, spec.id, 900, 700, 0, 200, 200, 50, 0, 0, 0),
                 PlacedBox(3, spec.id, 265, 165, 0, 670, 670, 100, 0, 0, 0)]
        self.assertTrue(engine._top_support(boxes)["long_edge_exception"])
        self.assertTrue(engine._top_support(boxes)["is_valid"])
        kept, unplaced = engine.level_top_four_corners(boxes, [])
        self.assertIs(kept, boxes)
        self.assertEqual(unplaced, [])

    def test_pallet_intersection_not_overhanging_length(self):
        boxes = four_corners()
        boxes.append(surface((-800, 400, -100, 600), top=200))
        result = self.check(boxes)
        self.assertEqual(result["support_height"], 100)
        self.assertLess(result["continuous_support_x_mm"], 670)

    def test_configurable_rule_and_invalid_values(self):
        self.assertEqual(required_support_points("OTHER", {"top_support_points": 5}), 5)
        self.assertEqual(required_support_points("TP331", {"top_support_points": 4}), 4)
        for value in (0, 6, True, "5", None):
            with self.assertRaises(ValueError):
                required_support_points("OTHER", {"top_support_points": value})

    def test_rotation_and_input_order_invariance(self):
        boxes = four_corners()
        self.assertEqual(self.check(boxes)["support_polygon"],
                         self.check(list(reversed(boxes)))["support_polygon"])
        swapped = [surface((s.bounds[1], s.bounds[0], s.bounds[3], s.bounds[2]),
                           s.top, s.box_id, s.order) for s in boxes]
        self.assertTrue(evaluate_top_support(swapped, 1000, 1200, 800, 800)["is_valid"])

    def test_engine_and_validator_recompute_both_coordinate_formats(self):
        for box_id in ("OTHER", "TP331", "TP-331"):
            spec = BoxSpec(box_id, box_id, "TP", 200, 200, 100, 0, 0)
            engine = Palletizer({box_id: spec}, PalletSpec(max_x_span=800, max_y_span=800))
            boxes = [PlacedBox(s.order, box_id, s.bounds[0], s.bounds[1], 0,
                               200, 200, 100, 0, 0, 0) for s in four_corners(box_id)]
            report = engine.calculate_summary(boxes)
            self.assertEqual(report["top_support"]["is_valid"], box_id == "OTHER")
            validator = PalletizeValidator({box_id: asdict(spec)}, {})
            for current in (True, False):
                data = {"test_name": "top", "pallet": asdict(engine.pallet),
                        "boxes": [b.to_dict() for b in boxes],
                        "summary": {"is_valid": True, "top_support": {"is_valid": True}}}
                if current:
                    data["coordinate_reference"] = "combined_footprint_min_xy_top_z"
                else:
                    for b in data["boxes"]:
                        b["position"]["z"] -= b["dimensions"]["height"]
                with patch("builtins.open", mock_open(read_data=json.dumps(data))):
                    independent = validator.validate_case("top.json")
                self.assertEqual(independent["top_support"], report["top_support"])

    def test_single_tp331_selection_avoids_hollow_center(self):
        spec = BoxSpec("TP331", "TP331", "TP", 335, 335, 102.5, 10, 16)
        engine = Palletizer({spec.id: spec})
        result = engine.run("tp331", [{"box_id": spec.id, "count": 9}])
        self.assertTrue(result.summary["is_valid"])
        self.assertTrue(result.summary["top_support"]["center_supported"])

    def test_leveling_preserves_valid_exception_and_finds_lower_support(self):
        spec = BoxSpec("OTHER", "OTHER", "TP", 200, 200, 100, 0, 0)
        engine = Palletizer({spec.id: spec}, PalletSpec(max_x_span=800, max_y_span=800))
        boxes = [PlacedBox(s.order, spec.id, s.bounds[0], s.bounds[1], 0,
                           200, 200, 100, 0, 0, 0) for s in four_corners()]
        tall = PlacedBox(5, spec.id, 500, 400, 100, 200, 200, 100, 0, 0, 0)
        kept, unplaced = engine.level_top_four_corners(boxes + [tall], [])
        self.assertEqual(kept, boxes)
        self.assertEqual(unplaced[0]["count"], 1)

    def test_area_uses_configured_limits_and_includes_internal_gaps(self):
        boxes = four_corners()
        smaller = evaluate_top_support(boxes, 1200, 1000, 800, 800)
        larger = evaluate_top_support(boxes, 1200, 1000, 1360, 1100)
        self.assertEqual(smaller["support_polygon_area_mm2"], 640000)
        self.assertEqual(smaller["support_area_ratio"], 1)
        self.assertTrue(smaller["is_valid"])
        self.assertFalse(larger["is_valid"])
        self.assertAlmostEqual(larger["support_area_ratio"], 640000 / (1360 * 1100))

    def test_area_65_percent_inclusive_boundary(self):
        for height, valid in ((649.99, False), (650, True), (650.01, True)):
            with self.subTest(height=height):
                y0, y1 = 500 - height / 2, 500 + height / 2
                boxes = [surface(r, order=i + 1) for i, r in enumerate(
                    ((100, y0, 250, y0 + 150), (950, y0, 1100, y0 + 150),
                     (100, y1 - 150, 250, y1), (950, y1 - 150, 1100, y1)))]
                result = evaluate_top_support(boxes, 1200, 1000, 1000, 1000)
                self.assertEqual(result["is_valid"], valid)
                self.assertAlmostEqual(result["support_area_ratio"], height / 1000)

    def test_centroid_quarter_limit_is_exclusive_in_both_axes(self):
        for axis in (0, 1):
            for distance, valid in ((249.99, True), (250, False), (250.01, False)):
                with self.subTest(axis=axis, distance=distance):
                    center = [1000, 1000]
                    center[axis] += distance
                    result = evaluate_top_support(
                        [surface((center[0] - 400, center[1] - 500,
                                  center[0] + 400, center[1] + 500))],
                        2000, 2000, 1000, 1000)
                    self.assertTrue(result["balanced"])
                    self.assertAlmostEqual(result["support_area_ratio"], 0.8)
                    self.assertEqual(result["is_valid"], valid)

    def test_centroid_is_area_weighted_not_bounding_box_center(self):
        result = evaluate_top_support([surface((0, 0, 1000, 200)),
                                       surface((0, 200, 200, 1000))],
                                      1000, 1000, 1000, 1000)
        self.assertEqual(result["support_polygon_area_mm2"], 680000)
        for value in result["support_centroid"]:
            self.assertAlmostEqual(value, 390.19607843137254)

    def test_multicorner_requires_short_side_670_even_with_sufficient_area(self):
        for short_side, valid in ((669.99, False), (670, True)):
            result = evaluate_top_support(
                [surface((100, 500 - short_side / 2, 1100, 500 + short_side / 2))],
                1200, 1000, 1000, 1000)
            self.assertEqual(result["corners_supported"], [True] * 4)
            self.assertGreater(result["support_area_ratio"], 0.65)
            self.assertEqual(result["multi_corner_boxes"][0]["corner_count"], 4)
            self.assertEqual(result["is_valid"], valid)

    def test_occluded_box_does_not_count_as_multicorner_support(self):
        boxes = four_corners() + [surface((200, 100, 1000, 900), top=99)]
        result = self.check(boxes)
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["multi_corner_boxes"], [])


class RevisedRealLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.raw = json.loads((cls.root / "box_research" / "box_db.json").read_text(encoding="utf-8"))
        cls.lids = json.loads((cls.root / "box_research" / "lid_db.json").read_text(encoding="utf-8"))
        cls.db = {key: BoxSpec.from_dict(value) for key, value in cls.raw.items()}

    def run_case(self, name):
        case = json.loads((self.root / "test_programmer" / "test_cases" / (name + ".json")).read_text(encoding="utf-8"))
        engine = Palletizer(self.db, PalletSpec.from_dict(case["pallet"]))
        result = engine.run(name, case["box_list"], self.lids)
        validator = PalletizeValidator(self.raw, self.lids)
        with patch("builtins.open", mock_open(read_data=json.dumps(result.to_dict()))):
            validation = validator.validate_case(name + ".json")
        self.assertEqual(validation["violations"], [])
        self.assertTrue(result.summary["is_valid"])
        self.assertEqual(result.input_boxes_count,
                         len(result.boxes) + sum(b["count"] for b in result.unplaced_boxes))
        for b in result.boxes:
            self.assertLessEqual(b.top_z, engine.pallet.max_height)
        return result, engine

    def test_aisin7_and_othics9_have_requested_partial_top(self):
        for name, counts in (("aisin_7", [6, 6, 5]), ("othics_9", [6, 6, 6, 6, 6, 4])):
            with self.subTest(name=name):
                result, _ = self.run_case(name)
                layers = [[b for b in result.boxes if b.layer_index == i] for i in range(len(counts))]
                self.assertEqual([len(layer) for layer in layers], counts)
                self.assertEqual(result.unplaced_boxes, [])
                pattern = {(b.x, b.y, b.rotation) for b in layers[0]}
                for layer in layers[1:-1]:
                    self.assertEqual({(b.x, b.y, b.rotation) for b in layer}, pattern)
                self.assertTrue({(b.x, b.y, b.rotation) for b in layers[-1]}.issubset(pattern))

    def test_aisin_three_of_four_top_is_not_silently_allowed(self):
        result, _ = self.run_case("aisin")
        self.assertEqual(len(result.boxes), 9)
        self.assertEqual(sum(b["count"] for b in result.unplaced_boxes), 2)

    def test_short_y_split_candidates_are_centered(self):
        for name, per_layer in (("aisin_10", 4), ("aisin_9", 4), ("arresuthi_2", 3)):
            with self.subTest(name=name):
                result, engine = self.run_case(name)
                spec = self.db[result.boxes[0].box_id]
                patterns = engine._generate_single_2d_patterns(spec.width, spec.length)
                split = next(p for p in patterns if p["type"] == "split_x" and
                             len(p["boxes"]) == per_layer)
                base = engine._single_pattern_boxes(spec, split)
                engine._align_pallet_bounds(base)
                columns = [b for b in base if b.rotation == 0]
                self.assertTrue(columns)
                for box in columns:
                    self.assertAlmostEqual((box.footprint_min_y + box.max_y) / 2,
                                           engine.pallet.width / 2)
                self.assertEqual(len({(b.x, b.y) for b in columns}), 1)
                self.assertTrue(engine._top_support(base)["is_valid"])
                if name in ("aisin_10", "aisin_9"):
                    self.assertEqual(result.summary["top_support"]["corners_supported"], [True] * 4)

    def test_short_x_rows_are_centered_where_split_layout_is_selected(self):
        for name in ("nok_2", "othics_6", "othics_7"):
            with self.subTest(name=name):
                result, engine = self.run_case(name)
                for index in {b.layer_index for b in result.boxes}:
                    layer = [b for b in result.boxes if b.layer_index == index]
                    for rotation in (0, 90):
                        row = [b for b in layer if b.rotation == rotation]
                        if row:
                            self.assertAlmostEqual(
                                (min(b.footprint_min_x for b in row) + max(b.max_x for b in row)) / 2,
                                engine.pallet.length / 2)

    def test_nittan_long_side_is_x(self):
        result, _ = self.run_case("nittan_2")
        bounds = result.summary["bounding_box"]
        self.assertEqual((bounds["x_span"], bounds["y_span"]), (1107, 846))

    def test_othics4_uses_corners_and_center(self):
        result, _ = self.run_case("othics_4")
        support = result.summary["top_support"]
        self.assertEqual(len(result.boxes), 5)
        self.assertEqual(result.summary["total_layers"], 1)
        self.assertEqual(support["corners_supported"], [True] * 4)
        self.assertTrue(support["center_supported"])
        self.assertFalse(support["long_edge_exception"])

    def test_revised_weak_top_cases_meet_opposed_edges_or_four_corners(self):
        for name in ("aisin_4", "othics_2", "roki"):
            with self.subTest(name=name):
                result, _ = self.run_case(name)
                support = result.summary["top_support"]
                edges = support["opposing_edge_lengths_mm"]
                self.assertTrue(all(support["corners_supported"]) or
                                min(edges.values()) >= 670)

    def test_aisin3_prefers_equal_layers_before_envelope_occupancy(self):
        result, _ = self.run_case("aisin_3")
        self.assertEqual([sum(b.layer_index == i for b in result.boxes) for i in (0, 1)], [6, 6])
        self.assertEqual(max(b.top_z for b in result.boxes), 410)
        self.assertEqual(result.summary["top_support"]["corners_supported"], [True] * 4)

    def test_aisin5_has_no_case_specific_unplacement_rule(self):
        result, _ = self.run_case("aisin_5")
        self.assertEqual(len(result.boxes), 10)
        self.assertEqual(result.unplaced_boxes, [])
        self.assertEqual(result.summary["top_support"]["corners_supported"], [True] * 4)
        self.assertTrue(result.summary["top_support"]["center_supported"])

    def test_aisin4_top_uses_four_lower_corner_columns(self):
        result, _ = self.run_case("aisin_4")
        self.assertEqual(len(result.boxes), 28)
        top = [b for b in result.boxes if b.layer_index == 4]
        self.assertEqual([b.supported_by for b in top], [[19], [21], [22], [24]])
        self.assertEqual(result.summary["top_support"]["corners_supported"], [True] * 4)

    def test_arresuthi2_stops_at_nine_under_configured_area_rule(self):
        result, _ = self.run_case("arresuthi_2")
        self.assertEqual([sum(b.layer_index == i for b in result.boxes) for i in range(3)],
                         [3, 3, 3])
        self.assertEqual(sum(b["count"] for b in result.unplaced_boxes), 2)
        self.assertGreaterEqual(result.summary["top_support"]["support_area_ratio"], 0.65)

    def test_narrow_multicorner_real_layouts_are_replaced(self):
        for name, per_layer, layers, missing in (("nok_2", 4, 7, 3), ("othics_3", 6, 2, 3)):
            with self.subTest(name=name):
                result, _ = self.run_case(name)
                self.assertEqual([sum(b.layer_index == i for b in result.boxes)
                                  for i in range(layers)], [per_layer] * layers)
                self.assertEqual(sum(b["count"] for b in result.unplaced_boxes), missing)
                self.assertGreaterEqual(result.summary["top_support"]["support_area_ratio"], 0.65)

    def test_corner_candidates_preserve_existing_candidates_and_inventory(self):
        spec = BoxSpec("COLUMN", "COLUMN", "NON_TP", 335, 502.5, 200, 10, 0)
        engine = Palletizer({spec.id: spec}, PalletSpec(max_x_span=1005, max_y_span=1005))
        pattern = next(p for p in engine._generate_single_2d_patterns(spec.width, spec.length)
                       if len(p["boxes"]) == 6 and all(b["rot"] == 0 for b in p["boxes"]))
        lower = engine._single_pattern_boxes(spec, pattern)
        envelope = {"x_span": 1005, "y_span": 1005}
        pool = [spec] * 4
        with patch.object(engine, "_corner_column_candidates", return_value=[]):
            old = engine._mixed_layer_candidates(pool, 190, 1, lower, envelope)
        new = engine._mixed_layer_candidates(pool, 190, 1, lower, envelope)
        signature = lambda layer: [(b.box_id, b.x, b.y, b.rotation) for b in layer]
        self.assertEqual([signature(layer) for layer, _ in old],
                         [signature(layer) for layer, _ in new[:len(old)]])
        extra = new[len(old):]
        self.assertTrue(extra)
        for layer, remaining in extra:
            self.assertEqual(len(layer) + len(remaining), len(pool))
            self.assertEqual(len({(b.x, b.y) for b in layer}), len(layer))
            self.assertTrue(engine._top_support(lower + layer, centered=True)["is_valid"])
            for b in layer:
                self.assertTrue(engine._column_stack_is_allowed(spec, b, lower))

    def test_validator_rejects_stale_success_summary_with_configured_area_shortfall(self):
        result, engine = self.run_case("arresuthi_2")
        data = result.to_dict()
        data["pallet"]["max_x_span"] = 2000
        data["pallet"]["max_y_span"] = 2000
        self.assertTrue(data["summary"]["top_support"]["is_valid"])
        validator = PalletizeValidator(self.raw, self.lids)
        with patch("builtins.open", mock_open(read_data=json.dumps(data))):
            report = validator.validate_case("stale.json")
        self.assertFalse(report["is_pass"])
        self.assertTrue(any("area ratio" in v for v in report["violations"]))
        self.assertEqual(report["top_support"]["reference_max_x_span_mm"], 2000)


if __name__ == "__main__":
    unittest.main()
