import copy
import os
import unittest
from unittest.mock import patch

from box_research.catalog_store import load_catalog, preview_skid_changes, save_catalog, validate_catalog
from box_research.catalog_store_test import CatalogFixture
from box_research.skid_catalog import resolve_skid_case, normalize_skid_id, validate_suppliers


class SkidCatalogTest(CatalogFixture, unittest.TestCase):
    def save_skids(self, draft):
        plan = preview_skid_changes(self.root, draft["skids"], self.revision)
        save_catalog(self.root, draft, self.revision, plan["confirmation"])
        return plan

    def test_change_preview_history_and_only_skid_file_changes(self):
        before = self.snapshot()
        draft = copy.deepcopy(self.data)
        draft["skids"]["0001AA"]["pallet"]["max_height"] = 826
        plan = self.save_skids(draft)
        self.assertEqual(plan["changes"][0]["affected_cases"], ["case"])
        self.assertEqual(plan["changes"][0]["before"]["pallet"]["max_height"], 1200)
        self.assertEqual(plan["changes"][0]["after"]["pallet"]["max_height"], 826)
        loaded, revision = load_catalog(self.root)
        after = self.snapshot()
        changed = [path for path in before if before[path] != after[path]]
        self.assertEqual(changed, [self.catalog_dir.relative_to(self.root) / "skid_db.json"])
        case = loaded["cases"]["test_cases"]["case"]
        self.assertNotIn("pallet", case)
        self.assertEqual(resolve_skid_case(case, loaded)["pallet"]["max_height"], 826)
        self.assertNotEqual(revision, self.revision)
        self.assertEqual(len(loaded["skids"]["0001AA"]["history"]), 2)

    def test_copied_skid_db_is_used_without_rewriting_cases(self):
        draft = copy.deepcopy(self.data)
        draft["skids"]["0001AA"]["pallet_id"] = "PALLET-A"
        self.save_skids(draft)
        loaded, _ = load_catalog(self.root)
        self.assertEqual(resolve_skid_case(loaded["cases"]["test_cases"]["case"], loaded)["pallet_id"],
                         "PALLET-A")
        # A receiver updates only the validated skid JSON, with unchanged cases.
        original_cases = self.snapshot()[self.catalog_dir.relative_to(self.root) / "test_cases.json"]
        self.write_json(self.catalog_dir / "skid_db.json", self.data["skids"])
        copied, revision = load_catalog(self.root)
        self.assertEqual(resolve_skid_case(copied["cases"]["test_cases"]["case"], copied)["pallet_id"],
                         self.data["skids"]["0001AA"]["pallet_id"])
        self.assertEqual(self.snapshot()[self.catalog_dir.relative_to(self.root) / "test_cases.json"],
                         original_cases)
        self.assertEqual(revision, self.revision)

    def test_incomplete_skid_blocks_calculation_and_new_cases_but_keeps_existing(self):
        draft = copy.deepcopy(self.data)
        draft["skids"]["0001AA"]["pallet_id"] = None
        self.save_skids(draft)
        loaded, revision = load_catalog(self.root)
        case = loaded["cases"]["test_cases"]["case"]
        with self.assertRaisesRegex(ValueError, "未登録"):
            resolve_skid_case(case, loaded)
        loaded["cases"]["test_cases"]["new"] = dict(copy.deepcopy(case), name="new")
        loaded["cases"]["approval_state"]["new"] = False
        with self.assertRaisesRegex(ValueError, "作成"):
            save_catalog(self.root, loaded, revision)

    def test_used_candidate_and_skid_deletion_are_rejected(self):
        extra = copy.deepcopy(self.data)
        extra["parts"]["00002"] = dict(extra["parts"][self.part_id], id="00002")
        self.revision = save_catalog(self.root, extra, self.revision)
        self.data, _ = load_catalog(self.root)
        for operation in ("part", "skid"):
            draft = copy.deepcopy(self.data)
            if operation == "part":
                draft["skids"]["0001AA"]["part_numbers"] = ["00002"]
            else:
                del draft["skids"]["0001AA"]
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, "候補|KEY2"):
                self.save_skids(draft)

    def test_unconfirmed_and_stale_changes_do_not_write(self):
        before = self.snapshot()
        draft = copy.deepcopy(self.data)
        draft["skids"]["0001AA"]["pallet"]["max_height"] = 826
        with self.assertRaisesRegex(ValueError, "確認"):
            save_catalog(self.root, draft, self.revision)
        self.assertEqual(self.snapshot(), before)
        plan = preview_skid_changes(self.root, draft["skids"], self.revision)
        draft["skids"]["0001AA"]["pallet"]["max_height"] = 827
        with self.assertRaisesRegex(ValueError, "確認"):
            save_catalog(self.root, draft, self.revision, plan["confirmation"])
        self.assertEqual(self.snapshot(), before)

    def test_history_tampering_and_invalid_limits_are_rejected(self):
        for value in (0, -1, True, 1.5e309, "826"):
            draft = copy.deepcopy(self.data)
            draft["skids"]["0001AA"]["pallet"]["max_height"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.save_skids(draft)
        draft = copy.deepcopy(self.data)
        draft["skids"]["0001AA"]["history"][0]["affected_cases"] = []
        with self.assertRaisesRegex(ValueError, "履歴"):
            save_catalog(self.root, draft, self.revision)
        draft = copy.deepcopy(self.data)
        draft["cases"]["test_cases"]["case"]["pallet_id"] = "PALLET-A"
        with self.assertRaises(ValueError):
            validate_catalog(draft)

    def test_candidates_allow_one_part_on_multiple_skids(self):
        draft = copy.deepcopy(self.data)
        draft["skids"]["0001AB"] = dict(copy.deepcopy(draft["skids"]["0001AA"]),
                                       id="0001AB", updated_at="", history=[])
        self.save_skids(draft)
        loaded, _ = load_catalog(self.root)
        self.assertEqual(loaded["skids"]["0001AB"]["part_numbers"], [self.part_id])

    def test_invalid_pallet_values_are_not_silently_treated_as_unregistered(self):
        for value in (False, 0, [], {}, ""):
            draft = copy.deepcopy(self.data)
            draft["skids"]["0001AA"]["pallet_id"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.save_skids(draft)

    def renamed_draft(self, target="0001A030J"):
        draft = copy.deepcopy(self.data)
        skid = draft["skids"].pop("0001AA")
        skid["id"] = target
        draft["skids"][target] = skid
        return draft

    def test_four_field_id_normalization_and_exact_lengths(self):
        for value, expected in (("0001aJ", "0001AJ"), ("０００１ａ０３０ｊ", "0001A030J"),
                                ("00010000z", "00010000Z")):
            with self.subTest(value=value):
                self.assertEqual(normalize_skid_id(value), expected)
        for value in ("1019430J", "001AJ", "0001AA0", "0001A0J", "0001A00J",
                      "0001A0000J", "0001A0301", "0001_030J", "0001あJ", 1019430, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_skid_id(value)

    def test_confirmed_rename_updates_case_references_and_preserves_history(self):
        draft = self.renamed_draft()
        renames = {"0001AA": "0001A030J"}
        before = self.snapshot()
        plan = preview_skid_changes(self.root, draft["skids"], self.revision, skid_renames=renames)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(plan["changes"][0]["old_skid_id"], "0001AA")
        self.assertEqual(plan["changes"][0]["affected_cases"], ["case"])
        with self.assertRaisesRegex(ValueError, "確認"):
            save_catalog(self.root, draft, self.revision, skid_renames=renames)
        self.assertEqual(self.snapshot(), before)
        save_catalog(self.root, draft, self.revision, plan["confirmation"], renames)
        saved, _ = load_catalog(self.root)
        self.assertNotIn("0001AA", saved["skids"])
        self.assertEqual(saved["cases"]["test_cases"]["case"]["skid_id"], "0001A030J")
        self.assertEqual(saved["cases"]["test_cases"]["case"]["box_list"],
                         self.data["cases"]["test_cases"]["case"]["box_list"])
        self.assertEqual(saved["cases"]["approval_state"], self.data["cases"]["approval_state"])
        skid = saved["skids"]["0001A030J"]
        self.assertEqual(skid["history"][:-1], self.data["skids"]["0001AA"]["history"])
        self.assertEqual(skid["history"][-1]["previous_id"], "0001AA")
        self.assertEqual(skid["history"][-1]["skid_id"], "0001A030J")
        self.assertEqual(skid["pallet"], self.data["skids"]["0001AA"]["pallet"])

    def test_rename_rejects_duplicate_target_and_invalid_mapping(self):
        for renames in ({"0001AA": "0001AA"}, {"0001AB": "0001A030J"}, [],
                        {"0001AA": "BAD"}, False):
            with self.subTest(renames=renames), self.assertRaises(ValueError):
                preview_skid_changes(self.root, self.renamed_draft()["skids"],
                                     self.revision, skid_renames=renames)
        draft = copy.deepcopy(self.data)
        draft["skids"]["0001AB"] = dict(copy.deepcopy(draft["skids"]["0001AA"]),
                                        id="0001AB", updated_at="", history=[])
        self.save_skids(draft)
        self.data, self.revision = load_catalog(self.root)
        draft = self.renamed_draft("0001AB")
        with self.assertRaisesRegex(ValueError, "既に"):
            preview_skid_changes(self.root, draft["skids"], self.revision,
                                 skid_renames={"0001AA": "0001AB"})

    def test_id_rename_to_incomplete_skid_is_allowed_for_existing_cases(self):
        draft = copy.deepcopy(self.data)
        draft["skids"]["0001AA"]["pallet_id"] = None
        self.save_skids(draft)
        self.data, self.revision = load_catalog(self.root)
        draft = self.renamed_draft()
        renames = {"0001AA": "0001A030J"}
        plan = preview_skid_changes(self.root, draft["skids"], self.revision, skid_renames=renames)
        save_catalog(self.root, draft, self.revision, plan["confirmation"], renames)
        saved, _ = load_catalog(self.root)
        with self.assertRaisesRegex(ValueError, "未登録"):
            resolve_skid_case(saved["cases"]["test_cases"]["case"], saved)

    def test_unknown_supplier_and_used_mapping_deletion_are_rejected(self):
        draft = self.renamed_draft("9999AA")
        with self.assertRaisesRegex(ValueError, "仕入先対応表"):
            preview_skid_changes(self.root, draft["skids"], self.revision,
                                 skid_renames={"0001AA": "9999AA"})
        draft = copy.deepcopy(self.data)
        draft["suppliers"].clear()
        with self.assertRaisesRegex(ValueError, "仕入先対応表"):
            preview_skid_changes(self.root, None, self.revision,
                                 updates={"suppliers": draft["suppliers"]})

    def test_mapping_creation_requires_confirmation_and_preserves_leading_zeros(self):
        draft = copy.deepcopy(self.data)
        draft["suppliers"]["０００２"] = dict(id="０００２", supplier_name="Supplier A")
        plan = preview_skid_changes(self.root, None, self.revision,
                                    updates={"suppliers": draft["suppliers"]})
        with self.assertRaisesRegex(ValueError, "確認"):
            save_catalog(self.root, draft, self.revision)
        save_catalog(self.root, draft, self.revision, plan["confirmation"])
        saved, _ = load_catalog(self.root)
        self.assertEqual(saved["suppliers"]["0002"], dict(id="0002", supplier_name="Supplier A"))
        for value in ("123", "12345", "ABCD"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_suppliers({value: dict(id=value, supplier_name="A")})

    def test_supplier_name_correction_previews_and_updates_every_reference(self):
        draft = copy.deepcopy(self.data)
        draft["suppliers"]["0001"]["supplier_name"] = "Corrected supplier"
        plan = preview_skid_changes(self.root, None, self.revision,
                                    updates={"suppliers": draft["suppliers"]})
        change = plan["supplier_changes"][0]
        self.assertEqual(change["before"], "Supplier A")
        self.assertEqual(change["after"], "Corrected supplier")
        self.assertEqual(change["affected_cases"], ["case"])
        self.assertEqual(change["affected_parts"], ["00001"])
        self.assertEqual(change["affected_pallets"], ["PALLET-A"])
        save_catalog(self.root, draft, self.revision, plan["confirmation"])
        saved, revision = load_catalog(self.root)
        self.assertNotEqual(revision, self.revision)
        for collection, key in (("suppliers", "0001"), ("parts", "00001"), ("skids", "0001AA")):
            self.assertEqual(saved[collection][key]["supplier_name"], "Corrected supplier")
        self.assertEqual(saved["cases"]["test_cases"]["case"]["supplier_name"], "Corrected supplier")
        self.assertEqual(saved["pallets"]["pallets"]["PALLET-A"]["suppliers"], ["Corrected supplier"])
        self.assertEqual(saved["skids"]["0001AA"]["history"][-1]["before"]["supplier_name"],
                         "Supplier A")
        self.assertEqual(saved["skids"]["0001AA"]["history"][-1]["after"]["supplier_name"],
                         "Corrected supplier")

    def test_supplier_correction_and_rename_roll_back_all_files_on_failure(self):
        for operation in ("rename", "supplier"):
            draft = self.renamed_draft() if operation == "rename" else copy.deepcopy(self.data)
            renames = {"0001AA": "0001A030J"} if operation == "rename" else {}
            if operation == "supplier":
                draft["suppliers"]["0001"]["supplier_name"] = "Corrected supplier"
            plan = preview_skid_changes(self.root, draft["skids"], self.revision,
                                        updates={"suppliers": draft["suppliers"]}, skid_renames=renames)
            before = self.snapshot()
            replace = os.replace
            calls = []

            def fail_second(source, target):
                calls.append(target)
                if len(calls) == 2:
                    raise OSError("replacement failed")
                return replace(source, target)

            with self.subTest(operation=operation), patch(
                    "box_research.catalog_store.os.replace", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "replacement failed"):
                    save_catalog(self.root, draft, self.revision, plan["confirmation"], renames)
            self.assertEqual(self.snapshot(), before)
