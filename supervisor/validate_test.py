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
    EPS,
    PalletizeValidator,
    get_footprint_bounds,
    load_box_db,
    load_lid_db,
    normalize_result_coordinates
)


class OverhangTests(unittest.TestCase):
    """pallet.max_overhang_x_mm / max_overhang_y_mm に基づくオーバーハング制約の検証。

    旧 max_small_edge_overhang_mm（335mm以下の辺・最下段のみ対象）ルールは廃止され、
    全段の箱・蓋結合外形を対象に、軸ごとの上限値（既定20mm、20mm自体は許容）で判定する。
    例外は、INPUT が単一荷姿種別（box_id + lid_id）のみで構成され、かつ回転後の箱本体
    寸法（蓋を除く）が670mm以上となる軸に限り適用される。
    """

    @classmethod
    def setUpClass(cls):
        cls.box_db = load_box_db()
        cls.lid_db = load_lid_db()
        cls.validator = PalletizeValidator(cls.box_db, cls.lid_db)
        cls.no_lid_id = next(lid_id for lid_id, lid in cls.lid_db.items() if lid.get("type") == "NONE")

    def validate_boxes(self, box_specs, overhang_x=20.0, overhang_y=20.0,
                        input_box_variants=None, extra_pallet=None):
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
            body_width = spec.get("body_width", body_width)
            body_length = spec.get("body_length", body_length)
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

        pallet = {
            "length": 1200.0,
            "width": 1000.0,
            "max_overhang_x_mm": overhang_x,
            "max_overhang_y_mm": overhang_y
        }
        if extra_pallet:
            pallet.update(extra_pallet)

        data = {
            "test_name": "overhang_test",
            "pallet": pallet,
            "boxes": boxes
        }
        if input_box_variants is not None:
            data["input_box_variants"] = input_box_variants

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
    def overhang_violations(result):
        return [v for v in result["violations"] if "オーバーハング違反" in v]

    def test_20mm_boundary_is_inclusive_and_above_is_rejected(self):
        at_limit = self.validate_boxes([{"box_id": "TP-331", "x": -20.0, "y": 300.0}])
        over_limit = self.validate_boxes([{"box_id": "TP-331", "x": -20.5, "y": 300.0}])

        self.assertEqual(self.overhang_violations(at_limit), [])
        self.assertEqual(len(self.overhang_violations(over_limit)), 1)

    def test_20_0001mm_exceeds_the_inclusive_20mm_boundary(self):
        # 20mm自体は許容(inclusive)だが、20.0001mmは浮動小数点丸め誤差を超える超過として拒否される
        result = self.validate_boxes([{"box_id": "TP-331", "x": -20.0001, "y": 300.0}])

        violations = self.overhang_violations(result)
        self.assertEqual(len(violations), 1)
        self.assertIn("X方向", violations[0])

    def test_overhang_is_checked_independently_per_axis(self):
        x_only = self.validate_boxes([{"box_id": "TP-331", "x": -25.0, "y": 300.0}])
        y_only = self.validate_boxes([{"box_id": "TP-331", "x": 400.0, "y": -25.0}])

        x_violations = self.overhang_violations(x_only)
        y_violations = self.overhang_violations(y_only)

        self.assertEqual(len(x_violations), 1)
        self.assertIn("X方向", x_violations[0])
        self.assertEqual(len(y_violations), 1)
        self.assertIn("Y方向", y_violations[0])

    def test_exception_applies_only_to_the_axis_with_670mm_rotated_body(self):
        # TP-362 (335mm x 670mm): rotation 0 -> X=335mm(<670, not exempt), Y=670mm(exempt)
        variants = [{"box_id": "TP-362", "lid_id": self.no_lid_id}]
        result = self.validate_boxes(
            [{"box_id": "TP-362", "x": -30.0, "y": -30.0}],
            input_box_variants=variants
        )

        violations = self.overhang_violations(result)
        self.assertEqual(len(violations), 1)
        self.assertIn("X方向", violations[0])

    def test_body_dimension_669_99mm_does_not_qualify_for_exception(self):
        variants = [{"box_id": "TP-362", "lid_id": self.no_lid_id}]
        result = self.validate_boxes(
            [{"box_id": "TP-362", "x": 400.0, "y": -30.0, "body_length": 669.99}],
            input_box_variants=variants
        )

        violations = self.overhang_violations(result)
        self.assertEqual(len(violations), 1)
        self.assertIn("Y方向", violations[0])

    def test_body_dimension_669_999mm_does_not_qualify_for_exception(self):
        variants = [{"box_id": "TP-362", "lid_id": self.no_lid_id}]
        result = self.validate_boxes(
            [{"box_id": "TP-362", "x": 400.0, "y": -30.0, "body_length": 669.999}],
            input_box_variants=variants
        )

        violations = self.overhang_violations(result)
        self.assertEqual(len(violations), 1)
        self.assertIn("Y方向", violations[0])

    def test_incomplete_input_metadata_does_not_enable_exception(self):
        valid = {"box_id": "TP-362", "lid_id": self.no_lid_id}
        for variants in ([valid, None], [valid, {}], [{"box_id": "TP-362"}]):
            with self.subTest(variants=variants):
                result = self.validate_boxes(
                    [{"box_id": "TP-362", "x": 400.0, "y": -30.0}],
                    input_box_variants=variants
                )
                self.assertEqual(len(self.overhang_violations(result)), 1)

    def test_exactly_670mm_qualifies_for_exception(self):
        variants = [{"box_id": "TP-362", "lid_id": self.no_lid_id}]
        result = self.validate_boxes(
            [{"box_id": "TP-362", "x": 400.0, "y": -30.0, "body_length": 670.0}],
            input_box_variants=variants
        )

        self.assertEqual(self.overhang_violations(result), [])

    def test_overhang_limit_applies_to_all_layers_not_only_bottom(self):
        variants = [{"box_id": "TP-362", "lid_id": self.no_lid_id}]
        result = self.validate_boxes([
            {"box_id": "TP-362", "x": 400.0, "y": 165.0},
            {"box_id": "TP-362", "x": -30.0, "y": -30.0, "z": 195.0}
        ], input_box_variants=variants)

        violations = self.overhang_violations(result)
        self.assertEqual(len(violations), 1)
        self.assertIn("X方向", violations[0])

    def test_mixed_input_variants_disallow_exception_even_if_only_one_type_is_placed(self):
        variants = [
            {"box_id": "TP-362", "lid_id": self.no_lid_id},
            {"box_id": "TP-331", "lid_id": self.no_lid_id}
        ]
        result = self.validate_boxes(
            [{"box_id": "TP-362", "x": 400.0, "y": -30.0}],
            input_box_variants=variants
        )

        violations = self.overhang_violations(result)
        self.assertEqual(len(violations), 1)
        self.assertIn("Y方向", violations[0])

    def test_missing_input_box_variants_disallows_exception(self):
        result = self.validate_boxes([{"box_id": "TP-362", "x": 400.0, "y": -30.0}])

        violations = self.overhang_violations(result)
        self.assertEqual(len(violations), 1)
        self.assertIn("Y方向", violations[0])

    def test_external_lid_combined_footprint_is_used_for_overhang(self):
        # 箱本体のみなら上限内(16mm)だが、蓋込み外形では超過(20.5mm)する
        result = self.validate_boxes([{
            "box_id": "TP-331", "x": -16.0, "y": 300.0,
            "lid_id": "サンボックス330フタ"
        }])

        violations = self.overhang_violations(result)
        self.assertEqual(len(violations), 1)
        self.assertIn("X方向", violations[0])

    def test_overhang_limit_is_configurable_per_axis(self):
        result = self.validate_boxes(
            [{"box_id": "TP-331", "x": -16.0, "y": 300.0}],
            overhang_x=15.0
        )

        violations = self.overhang_violations(result)
        self.assertEqual(len(violations), 1)
        self.assertIn("X方向", violations[0])

    def test_old_overhang_key_is_reported_as_invalid(self):
        result = self.validate_boxes(
            [{"box_id": "TP-331", "x": 432.5, "y": 332.5}],
            extra_pallet={"max_small_edge_overhang_mm": 30.0}
        )

        self.assertEqual(self.overhang_violations(result), [])
        self.assertTrue(any(
            "max_small_edge_overhang_mm" in v for v in result["violations"]
        ))

    def test_invalid_overhang_limit_value_is_reported_and_defaults_are_used(self):
        result = self.validate_boxes(
            [{"box_id": "TP-331", "x": -16.0, "y": 300.0}],
            extra_pallet={"max_overhang_x_mm": -5.0}
        )

        self.assertTrue(any(
            "max_overhang_x_mm" in v for v in result["violations"]
        ))
        # 既定値20mmにフォールバックするため、16mmのオーバーハングは違反にならない
        self.assertEqual(self.overhang_violations(result), [])

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

    def make_engine_and_pool(self, max_overhang_y_mm=25.0):
        """独立行探索テスト専用: 承認済み入力コーパス(outer_cover_test.json)自体は変更せず、
        このテストローカルの PalletSpec インスタンスにのみ Y方向オーバーハング許容を
        25mm 設定し、行探索の組み合わせ回帰意図を維持する（max_overhang_y_mm=None なら
        pallet.json の既定値(未設定時 PalletSpec既定の20mm)をそのまま使用する）。
        """
        pallet_spec = PalletSpec.from_dict(self.testcase["pallet"])
        if max_overhang_y_mm is not None:
            pallet_spec.max_overhang_y_mm = max_overhang_y_mm
        engine = Palletizer(
            {box_id: BoxSpec.from_dict(data) for box_id, data in self.box_db.items()},
            pallet_spec
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
        layer_pool = [box for box in pool if box.height + box.lid_thickness == 115.5]
        candidates = engine._mixed_layer_candidates(layer_pool, 0.0, 0, [], envelope)
        proposed = [boxes for boxes, _ in candidates
                    if Counter(box.box_id for box in boxes) == {"TP-341": 4, "TP-331": 3}]
        self.assertTrue(proposed)
        for boxes in proposed:
            self.assertAlmostEqual(max(box.max_x for box in boxes)
                                   - min(box.footprint_min_x for box in boxes), 1032.0)
            self.assertAlmostEqual(max(box.max_y for box in boxes)
                                   - min(box.footprint_min_y for box in boxes), 1034.0)

    def test_default_20mm_overhang_is_required_for_widest_mixed_combination(self):
        """pallet.max_overhang_y_mm の既定値(20mm)が、この行探索の組み合わせ候補を
        実際に左右していることを確認する（既定20mmでは許容されるが、0mmまで絞ると
        同じ幅の組み合わせが候補から排除される=既定値が単なる飾りでないことの回帰確認）。
        """
        engine, pool = self.make_engine_and_pool(max_overhang_y_mm=None)
        layer_pool = [box for box in pool if box.height + box.lid_thickness == 115.5]

        # ここでは行探索テスト専用の25mmローカルオーバーライドではなく、
        # PalletSpecの既定値(20mm)相当のエンベロープで検証する
        engine.pallet.max_overhang_y_mm = 20.0
        default_envelope = engine._determine_mixed_envelope(pool)
        self.assertAlmostEqual(default_envelope["y_span"], 1040.0)
        default_candidates = engine._mixed_layer_candidates(layer_pool, 0.0, 0, [], default_envelope)
        default_spans = [
            max(box.max_y for box in boxes) - min(box.footprint_min_y for box in boxes)
            for boxes, _ in default_candidates
        ]
        self.assertTrue(any(span > 1034.0 for span in default_spans))
        self.assertTrue(all(span <= default_envelope["y_span"] + EPS for span in default_spans))

        # オーバーハングを0mmまで絞ると、同じ幅の組み合わせ候補は生成されなくなる
        engine.pallet.max_overhang_y_mm = 0.0
        strict_envelope = engine._determine_mixed_envelope(pool)
        self.assertAlmostEqual(strict_envelope["y_span"], 1000.0)
        strict_candidates = engine._mixed_layer_candidates(layer_pool, 0.0, 0, [], strict_envelope)
        strict_spans = [
            max(box.max_y for box in boxes) - min(box.footprint_min_y for box in boxes)
            for boxes, _ in strict_candidates
        ]
        self.assertTrue(all(span <= strict_envelope["y_span"] + EPS for span in strict_spans))
        self.assertFalse(any(span > 1034.0 for span in strict_spans))

    def test_candidate_limit_inventory_and_input_are_preserved(self):
        engine, pool = self.make_engine_and_pool()
        layer_pool = [box for box in pool if box.height + box.lid_thickness == 115.5]
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
        layer_pool = [box for box in pool if box.height + box.lid_thickness == 115.5]
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