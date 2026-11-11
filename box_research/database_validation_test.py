import copy
import unittest

from box_research.database_validation import (
    STANDARD_PALLET,
    STANDARD_PALLET_ID,
    validate_box_lid_databases,
    validate_case_references,
    validate_pallet_database,
)


class DatabaseValidationTest(unittest.TestCase):
    def setUp(self):
        self.boxes = {"BOX": {"id": "BOX", "compatible_lids": ["LID"]}}
        self.lids = {
            "NONE": {"id": "NONE", "type": "NONE"},
            "LID": {"id": "LID", "type": "TP"},
        }
        self.pallet_db = {"pallets": {
            STANDARD_PALLET_ID: copy.deepcopy(STANDARD_PALLET),
            "MODEL": {
                "id": "MODEL", "model": "Model", "length": 1200, "width": 1000,
                "height": 130, "suppliers": ["Supplier"],
            },
        }}

    def test_valid_databases_are_not_modified(self):
        original = copy.deepcopy((self.boxes, self.lids, self.pallet_db))
        validate_box_lid_databases(self.boxes, self.lids)
        self.assertIs(validate_pallet_database(self.pallet_db), self.pallet_db)
        self.assertEqual((self.boxes, self.lids, self.pallet_db), original)

    def test_rejects_malformed_box_lid_database_and_unknown_compatible_lids(self):
        for boxes, lids in (
            ([], self.lids), (self.boxes, []),
            ({"BOX": {"id": "OTHER"}}, self.lids),
            (self.boxes, {"NONE": {"id": "OTHER", "type": "NONE"}}),
            (self.boxes, {"LID": self.lids["LID"]}),
            ({"BOX": {"id": "BOX", "compatible_lids": ["UNKNOWN"]}}, self.lids),
            ({"BOX": {"id": "BOX", "compatible_lids": None}}, self.lids),
        ):
            with self.subTest(boxes=boxes, lids=lids):
                with self.assertRaises(ValueError):
                    validate_box_lid_databases(boxes, lids)

    def test_rejects_invalid_pallet_dimensions(self):
        for field in ("length", "width", "height"):
            for value in (0, -1, True, "1200", None, float("nan"), float("inf")):
                with self.subTest(field=field, value=value):
                    data = copy.deepcopy(self.pallet_db)
                    data["pallets"]["MODEL"][field] = value
                    with self.assertRaisesRegex(ValueError, field):
                        validate_pallet_database(data)

    def test_standard_pallet_cannot_be_changed_or_removed(self):
        for removed in (True, False):
            with self.subTest(removed=removed):
                data = copy.deepcopy(self.pallet_db)
                if removed:
                    del data["pallets"][STANDARD_PALLET_ID]
                else:
                    data["pallets"][STANDARD_PALLET_ID]["height"] = 150
                with self.assertRaises(ValueError):
                    validate_pallet_database(data)

    def test_pallet_length_must_be_at_least_width(self):
        data = copy.deepcopy(self.pallet_db)
        data["pallets"]["MODEL"].update(length=999, width=1000)
        with self.assertRaisesRegex(ValueError, "length L.*width W"):
            validate_pallet_database(data)
        data["pallets"]["MODEL"]["length"] = 1000
        validate_pallet_database(data)

    def test_rejects_invalid_pallet_records(self):
        for update in (
            {"id": "OTHER"}, {"model": ""}, {"standard": True},
            {"suppliers": []}, {"suppliers": ["Supplier", "Supplier"]},
            {"suppliers": [""]}, {"suppliers": [None]},
        ):
            with self.subTest(update=update):
                data = copy.deepcopy(self.pallet_db)
                data["pallets"]["MODEL"].update(update)
                with self.assertRaises(ValueError):
                    validate_pallet_database(data)

    def test_case_validation_does_not_change_input(self):
        case = {
            "description": "Test", "pallet_id": "MODEL", "supplier_name": "Supplier",
            "box_list": [{"box_id": "BOX", "lid_id": "LID", "count": 1}],
        }
        original = copy.deepcopy(case)
        validate_case_references("case", case, self.boxes, self.lids, self.pallet_db)
        self.assertEqual(case, original)


if __name__ == "__main__":
    unittest.main()
