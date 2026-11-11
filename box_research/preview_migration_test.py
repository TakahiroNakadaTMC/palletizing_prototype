import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

from box_research.preview_migration import (
    ROOT, build_preview, normalize_id, write_preview,
)


class PreviewMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "box_research").mkdir()
        (self.root / "test_programmer" / "test_cases").mkdir(parents=True)
        self.box = {
            "id": "NP22C", "name": "現場名", "type": "NON_TP",
            "length": 610, "width": 370, "height": 156,
            "fitting_depth": 7, "rib_thickness": 18, "module_ratio": None,
            "compatible_lids": ["サンボックス＃22B"],
        }
        self.boxes = {"NP22C": self.box}
        self.lids = {
            "無蓋": {"id": "無蓋", "type": "NONE"},
            "サンボックス＃22B": {"id": "サンボックス＃22B", "type": "OTHER"},
        }
        self.rows = [
            ["オティックス", "00001", "NP22C", "ｻﾝﾎﾞｯｸｽ＃22B"],
            ["オティックス", "00002", "NP22C", "ｻﾝﾎﾞｯｸｽ＃22B"],
        ]
        self.case = {
            "supplier_name": "オティックス",
            "box_list": [{"box_id": "NP22C", "lid_id": "サンボックス＃22B", "count": 17}],
        }

    def save_inputs(self):
        for name, value in (("box_db.json", self.boxes), ("lid_db.json", self.lids)):
            (self.root / "box_research" / name).write_text(
                json.dumps(value, ensure_ascii=False), encoding="utf-8")
        (self.root / "test_programmer" / "test_cases" / "case.json").write_text(
            json.dumps(self.case, ensure_ascii=False), encoding="utf-8")
        with (self.root / "box_research" / "box_list.csv").open(
                "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["仕入先名", "品番", "箱種", "型式"])
            writer.writerows(self.rows)

    def preview(self):
        self.save_inputs()
        return build_preview(self.root)

    def test_normalization_is_targeted_and_idempotent(self):
        value = "　ｻﾝﾎﾞｯｸｽ＃２２Ｂ－a  B①−　"
        expected = "サンボックス#22B-a  B①−"
        self.assertEqual(normalize_id(value), expected)
        self.assertEqual(normalize_id(expected), expected)
        for invalid in ("a\u200bb", "a\nb", "a\tb", "a\x00b"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    normalize_id(invalid)

    def test_first_candidate_uses_csv_order_preserves_count_and_inputs(self):
        self.rows.reverse()
        self.save_inputs()
        paths = [path for path in self.root.rglob("*") if path.is_file()]
        before = {path: path.read_bytes() for path in paths}
        report = build_preview(self.root)
        self.assertEqual(before, {path: path.read_bytes() for path in paths})
        row = report["case_rows"][0]
        self.assertEqual(row["part_number"], "00002")
        self.assertEqual(row["candidates"], ["00002", "00001"])
        self.assertEqual(row["count"], 17)
        self.assertEqual(row["status"], "first_candidate")
        self.assertFalse(report["applied"])
        self.assertTrue(report["requires_user_approval"])
        self.assertEqual(report["counts"]["blockers"], 0)

    def test_preview_is_unchanged_by_lf_crlf_conversion(self):
        self.save_inputs()
        lf_report = build_preview(self.root)
        paths = [path for path in self.root.rglob("*") if path.is_file()]
        for path in paths:
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.assertEqual(build_preview(self.root), lf_report)
        for path in paths:
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
        self.assertEqual(build_preview(self.root), lf_report)

    def test_exact_duplicates_and_blank_rows(self):
        self.rows.extend([self.rows[0][:], ["", "", "", "　"]])
        report = self.preview()
        self.assertEqual(report["counts"]["parts"], 2)
        self.assertEqual(report["counts"]["exact_duplicates"], 1)
        self.assertEqual(report["counts"]["blank_rows"], 1)
        self.assertEqual(report["parts"][0]["source_lines"], [2, 4])

    def test_conflicting_or_normalized_duplicate_part_is_blocked(self):
        for row in (
            ["別仕入先", "00001", "NP22C", "ｻﾝﾎﾞｯｸｽ＃22B"],
            ["オティックス", "００００１", "NP22C", "ｻﾝﾎﾞｯｸｽ＃22B"],
        ):
            with self.subTest(row=row):
                self.rows = [self.rows[0], row]
                report = self.preview()
                self.assertEqual(report["counts"]["blockers"], 1)
                self.assertEqual(report["counts"]["exact_duplicates"], 0)

    def test_unmatched_case_is_not_assigned_arbitrary_part(self):
        self.case["box_list"][0]["lid_id"] = "無蓋"
        report = self.preview()
        self.assertEqual(report["case_rows"][0]["status"], "unmatched")
        self.assertEqual(report["case_rows"][0]["part_number"], "")
        self.assertEqual(report["counts"]["unmatched_case_rows"], 1)

    def test_unknown_and_incompatible_lids_are_blocked(self):
        for label in ("UNKNOWN", "OTHER"):
            with self.subTest(label=label):
                self.lids["OTHER"] = {"id": "OTHER", "type": "OTHER"}
                self.rows = [["オティックス", "00001", "NP22C", label]]
                report = self.preview()
                self.assertFalse(report["parts"][0]["valid"])
                self.assertGreater(report["counts"]["blockers"], 0)

    def test_approved_merges_require_same_specs(self):
        second = copy.deepcopy(self.box)
        second["id"] = "NPP24"
        self.boxes["NPP24"] = second
        report = self.preview()
        self.assertEqual(report["model_mapping"]["NP22C"], "サンボックス#22H")
        self.assertEqual(report["model_mapping"]["NPP24"], "サンボックス#22H")
        self.assertEqual(report["counts"]["blockers"], 0)
        second["height"] = 200
        self.assertTrue(any(item["kind"] == "model_collision"
                            for item in self.preview()["issues"]))

    def test_approved_overrides_and_new_models(self):
        for part, box, lid in (
            ("130902501000", "TP341", "TP34蓋"),
            ("153702502000", "TP341", "TP340フタ"),
            ("155202501000", "TP331", "無蓋"),
        ):
            record = copy.deepcopy(self.box)
            record.update(id=box, compatible_lids=["TP34蓋", "TP340フタ"])
            self.boxes[box] = record
            self.lids.update({name: {"id": name, "type": "TP"}
                              for name in ("TP34蓋", "TP340フタ")})
            self.rows.append(["DENSO", part, box, "CSVの旧指定"])
        self.rows.append(["輸入部品", "13211F204002", "NEUAD9", "　"])
        report = self.preview()
        parts = {part["id"]: part for part in report["parts"]}
        self.assertEqual(parts["130902501000"]["lid_id"], "TP34蓋")
        self.assertEqual(parts["153702502000"]["lid_id"], "TP340フタ")
        self.assertEqual(parts["155202501000"]["lid_id"], "無蓋")
        self.assertTrue(parts["13211F204002"]["valid"])
        self.assertEqual(report["models"]["NEUAD9"]["fitting_depth"], 5)
        self.assertEqual(report["models"]["NS80858"]["length"], 1400)
        self.assertEqual(report["counts"]["blockers"], 0)

    def test_lid_normalization_collision_is_blocked(self):
        self.lids["サンボックス#22Bフタ"] = {
            "id": "サンボックス#22Bフタ", "type": "OTHER",
        }
        report = self.preview()
        self.assertTrue(any(item["kind"] == "id_collision" for item in report["issues"]))

    def test_support_points_and_supplier_alias_are_preserved(self):
        record = copy.deepcopy(self.box)
        record["id"] = "TP331"
        self.boxes["TP331"] = record
        self.rows = [["ＮＩＴＴＡＮ", "001", "TP331", "　"]]
        self.case = {"supplier_name": "ニッタン", "box_list": [
            {"box_id": "TP331", "lid_id": "無蓋", "count": 1}]}
        report = self.preview()
        self.assertEqual(report["parts"][0]["supplier_name"], "ニッタン")
        self.assertEqual(report["models"]["TP331"]["top_support_points"], 5)
        self.assertEqual(report["case_rows"][0]["part_number"], "001")

    def test_reports_are_new_files_and_do_not_overwrite(self):
        report = self.preview()
        output = self.root / "review"
        write_preview(report, output, self.root)
        self.assertEqual(len(list(output.iterdir())), 5)
        saved = json.loads((output / "preview.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, report)
        with (output / "cases.csv").open(encoding="utf-8-sig", newline="") as source:
            self.assertEqual(next(csv.DictReader(source))["part_number"], "00001")
        with self.assertRaises(FileExistsError):
            write_preview(report, output, self.root)
        with self.assertRaises(ValueError):
            write_preview(report, self.root, self.root)

    def test_invalid_csv_columns_and_duplicate_json_keys_fail_explicitly(self):
        self.save_inputs()
        path = self.root / "box_research" / "box_list.csv"
        path.write_text("品番,箱種\n1,BOX\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "CSV"):
            build_preview(self.root)
        self.save_inputs()
        (self.root / "box_research" / "box_db.json").write_text(
            '{"BOX": {}, "BOX": {}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "JSON"):
            build_preview(self.root)


class RepositoryPreviewTest(unittest.TestCase):
    def test_current_data_matches_approved_target_mappings(self):
        report = build_preview(ROOT)
        parts = {part["id"]: part for part in report["parts"]}
        for part, model in (
            ("111032402200", "サンボックス#22H"),
            ("111032401100", "サンボックス#22H"),
            ("113101501000", "TP364"),
            ("113202401000", "TP364"),
        ):
            with self.subTest(part=part):
                self.assertTrue(parts[part]["valid"])
                self.assertEqual(parts[part]["box_model_id"], model)
        self.assertEqual(report["counts"]["parts"], 362)
        self.assertEqual(report["counts"]["exact_duplicates"], 2)
        self.assertFalse(any(issue["severity"] == "blocker"
                             and issue["kind"] != "unmatched_case"
                             for issue in report["issues"]))


if __name__ == "__main__":
    unittest.main()
