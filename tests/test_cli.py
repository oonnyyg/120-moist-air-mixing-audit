import csv
import json
import os
import tempfile
import unittest

from moist_air.cli import main

CONFIG = {
    "total_pressure_kpa": 101.325,
    "saturation_table": {
        "temperatures_c": [0.0, 10.0, 20.0, 30.0, 40.0],
        "pressures_kpa": [0.611, 1.228, 2.339, 4.246, 7.384],
    },
    "schemes": [
        {
            "name": "ok",
            "inlets": [
                {"name": "a", "temperature_c": 20.0,
                 "relative_humidity": 0.5, "mass_flow_dry_kg_s": 1.0},
                {"name": "b", "temperature_c": 30.0,
                 "relative_humidity": 0.4, "mass_flow_dry_kg_s": 2.0},
            ],
        },
        {
            "name": "bad",
            "inlets": [
                {"name": "a", "temperature_c": 20.0,
                 "relative_humidity": 1.2, "mass_flow_dry_kg_s": 1.0},
                {"name": "b", "temperature_c": 30.0,
                 "relative_humidity": 0.4, "mass_flow_dry_kg_s": 2.0},
            ],
        },
    ],
}


class CliTests(unittest.TestCase):
    def test_end_to_end_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = os.path.join(tmp, "config.json")
            csv_path = os.path.join(tmp, "out.csv")
            json_path = os.path.join(tmp, "out.json")
            with open(cfg, "w", encoding="utf-8") as fh:
                json.dump(CONFIG, fh)

            rc = main([cfg, "--csv", csv_path, "--json", json_path])
            self.assertEqual(rc, 0)

            with open(csv_path, newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            # ok scheme: 2 inlets + 1 mixed; bad scheme: 1 invalid row.
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[-1]["role"], "invalid")

            with open(json_path, encoding="utf-8") as fh:
                report = json.load(fh)
            self.assertEqual(report["total_pressure_kpa"], 101.325)
            ok, bad = report["schemes"]
            self.assertTrue(ok["valid"])
            self.assertFalse(bad["valid"])
            self.assertIn("error", bad)
            for value in ok["balance_residuals"].values():
                self.assertAlmostEqual(value, 0.0)

    def test_config_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = os.path.join(tmp, "config.json")
            bad = dict(CONFIG)
            bad["total_pressure_kpa"] = 1.0  # below table saturation pressures
            with open(cfg, "w", encoding="utf-8") as fh:
                json.dump(bad, fh)
            rc = main([cfg, "--csv", os.path.join(tmp, "a.csv"),
                       "--json", os.path.join(tmp, "a.json")])
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
