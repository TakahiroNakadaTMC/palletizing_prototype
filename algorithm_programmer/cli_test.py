import unittest

from algorithm_programmer.cli import resolve_pallet_spec


class ResolvePalletSpecTest(unittest.TestCase):
    def setUp(self):
        self.pallet_database = {
            "pallets": {
                "PALLET_A": {
                    "id": "PALLET_A", "length": 1200, "width": 1000, "height": 130,
                    "suppliers": ["Supplier A"],
                },
                "__STANDARD_1200_1000_130__": {
                    "id": "__STANDARD_1200_1000_130__",
                    "length": 1200, "width": 1000, "height": 130, "suppliers": [],
                },
            }
        }
        self.test_case = {
            "pallet_id": "PALLET_A",
            "supplier_name": "Supplier A",
            "pallet": {"max_x_span": 1300, "max_y_span": 1050, "max_height": 1000},
        }

    def test_resolves_physical_dimensions_from_pallet_id(self):
        spec = resolve_pallet_spec(self.test_case, self.pallet_database)
        self.assertEqual((spec.length, spec.width, spec.height), (1200, 1000, 130))
        self.assertEqual((spec.max_x_span, spec.max_y_span, spec.max_height), (1300, 1050, 1000))

    def test_pallet_database_dimensions_override_legacy_case_values(self):
        case = {
            **self.test_case,
            "pallet": {
                "length": 999, "width": 888, "height": 77,
                "max_x_span": 1300, "max_y_span": 1050, "max_height": 1000,
            },
        }
        spec = resolve_pallet_spec(case, self.pallet_database)
        self.assertEqual((spec.length, spec.width, spec.height), (1200, 1000, 130))

    def test_standard_pallet_is_available_without_supplier_association(self):
        case = {
            "pallet_id": "__STANDARD_1200_1000_130__",
            "pallet": {"max_x_span": 1360, "max_y_span": 1100, "max_height": 1200},
        }
        spec = resolve_pallet_spec(case, self.pallet_database)
        self.assertEqual((spec.length, spec.width, spec.height), (1200, 1000, 130))

    def test_rejects_missing_pallet_id(self):
        case = dict(self.test_case)
        case.pop("pallet_id")
        with self.assertRaisesRegex(ValueError, "pallet_id"):
            resolve_pallet_spec(case, self.pallet_database)

    def test_rejects_supplier_mismatch(self):
        case = dict(self.test_case, supplier_name="Other supplier")
        with self.assertRaisesRegex(ValueError, "仕入先"):
            resolve_pallet_spec(case, self.pallet_database)


if __name__ == "__main__":
    unittest.main()
