import json
import unittest
from collections import Counter
from dataclasses import asdict, replace
from unittest.mock import mock_open, patch

from algorithm_programmer.models import BoxSpec, PlacedBox
from algorithm_programmer.palletizer import Palletizer
from supervisor.validate import (
    PalletizeValidator, covered_support_corners, normalize_result_coordinates,
)


def box(order=1, x=0.0, y=0.0, z=0.0, w=100.0, l=100.0, **kwargs):
    return PlacedBox(order=order, box_id="TP", x=x, y=y, z=z,
                     width=w, length=l, height=100.0, fitting_depth=10.0,
                     rib_thickness=2.0, rotation=0, **kwargs)


def legacy(item):
    data = item.to_dict()
    data['position'] = {'x': item.x, 'y': item.y, 'z': item.z}
    data['dimensions'] = {'width': item.width, 'length': item.length, 'height': item.height}
    return data


class CornerSupportTests(unittest.TestCase):
    def setUp(self):
        self.spec = BoxSpec(id="TP", name="test", type="TP", width=100.0,
                            length=100.0, height=100.0, fitting_depth=10.0,
                            rib_thickness=2.0)
        self.engine = Palletizer({'TP': self.spec})

    def assert_points(self, upper, lowers, expected):
        self.assertEqual(len(self.engine._covered_support_corners(upper, lowers)), expected)
        _, points = covered_support_corners(legacy(upper), [legacy(b) for b in lowers])
        self.assertEqual(len(points), expected)
        self.assertEqual(self.engine._support_corners_allowed(upper, lowers), expected >= 2)

    def validate(self, upper, lowers, box_type="TP", lids=None, current=False):
        db = {item.box_id: dict(asdict(self.spec), id=item.box_id, type=box_type)
              for item in lowers + [upper]}
        validator = PalletizeValidator(db, lids or {})
        data = {'test_name': 'corners', 'boxes': [legacy(b) for b in lowers + [upper]]}
        if current:
            data['coordinate_reference'] = 'combined_footprint_min_xy_top_z'
            data['boxes'] = [b.to_dict() for b in lowers + [upper]]
        with patch('builtins.open', mock_open(read_data=json.dumps(data))):
            return validator.validate_case('fixture.json')['violations']

    def test_zero_one_two_four_corners(self):
        lower = box()
        for x, y, w, l, expected in (
            (0, 25, 100, 50, 0), (50, 50, 100, 100, 1),
            (0, 0, 100, 50, 2), (0, 0, 100, 100, 4),
        ):
            with self.subTest(expected=expected):
                self.assert_points(box(2, x, y, 90, w, l), [lower], expected)

    def test_multiple_supports_aggregate_and_deduplicate(self):
        lowers = [box(1), box(2, x=100)]
        upper = box(3, x=50, y=50, z=90, w=100, l=100)
        self.assert_points(upper, lowers, 1)
        raw, unique = covered_support_corners(legacy(upper), [legacy(b) for b in lowers])
        self.assertEqual((len(raw), len(unique)), (2, 1))
        separated = [box(1), box(2, x=110)]
        self.assert_points(upper, separated, 2)

    def test_boundary_tolerance_and_order_independence(self):
        lower = box()
        for offset, expected in ((0, 4), (0.009, 4), (0.01, 4), (0.0101, 2)):
            with self.subTest(offset=offset):
                self.assert_points(box(2, x=offset, z=90), [lower], expected)
        upper = box(4, z=90, w=200)
        lowers = [box(1), box(2, x=0.01), box(3, x=0.02)]
        original = self.engine._covered_support_corners(upper, lowers)
        self.assertEqual(original, self.engine._covered_support_corners(upper, list(reversed(lowers))))
        self.assertEqual(len(original), 8)
        _, independent = covered_support_corners(legacy(upper), [legacy(b) for b in lowers])
        self.assertEqual(original, independent)

    def test_only_direct_supports_count(self):
        upper = box(3, z=90)
        self.assertEqual(self.engine._covered_support_corners(upper, [box(z=10)]), [])
        self.assertEqual(self.engine._covered_support_corners(upper, [box(x=100)]), [])
        self.assertEqual(len(self.engine._covered_support_corners(upper, [box(z=1)])), 4)
        self.assertEqual(self.engine._covered_support_corners(upper, [box(z=1.01)]), [])
        for lower in (box(z=10), box(x=100)):
            messages = self.validate(upper, [lower])
            self.assertTrue(any('空中浮遊' in m for m in messages))

    def test_ground_is_exempt(self):
        self.assertTrue(self.engine._support_corners_allowed(box(), []))
        self.assertFalse(any('下段隅' in m for m in self.validate(box(), [])))

    def test_upper_lid_is_not_coverage_and_lower_lid_is_used(self):
        upper = box(2, x=25, y=25, z=90, w=50, l=50,
                    lid_width=100, lid_length=100, lid_fit_type='内嵌め')
        self.assert_points(upper, [box()], 0)
        lower = box(lid_width=120, lid_length=120, lid_fit_type='内嵌め')
        self.assert_points(box(2, z=90), [lower], 0)

    def test_fixed_large_volume_examples(self):
        central = box(13, x=97.5, y=667.5, z=90, w=335, l=167.5)
        self.assert_points(central, [box(4, x=97.5, y=500, w=335, l=502.5)], 0)
        lowers = [box(7, x=97.5, y=-2.5, w=335, l=502.5),
                  box(8, x=432.5, y=-2.5, w=335, l=502.5),
                  box(10, x=97.5, y=500, w=335, l=167.5),
                  box(11, x=432.5, y=500, w=335, l=167.5)]
        for order, y, expected in ((19, -2.5, 2), (21, 332.5, 4)):
            upper = box(order, x=97.5, y=y, z=90, w=502.5, l=335)
            supports = lowers[:2] if order == 19 else lowers
            self.assert_points(upper, supports, expected)
            self.assertFalse(any('下段隅' in m for m in self.validate(upper, supports)))

    def test_validator_diagnostics_and_coordinate_formats(self):
        lower = box(1, w=100, l=300)
        upper = box(2, y=100, z=90)
        upper.supported_by = [999]
        for current in (False, True):
            messages = self.validate(upper, [lower], current=current)
            diagnostic = next(m for m in messages if '下段隅' in m)
            self.assertIn('Order #2', diagnostic)
            self.assertIn('支持箱=[1]', diagnostic)
            self.assertIn('重複除外後=0', diagnostic)
        upper = box(2, z=90, lid_width=120, lid_length=120, lid_fit_type='内嵌め')
        data = normalize_result_coordinates({'coordinate_reference': 'combined_footprint_min_xy_top_z',
                                             'boxes': [upper.to_dict()]})
        self.assertEqual(data['boxes'][0]['position'], legacy(upper)['position'])

    def test_external_tp_and_non_tp_column_exemptions(self):
        lids = {'LID': {'fit_type': '外嵌め'}, 'OTHER': {'fit_type': '外嵌め'}}
        for box_type in ('TP', 'NON_TP'):
            engine = Palletizer({'TP': replace(self.spec, type=box_type)})
            lower = box(lid_id='LID', lid_width=120, lid_length=120, lid_fit_type='外嵌め')
            upper = replace(lower, order=2, z=90)
            self.assertEqual(engine._covered_support_corners(upper, [lower]), [])
            self.assertTrue(engine._support_corners_allowed(upper, [lower]))
            self.assertFalse(any('下段隅' in m or 'コラム' in m
                                 for m in self.validate(upper, [lower], box_type, lids)))
            shifted = replace(upper, x=1)
            self.assertFalse(engine._support_corners_allowed(shifted, [lower]))
            self.assertTrue(any('コラム' in m for m in self.validate(shifted, [lower], box_type, lids)))
            other_lid = replace(upper, lid_id='OTHER')
            self.assertEqual(engine._support_corners_allowed(other_lid, [lower]), box_type == 'NON_TP')
            messages = self.validate(other_lid, [lower], box_type, lids)
            self.assertEqual(any('コラム' in m for m in messages), box_type == 'TP')

    def test_column_exemption_preserves_type_and_single_support_rules(self):
        lids = {'LID': {'fit_type': '外嵌め'}}
        lower = box(lid_id='LID', lid_width=120, lid_length=120, lid_fit_type='外嵌め')
        upper = replace(lower, order=3, z=90, box_id='OTHER')
        for box_type in ('TP', 'NON_TP'):
            engine = Palletizer({'TP': replace(self.spec, type=box_type),
                                 'OTHER': replace(self.spec, id='OTHER', type=box_type)})
            self.assertEqual(engine._support_corners_allowed(upper, [lower]), box_type == 'TP')
            violations = self.validate(upper, [lower], box_type, lids)
            self.assertEqual(any('コラム' in m for m in violations), box_type == 'NON_TP')
            extra = replace(lower, order=2, x=100)
            self.assertFalse(engine._support_corners_allowed(upper, [lower, extra]))
            self.assertTrue(any('コラム' in m for m in self.validate(upper, [lower, extra], box_type, lids)))

    def test_candidate_paths_reject_central_placement(self):
        lower = box(w=100, l=300)
        candidate = self.engine._try_place_at(0, 100, self.spec, 0, [], 500, 500, 90, 1, [lower])
        self.assertIsNone(candidate)
        placed = self.engine._fill_row_intervals([(0, 100)], 100, 100,
                    Counter({self.spec.pool_key: 1}), {self.spec.pool_key: self.spec}, 90, 1, [lower])
        self.assertEqual(placed, [])
        self.assertIsNotNone(self.engine._try_place_at(0, 0, self.spec, 0, [], 500, 500, 90, 1, [lower]))

    def test_final_summary_detects_removed_support(self):
        lower = box()
        upper = box(2, z=90)
        before = self.engine.calculate_summary([lower, upper])
        after = self.engine.calculate_summary([upper])
        self.assertFalse(any('下段隅' in m for m in before['violations']))
        self.assertTrue(any('下段隅' in m for m in after['violations']))

    def test_rotation_does_not_change_corner_geometry(self):
        lower = box(w=100, l=200)
        upper = box(2, z=90, w=100, l=50)
        rotated_lower = replace(lower, width=200, length=100, rotation=90)
        rotated_upper = replace(upper, width=50, length=100, rotation=90)
        self.assert_points(upper, [lower], 2)
        self.assert_points(rotated_upper, [rotated_lower], 2)

    def test_existing_support_ratio_still_applies(self):
        upper = box(3, z=90, w=300, l=100)
        lowers = [box(1, w=100, l=100), box(2, x=200, w=100, l=100)]
        self.assertGreaterEqual(len(self.engine._covered_support_corners(upper, lowers)), 2)
        spec = replace(self.spec, width=300)
        self.assertIsNone(self.engine._try_place_at(0, 0, spec, 0, [], 500, 500, 90, 1, lowers))
        self.assertTrue(any('支持面積不足' in m for m in self.validate(upper, lowers)))


if __name__ == '__main__':
    unittest.main()
