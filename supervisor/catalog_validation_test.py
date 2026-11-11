"""品番・共通モデル・数量を信用せず独立に照合するテスト。"""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from algorithm_programmer.catalog import run_catalog_case
from algorithm_programmer.cli import resolve_pallet_spec
from box_research.catalog_store import catalog_pallets, load_catalog
from supervisor.catalog_validation import validate_catalog_run
from supervisor.validate import PalletizeValidator


ROOT = Path(__file__).resolve().parent.parent


class CatalogValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.revision = load_catalog(ROOT)
        cls.pallets = catalog_pallets(ROOT)
        case = cls.catalog["cases"]["test_cases"]["othics_6"]
        cls.result = run_catalog_case("othics_6", case, cls.catalog,
                                     resolve_pallet_spec(case, cls.pallets), cls.revision)

    def validate(self, data, catalog=None, revision=None):
        catalog = catalog or self.catalog
        validator = PalletizeValidator(catalog["models"], catalog["lids"],
                                      catalog, revision or self.revision, self.pallets)
        return validator.validate_data(data)

    def test_valid_alias_stack_and_quantities(self):
        report = self.validate(self.result)
        self.assertTrue(report["is_pass"], report["violations"])
        self.assertEqual(report["part_counts"], self.result["part_counts"])
        self.assertEqual(report["input_boxes_count"], 30)
        self.assertEqual(report["unplaced_boxes_count"], 6)
        for box in report["top_support"]["support_boxes"]:
            self.assertIn("part_number", box)
            self.assertIn(box["box_id"], ("NP22C", "NPP24"))

    def test_no_catalog_is_explicit_failure(self):
        report = PalletizeValidator({}, {}).validate_data(self.result)
        self.assertFalse(report["is_pass"])
        self.assertIn("--catalog-results", report["violations"][0])

    def test_identity_forgery_is_rejected(self):
        for field in ("part_number", "supplier_name", "box_id", "box_name", "box_model_id", "lid_id"):
            for section in ("boxes", "unplaced_boxes", "input_parts", "part_counts"):
                with self.subTest(field=field, section=section):
                    data = copy.deepcopy(self.result)
                    data[section][0][field] = "偽の参照"
                    self.assertFalse(self.validate(data)["is_pass"])

    def test_stale_result_and_changed_case_are_rejected(self):
        self.assertFalse(self.validate(self.result, revision="different")["is_pass"])
        data = copy.deepcopy(self.result)
        data["test_name"] = "missing"
        self.assertFalse(self.validate(data)["is_pass"])
        for field in ("supplier_name", "pallet_id"):
            data = copy.deepcopy(self.result)
            data[field] = "different"
            self.assertFalse(self.validate(data)["is_pass"])
        changed = copy.deepcopy(self.catalog)
        changed["cases"]["test_cases"]["othics_6"]["box_list"][0]["count"] += 1
        self.assertFalse(self.validate(self.result, catalog=changed)["is_pass"])

    def test_counts_and_derived_lists_are_recomputed(self):
        for field in ("input_boxes_count", "placed_boxes_count", "unplaced_boxes_count"):
            for value in (0, True, 1.5, None):
                with self.subTest(field=field, value=value):
                    data = copy.deepcopy(self.result)
                    data[field] = value
                    self.assertFalse(self.validate(data)["is_pass"])
        for field in ("input_parts", "part_counts", "input_box_variants", "unplaced_boxes"):
            for value in (None, {}, []):
                with self.subTest(field=field, value=value):
                    data = copy.deepcopy(self.result)
                    data[field] = value
                    self.assertFalse(self.validate(data)["is_pass"])
        for field in ("input_count", "placed_count", "unplaced_count"):
            data = copy.deepcopy(self.result)
            data["part_counts"][0][field] = True
            self.assertFalse(self.validate(data)["is_pass"])

    def test_nonfinite_numbers_order_and_fitting_are_rejected(self):
        for section, field, value in (
            ("position", "x", float("nan")), ("position", "z", float("inf")),
            ("dimensions", "height", -1), ("lid_dimensions", "width", float("inf")),
        ):
            with self.subTest(section=section, field=field):
                data = copy.deepcopy(self.result)
                data["boxes"][0][section][field] = value
                self.assertFalse(self.validate(data)["is_pass"])
        for field, value in (("order", 2), ("order", True), ("rotation", True),
                             ("fitting_depth", 99), ("supported_by", [1]), ("layer_index", -1)):
            data = copy.deepcopy(self.result)
            data["boxes"][0][field] = value
            self.assertFalse(self.validate(data)["is_pass"])
        data = copy.deepcopy(self.result)
        upper = next(box for box in data["boxes"] if box["supported_by"])
        upper["supported_by"] = []
        self.assertFalse(self.validate(data)["is_pass"])

    def test_pallet_settings_are_checked_against_authoritative_data(self):
        for key in ("length", "width", "height", "max_x_span", "max_y_span", "max_height"):
            data = copy.deepcopy(self.result)
            data["pallet"][key] += 100
            self.assertFalse(self.validate(data)["is_pass"])

    def test_geometry_and_lids_are_independent_of_success_summary(self):
        for change in ("shift", "floating", "lid", "height", "bottom", "rotation"):
            with self.subTest(change=change):
                data = copy.deepcopy(self.result)
                box = data["boxes"][-1]
                if change == "shift":
                    box["position"]["x"] += 20
                elif change == "floating":
                    box["position"]["z"] += 100
                elif change == "lid":
                    box["lid_dimensions"]["width"] += 10
                elif change == "height":
                    box["dimensions"]["height"] += 10
                elif change == "bottom":
                    data["boxes"][0]["position"]["z"] = 0
                elif change == "rotation":
                    box["rotation"] = 45
                data["summary"]["is_valid"] = True
                self.assertFalse(self.validate(data)["is_pass"])
        data = copy.deepcopy(self.result)
        data["summary"] = {"is_valid": False, "violations": ["not authoritative"]}
        self.assertTrue(self.validate(data)["is_pass"])

    def test_external_tp_column_keeps_same_lid_alignment_and_single_support(self):
        catalog = copy.deepcopy(self.catalog)
        data = copy.deepcopy(self.result)
        first, second = [row["part_number"] for row in data["input_parts"]]
        model_id = catalog["parts"][first]["box_model_id"]
        lid_id = catalog["parts"][first]["lid_id"]
        catalog["models"][model_id]["type"] = "TP"
        catalog["lids"][lid_id]["fit_type"] = "外嵌め"
        for box in data["boxes"]:
            box["lid_fit_type"] = "外嵌め"
        valid = self.validate(data, catalog)
        self.assertTrue(valid["is_pass"], valid["violations"])
        for change in ("different_lid", "offset", "multiple_supports"):
            with self.subTest(change=change):
                modified = copy.deepcopy(data)
                masters = copy.deepcopy(catalog)
                if change == "different_lid":
                    masters["lids"]["別の外蓋"] = dict(masters["lids"][lid_id], id="別の外蓋")
                    masters["models"][model_id]["compatible_lids"].append("別の外蓋")
                    masters["parts"][second]["lid_id"] = "別の外蓋"
                    for field in ("boxes", "unplaced_boxes", "input_parts", "part_counts", "input_box_variants"):
                        for row in modified[field]:
                            if row["part_number"] == second:
                                row["lid_id"] = "別の外蓋"
                    modified["algorithm_mode"] = "mixed"
                elif change == "offset":
                    modified["boxes"][-1]["position"]["x"] += 0.02
                else:
                    modified["boxes"][1]["position"] = dict(modified["boxes"][0]["position"])
                report = self.validate(modified, masters)
                self.assertFalse(report["is_pass"])
                self.assertTrue(any("コラム積み条件違反" in item for item in report["violations"]),
                                report["violations"])

    def test_saved_result_file_api_and_invalid_json(self):
        validator = PalletizeValidator(self.catalog["models"], self.catalog["lids"],
                                      self.catalog, self.revision, self.pallets)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text(json.dumps(self.result, ensure_ascii=False), encoding="utf-8")
            self.assertTrue(validator.validate_case(str(path))["is_pass"])
            path.write_text("{", encoding="utf-8")
            self.assertFalse(validator.validate_case(str(path))["is_pass"])

    def fixture_run(self, directory):
        catalog = copy.deepcopy(self.catalog)
        catalog["cases"]["test_cases"] = {"othics_6": catalog["cases"]["test_cases"]["othics_6"]}
        catalog["cases"]["approval_state"] = {"othics_6": True}
        path = Path(directory) / "results"
        path.mkdir()
        (path / "result_othics_6.json").write_text(json.dumps(self.result), encoding="utf-8")
        manifest = dict(input_mode="part_number", catalog_revision=self.revision,
                        cases=[dict(name="othics_6", result_file="result_othics_6.json", status="PASS")])
        (path / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return catalog, path, manifest

    def test_run_reports_quantity_and_does_not_trust_manifest_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog, results, manifest = self.fixture_run(directory)
            with patch("supervisor.catalog_validation.load_catalog", return_value=(catalog, self.revision)), \
                 redirect_stdout(StringIO()):
                reports = Path(directory) / "reports"
                self.assertEqual(validate_catalog_run(ROOT, results, reports), 0)
                report = json.loads((reports / "report_othics_6.json").read_text(encoding="utf-8"))
                self.assertEqual(report["part_counts"], self.result["part_counts"])
                self.assertTrue((reports / "validation_report.md").exists())
                with self.assertRaises(FileExistsError):
                    validate_catalog_run(ROOT, results, reports)
                data = copy.deepcopy(self.result)
                data["boxes"][0]["fitting_depth"] += 10
                (results / "result_othics_6.json").write_text(json.dumps(data), encoding="utf-8")
                self.assertEqual(validate_catalog_run(ROOT, results, Path(directory) / "bad"), 1)

    def test_manifest_missing_case_revision_wrong_file_and_stale_error_result(self):
        for change in ("missing", "revision", "filename", "case_name", "error"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                catalog, results, manifest = self.fixture_run(directory)
                if change == "missing":
                    manifest["cases"] = []
                elif change == "revision":
                    manifest["catalog_revision"] = "changed"
                elif change == "filename":
                    manifest["cases"][0]["result_file"] = "..\\result.json"
                elif change == "case_name":
                    data = copy.deepcopy(self.result)
                    data["test_name"] = "aisin"
                    (results / "result_othics_6.json").write_text(json.dumps(data), encoding="utf-8")
                elif change == "error":
                    manifest["cases"][0].update(status="ERROR", error="calculation failed")
                (results / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                with patch("supervisor.catalog_validation.load_catalog", return_value=(catalog, self.revision)), \
                     redirect_stdout(StringIO()):
                    if change in ("case_name", "error"):
                        target = Path(directory) / "report"
                        self.assertEqual(validate_catalog_run(ROOT, results, target), 1)
                        report = json.loads((target / "report_othics_6.json").read_text(encoding="utf-8"))
                        self.assertFalse(report["is_pass"])
                    else:
                        with self.assertRaises(ValueError):
                            validate_catalog_run(ROOT, results, Path(directory) / "report")

    def test_cli_rejects_stale_manifest_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            _, results, manifest = self.fixture_run(directory)
            manifest["catalog_revision"] = "stale"
            (results / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            run = subprocess.run([sys.executable, str(ROOT / "supervisor" / "validate.py"),
                                  "--catalog-results", str(results), "--report-dir",
                                  str(Path(directory) / "reports")], capture_output=True, encoding="utf-8")
            self.assertEqual(run.returncode, 1)
            self.assertIn("再計算", run.stderr)


if __name__ == "__main__":
    unittest.main()
