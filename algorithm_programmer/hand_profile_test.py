import copy
import json
import math
from pathlib import Path
import unittest
import tempfile

from algorithm_programmer.hand_profile import (
    CORNERS, build_preview, sample_profile, validate_profile, validate_store, load_profile,
)
from algorithm_programmer.models import BoxSpec


class HandProfileTests(unittest.TestCase):
    def test_equipment_selection_requires_id_when_multiple_profiles_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            first, second = sample_profile(), sample_profile()
            second["id"] = "second"
            path.write_text(json.dumps({"schema_version": 1, "profiles": [first]}), encoding="utf-8")
            self.assertEqual(load_profile(str(path)), first)
            path.write_text(json.dumps({"schema_version": 1, "profiles": [first, second]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_profile(str(path))
            self.assertEqual(load_profile(str(path), "second"), second)
            with self.assertRaises(ValueError):
                load_profile(str(path), "missing")

    def setUp(self):
        self.profile = sample_profile()
        self.box = BoxSpec("TEST", "TEST", "TP", 335, 503, 195, 10, 22)

    def preview(self, corner=CORNERS[0], rotation=0):
        return build_preview(self.profile, self.box, rotation, corner)

    def test_saved_profiles_and_sample_are_valid(self):
        path = Path(__file__).with_name("hand_profiles.json")
        store = json.loads(path.read_text(encoding="utf-8"))
        validate_store(store)
        validate_profile(self.profile)

    def test_claw_position_follows_size_from_opposite_end(self):
        small = self.preview()["envelope"][2]
        self.box.width = 503
        large = self.preview()["envelope"][2]
        self.assertEqual((small["min"][0] + small["max"][0]) / 2, 285)
        self.assertEqual((large["min"][0] + large["max"][0]) / 2, 453)
        self.assertEqual(small["min"][1], large["min"][1])

    def test_fixed_body_does_not_shrink_with_box_size(self):
        small = self.preview()["envelope"][:2]
        self.box.width = 503
        self.assertEqual(self.preview()["envelope"][:2], small)
        self.box.width = 1005
        with self.assertRaises(ValueError):
            self.preview()

    def test_all_corners_and_rotations_have_expected_reference_and_yaw(self):
        for rotation, anchors in (
                (0, ([0, 0, 0], [335, 0, 0], [335, 503, 0], [0, 503, 0])),
                (90, ([503, 0, 0], [503, 335, 0], [0, 335, 0], [0, 0, 0]))):
            for index, corner in enumerate(CORNERS):
                with self.subTest(rotation=rotation, corner=corner):
                    result = self.preview(corner, rotation)
                    self.assertEqual(result["reference_position"], anchors[index])
                    self.assertEqual(result["hand_yaw_deg"], (index * 90 + rotation) % 360)
                    self.assertEqual(result["box_size"], [503, 335, 195] if rotation else [335, 503, 195])
                    self.assertFalse(result["feasibility_checked"])
                    for part in result["envelope"]:
                        self.assertTrue(all(a < b for a, b in zip(part["min"], part["max"])))

    def test_rotation_is_rigid_without_reflection(self):
        for corner in CORNERS:
            a, b = self.preview(corner), self.preview(corner, 90)
            for source, target in zip(a["envelope"], b["envelope"]):
                self.assertEqual(target["min"], [503 - source["max"][1], source["min"][0], source["min"][2]])
                self.assertEqual(target["max"], [503 - source["min"][1], source["max"][0], source["max"][2]])

    def test_lid_uses_combined_extent_and_top(self):
        self.box.lid_width, self.box.lid_length = 345, 512
        self.box.lid_thickness, self.box.lid_fit_type = 13, "外嵌め"
        result = self.preview(CORNERS[2])
        self.assertEqual(result["reference_position"], [345, 512, 0])
        self.assertEqual(result["box_size"], [345, 512, 208])
        self.box.lid_width, self.box.lid_length = 300, 480
        self.box.lid_fit_type = "内嵌め"
        self.assertEqual(self.preview()["box_size"], [335, 503, 208])

    def test_finger_envelope_uses_only_fixed_dimensions(self):
        result = self.preview()
        u_finger, v_finger = result["envelope"][2:]
        self.assertEqual(u_finger["min"], [265, -12, -30])
        self.assertEqual(u_finger["max"], [305, 0, 60])
        self.assertEqual(v_finger["min"], [-12, 433, -30])
        self.assertEqual(v_finger["max"], [0, 473, 60])
        self.profile["parameters"]["finger_thickness"] = 180
        thicker = self.preview()["envelope"]
        self.assertEqual(thicker[2]["min"][1], -180)
        self.assertEqual(thicker[3]["min"][0], -180)
        self.assertEqual(thicker[2]["max"], u_finger["max"])
        self.assertEqual(thicker[3]["max"], v_finger["max"])

    def test_preview_never_changes_equipment_or_saves_box_selection(self):
        before = copy.deepcopy(self.profile)
        for size in (335, 503):
            self.box.width = size
            for corner in CORNERS:
                for rotation in (0, 90):
                    result = self.preview(corner, rotation)
                    self.assertNotIn("path", result)
        self.assertEqual(self.profile, before)
        self.assertEqual(set(self.profile), {"id", "name", "parameters"})
        self.assertFalse(any(key.startswith(("approach", "retreat", "lift", "transfer"))
                             or key.endswith("_release")
                             for key in self.profile["parameters"]))

    def test_invalid_parameters_and_store_are_rejected(self):
        for key, value in (("body_thickness", 0), ("finger_depth", -1),
                           ("clearance", -1), ("finger_thickness", True),
                           ("body_height", math.inf), ("finger_length", math.nan),
                           ("body_u_length", 10 ** 400), ("body_bottom", -1000)):
            with self.subTest(key=key, value=value):
                profile = copy.deepcopy(self.profile)
                profile["parameters"][key] = value
                with self.assertRaises(ValueError):
                    validate_profile(profile)
        for store in ({}, {"schema_version": 1, "profiles": []},
                      {"schema_version": True, "profiles": [self.profile]},
                      {"schema_version": 1, "profiles": [self.profile, self.profile]}):
            with self.assertRaises(ValueError):
                validate_store(store)

    def test_invalid_preview_and_unknown_corner_are_rejected(self):
        for rotation in (45, True, "90"):
            with self.assertRaises(ValueError):
                self.preview(rotation=rotation)
        with self.assertRaises(ValueError):
            self.preview("UNKNOWN")
        self.profile["parameters"]["u_end_distance"] = 5
        with self.assertRaises(ValueError):
            self.preview()


if __name__ == "__main__":
    unittest.main()
