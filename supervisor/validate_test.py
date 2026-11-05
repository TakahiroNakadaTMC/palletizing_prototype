import json
import math
import os
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from unittest.mock import mock_open, patch

from algorithm_programmer.models import BoxSpec, PalletSpec
from algorithm_programmer.palletizer import Palletizer
from supervisor.validate import (
    EPS,
    PalletizeValidator,
    get_footprint_bounds,
    load_box_db,
    load_lid_db,
    normalize_result_coordinates,
    resolve_pallet_dims,
)


class PalletCaseBuilderMixin:
    """結果JSONを組み立て、一時ファイル経由で validate_case を呼び出す共通ヘルパー。"""

    @classmethod
    def setUpClass(cls):
        cls.box_db = load_box_db()
        cls.lid_db = load_lid_db()
        cls.validator = PalletizeValidator(cls.box_db, cls.lid_db)
        cls.no_lid_id = next(lid_id for lid_id, lid in cls.lid_db.items() if lid.get("type") == "NONE")

    def build_box(self, spec):
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
        return {
            "order": spec.get("order", 1),
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
        }

    def validate_boxes(self, box_specs, pallet=None, extra_pallet=None, omit_pallet=False):
        boxes = []
        for order, spec in enumerate(box_specs, start=1):
            spec = dict(spec)
            spec.setdefault("order", order)
            boxes.append(self.build_box(spec))

        data = {"test_name": "case", "boxes": boxes}
        if not omit_pallet:
            pallet_data = dict(pallet) if pallet is not None else {"length": 1200.0, "width": 1000.0}
            if extra_pallet:
                pallet_data.update(extra_pallet)
            data["pallet"] = pallet_data

        path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as output:
                json.dump(data, output)
                path = output.name
            return self.validator.validate_case(path)
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

class PalletDimensionValidationTests(PalletCaseBuilderMixin, unittest.TestCase):
    """新パレット6項目 (length/width/height/max_x_span/max_y_span/max_height) の検証。

    下限(旧800mm)・軸別オーバーハング上限・670mm例外・旧 max_small_edge_overhang_mm は
    すべて廃止された。各上限は inclusive (境界値そのものは合格)。
    """

    def test_resolve_pallet_dims_uses_six_defaults_when_omitted(self):
        violations = []
        resolved = resolve_pallet_dims({}, violations)
        self.assertEqual(violations, [])
        self.assertEqual(resolved, {
            "length": 1200.0, "width": 1000.0, "height": 130.0,
            "max_x_span": 1360.0, "max_y_span": 1100.0, "max_height": 1200.0
        })

    def test_resolve_pallet_dims_accepts_none_and_missing_pallet(self):
        violations = []
        resolved = resolve_pallet_dims(None, violations)
        self.assertEqual(violations, [])
        self.assertEqual(resolved["max_height"], 1200.0)

    def test_resolve_pallet_dims_rejects_non_dict_pallet(self):
        violations = []
        resolved = resolve_pallet_dims("bad", violations)
        self.assertTrue(any("オブジェクト形式" in v for v in violations))
        self.assertEqual(resolved["length"], 1200.0)

    def test_retired_keys_are_ignored_without_errors(self):
        violations = []
        resolved = resolve_pallet_dims({
            "min_x_span": 800.0, "min_y_span": 800.0,
            "max_overhang_x_mm": -5.0, "max_overhang_y_mm": "bad",
            "max_small_edge_overhang_mm": 30.0
        }, violations)
        self.assertEqual(violations, [])
        self.assertEqual(resolved, {
            "length": 1200.0, "width": 1000.0, "height": 130.0,
            "max_x_span": 1360.0, "max_y_span": 1100.0, "max_height": 1200.0
        })

    def test_invalid_dimension_values_are_reported_explicitly_and_fallback_applied(self):
        for field in ("length", "width", "height", "max_x_span", "max_y_span", "max_height"):
            for bad_value in (0, -1, float("nan"), float("inf"), "bad", True):
                with self.subTest(field=field, value=bad_value):
                    violations = []
                    resolved = resolve_pallet_dims({field: bad_value}, violations)
                    self.assertTrue(
                        any(f"pallet.{field}" in v for v in violations),
                        f"expected explicit violation for {field}={bad_value!r}: {violations}"
                    )
                    # 無効値は既定値へフォールバックするが、検証は常に明示的に報告される
                    # (サイレントフォールバックではない)
                    default_map = {
                        "length": 1200.0, "width": 1000.0, "height": 130.0,
                        "max_x_span": 1360.0, "max_y_span": 1100.0, "max_height": 1200.0
                    }
                    if field not in ("length", "width"):
                        self.assertEqual(resolved[field], default_map[field])

    def test_max_y_span_cannot_exceed_max_x_span(self):
        violations = []
        resolve_pallet_dims({"max_x_span": 900.0, "max_y_span": 1000.0}, violations)
        self.assertTrue(any("max_x_span" in v and "max_y_span" in v for v in violations))

    def test_length_width_swap_is_preserved(self):
        violations = []
        resolved = resolve_pallet_dims({"length": 900.0, "width": 1100.0}, violations)
        self.assertEqual((resolved["length"], resolved["width"]), (1100.0, 900.0))
        self.assertEqual(violations, [])

class PalletBoundaryIntegrationTests(PalletCaseBuilderMixin, unittest.TestCase):
    """validate_case 全体を通した、境界値(inclusive)・下限なし・空結果の検証。"""

    def test_default_pallet_centered_small_box_fails_only_upper_support(self):
        result = self.validate_boxes(
            [{"box_id": "TP-331", "x": 432.5, "y": 332.5}], omit_pallet=True
        )
        self.assertEqual(result["violations"], result["top_support"]["violations"])
        self.assertTrue(any("area ratio" in v for v in result["violations"]))
        self.assertTrue(any("multiple outer corners" in v for v in result["violations"]))

    def test_long_side_span_boundary_is_inclusive(self):
        at_limit = self.validate_boxes(
            [{"box_id": "TP-331", "x": 432.5, "y": 332.5}],
            extra_pallet={"max_x_span": 335.0, "max_y_span": 335.0}
        )
        over_limit = self.validate_boxes(
            [{"box_id": "TP-331", "x": 432.5, "y": 332.5}],
            extra_pallet={"max_x_span": 334.99, "max_y_span": 334.99}
        )
        self.assertEqual(at_limit["violations"], at_limit["top_support"]["violations"])
        self.assertTrue(any("長辺荷姿スパン超過" in v for v in over_limit["violations"]))

    def test_short_side_span_boundary_is_inclusive(self):
        at_limit = self.validate_boxes(
            [{"box_id": "TP-331", "x": 432.5, "y": 332.5}],
            extra_pallet={"max_y_span": 335.0}
        )
        over_limit = self.validate_boxes(
            [{"box_id": "TP-331", "x": 432.5, "y": 332.5}],
            extra_pallet={"max_y_span": 334.99}
        )
        self.assertEqual(at_limit["violations"], at_limit["top_support"]["violations"])
        self.assertTrue(any("短辺荷姿スパン超過" in v for v in over_limit["violations"]))

    def test_max_height_boundary_is_inclusive(self):
        at_limit = self.validate_boxes(
            [{"box_id": "TP-331", "x": 432.5, "y": 332.5}],
            extra_pallet={"max_height": 102.5}
        )
        over_limit = self.validate_boxes(
            [{"box_id": "TP-331", "x": 432.5, "y": 332.5}],
            extra_pallet={"max_height": 102.49}
        )
        self.assertEqual(at_limit["violations"], at_limit["top_support"]["violations"])
        self.assertTrue(any("最大積載高さ超過" in v for v in over_limit["violations"]))

    def test_case_specific_max_height_is_authoritative_no_fixed_1200_cap(self):
        # 旧実装の固定1200mmキャップは廃止。ケースごとの pallet.max_height が常に権威値。
        result = self.validate_boxes(
            [{"box_id": "TP-331", "x": 432.5, "y": 332.5, "z": 0.0}],
            extra_pallet={"max_height": 5000.0}
        )
        self.assertEqual(result["violations"], result["top_support"]["violations"])
        exceeding_default_only = self.validate_boxes(
            [{"box_id": "TP-331", "x": 432.5, "y": 332.5, "z": 1150.0}],
            extra_pallet={"max_height": 5000.0}
        )
        # z=1150 + height(102.5) = 1252.5 > 旧固定1200mmだが、max_height=5000なので合格
        self.assertFalse(any("最大積載高さ超過" in v for v in exceeding_default_only["violations"]))

    def test_no_minimum_span_small_single_box_passes(self):
        result = self.validate_boxes([{
            "box_id": "TP-331", "x": 575.0, "y": 475.0,
            "body_width": 50.0, "body_length": 50.0
        }])
        self.assertEqual(result["x_span"], 50.0)
        self.assertEqual(result["y_span"], 50.0)
        self.assertFalse(any("不足" in v for v in result["violations"]))

    def test_empty_boxes_still_reports_pallet_dimension_errors_without_keyerror(self):
        result = self.validate_boxes([], extra_pallet={"max_height": -1.0})
        self.assertFalse(result["is_pass"])
        self.assertEqual(result["total_boxes"], 0)
        self.assertEqual(result["x_span"], 0.0)
        self.assertEqual(result["y_span"], 0.0)
        self.assertEqual(result["max_z"], 0.0)
        self.assertEqual(result["vol_eff"], 0.0)
        self.assertIn("overhang_mm", result)
        self.assertTrue(any("配置箱数が0です" in v for v in result["violations"]))
        self.assertTrue(any("pallet.max_height" in v for v in result["violations"]))

    def test_missing_result_file_does_not_raise(self):
        result = self.validator.validate_case(
            os.path.join(tempfile.gettempdir(), "does-not-exist-supervisor-validate.json")
        )
        self.assertFalse(result["is_pass"])
        self.assertEqual(result["total_boxes"], 0)

class OverhangInformationalWarningTests(PalletCaseBuilderMixin, unittest.TestCase):
    """オーバーハングは合否に影響しない参考情報。overhang_mm (left/right/front/back) と
    warnings に記録されるのみで、violations には現れない。
    """

    def test_overhang_is_warning_not_violation(self):
        result = self.validate_boxes([{"box_id": "TP-331", "x": -16.0, "y": 300.0}])

        self.assertFalse(any("オーバーハング" in v for v in result["violations"]))
        self.assertEqual(result["overhang_mm"], {"left": 16.0, "right": 0.0, "front": 0.0, "back": 0.0})
        self.assertTrue(any("はみ出し" in w for w in result["warnings"]))

    def test_fully_inside_pallet_has_zero_overhang_and_no_warning(self):
        result = self.validate_boxes([{"box_id": "TP-331", "x": 432.5, "y": 332.5}])

        self.assertEqual(result["overhang_mm"], {"left": 0.0, "right": 0.0, "front": 0.0, "back": 0.0})
        self.assertEqual(result["warnings"], [])

    def test_right_and_back_overhang_are_measured_independently(self):
        result = self.validate_boxes([{"box_id": "TP-331", "x": 900.0, "y": 700.0}])

        # x: min=900,max=1235 -> right = 1235-1200 = 35 ; y: min=700,max=1035 -> back = 1035-1000=35
        self.assertEqual(result["overhang_mm"], {"left": 0.0, "right": 35.0, "front": 0.0, "back": 35.0})

    def test_external_lid_combined_footprint_is_used_for_overhang(self):
        # 箱本体のみなら上限内(16mm)だが、蓋込み外形では超過(20.5mm)する
        result = self.validate_boxes([{
            "box_id": "TP-331", "x": -16.0, "y": 300.0,
            "lid_id": "サンボックス330フタ"
        }])

        self.assertGreater(result["overhang_mm"]["left"], 16.0)

    def test_old_retired_overhang_keys_do_not_affect_warning_or_violations(self):
        with_retired = self.validate_boxes(
            [{"box_id": "TP-331", "x": -16.0, "y": 300.0}],
            extra_pallet={"max_overhang_x_mm": 0.0, "max_small_edge_overhang_mm": 5.0}
        )
        without_retired = self.validate_boxes([{"box_id": "TP-331", "x": -16.0, "y": 300.0}])

        self.assertEqual(with_retired["overhang_mm"], without_retired["overhang_mm"])
        self.assertEqual(with_retired["violations"], without_retired["violations"])


class PalletBottomSupportTests(PalletCaseBuilderMixin, unittest.TestCase):
    """85%底面支持率は、パレット直置き分も箱本体底面とパレット矩形(原点0,0〜
    length×width)との実交差面積で判定する。
    """

    def test_support_math_matches_engine_formula_at_exact_85_percent_boundary(self):
        from supervisor.validate import get_intersection_area, MIN_SUPPORT_RATIO, SUPPORT_RATIO_TOLERANCE

        # engine._support_ratio(0, 0, 1000, 850, 0, 0, []) と同一の数値例
        area = get_intersection_area(0.0, 0.0, 1000.0, 850.0, 0.0, 0.0, 850.0, 850.0)
        ratio = area / (1000.0 * 850.0)
        self.assertAlmostEqual(ratio, 0.85)
        self.assertGreaterEqual(ratio, MIN_SUPPORT_RATIO - SUPPORT_RATIO_TOLERANCE)

    def test_box_mostly_outside_small_pallet_fails_support_ratio(self):
        # TP-331(335x335) をパレット(167.5x167.5)の角に直置き -> 支持率25%
        result = self.validate_boxes(
            [{"box_id": "TP-331", "x": 0.0, "y": 0.0}],
            pallet={"length": 167.5, "width": 167.5}
        )
        self.assertTrue(any("支持面積不足" in v for v in result["violations"]))

    def test_box_fully_within_pallet_at_origin_passes_support_ratio(self):
        result = self.validate_boxes(
            [{"box_id": "TP-331", "x": 0.0, "y": 0.0}],
            pallet={"length": 335.0, "width": 335.0}
        )
        self.assertFalse(any("支持面積不足" in v or "空中浮遊" in v for v in result["violations"]))

    def test_box_entirely_off_pallet_is_floating(self):
        result = self.validate_boxes(
            [{"box_id": "TP-331", "x": 10000.0, "y": 10000.0}],
            pallet={"length": 335.0, "width": 335.0}
        )
        self.assertTrue(any("空中浮遊エラー" in v for v in result["violations"]))

class CoordinateReferenceAndCenteringTests(PalletCaseBuilderMixin, unittest.TestCase):
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


class ExternalLidColumnStackTests(PalletCaseBuilderMixin, unittest.TestCase):
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
    """行探索の組み合わせ回帰テスト。旧 max_overhang_y_mm 由来のエンベロープ計算は
    廃止され、_determine_mixed_envelope は pallet.max_x_span / max_y_span を
    そのまま返す (inclusive、ケースごとの上限がそのまま探索幅になる)。
    """

    @classmethod
    def setUpClass(cls):
        cls.box_db = load_box_db()
        cls.lid_db = load_lid_db()
        testcase_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                     "test_programmer", "test_cases", "outer_cover_test.json")
        if not os.path.exists(testcase_path):
            raise unittest.SkipTest(
                f"fixture not provided by test_programmer: {testcase_path}"
            )
        with open(testcase_path, encoding="utf-8") as source:
            cls.testcase = json.load(source)
        cls.validator = PalletizeValidator(cls.box_db, cls.lid_db)

    def make_engine_and_pool(self, max_y_span=None):
        """独立行探索テスト専用: 承認済み入力コーパス(outer_cover_test.json)自体は変更せず、
        このテストローカルの PalletSpec インスタンスにのみ荷山最大W (max_y_span) を
        上書きし、行探索の組み合わせ回帰意図を維持する(max_y_span=None なら
        pallet.json の既定値をそのまま使用する)。
        """
        pallet_spec = PalletSpec.from_dict(self.testcase["pallet"])
        if max_y_span is not None:
            pallet_spec.max_y_span = max_y_span
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
        self.assertEqual(envelope["y_span"], engine.pallet.max_y_span)
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

    def test_mixed_envelope_is_the_case_max_span_directly(self):
        """_determine_mixed_envelope は pallet.max_x_span / max_y_span をそのまま
        返す(ケースごとの上限がそのまま探索幅になる。旧オーバーハング由来の
        1040mm相当の計算式は存在しない)。
        """
        engine, pool = self.make_engine_and_pool(max_y_span=1040.0)
        envelope = engine._determine_mixed_envelope(pool)
        self.assertEqual(envelope["y_span"], 1040.0)
        self.assertEqual(envelope["x_span"], engine.pallet.max_x_span)

        layer_pool = [box for box in pool if box.height + box.lid_thickness == 115.5]
        candidates = engine._mixed_layer_candidates(layer_pool, 0.0, 0, [], envelope)
        spans = [
            max(box.max_y for box in boxes) - min(box.footprint_min_y for box in boxes)
            for boxes, _ in candidates
        ]
        self.assertTrue(all(span <= envelope["y_span"] + EPS for span in spans))

        # max_y_spanを厳しく絞ると、同じ幅の組み合わせ候補は生成されなくなる
        engine.pallet.max_y_span = 1000.0
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
        from algorithm_programmer.palletizer import MIXED_LAYER_SEARCH_WIDTH
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
