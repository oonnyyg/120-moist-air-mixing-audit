import csv
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moist_air import Inlet, PropertyTable, evaluate_scheme, inlet_state
from moist_air.audit import (
    CSV_HEADER,
    ConfigError,
    parse_config,
    report_to_dict,
    report_to_row,
    run_audit,
)
from moist_air.cli import main as cli_main
from moist_air.properties import PropertyTableError
from moist_air.psychrometry import (
    InletError,
    temperature_from_enthalpy,
    vapour_pressure_from_humidity_ratio,
)

TEMPS = (0.0, 10.0, 20.0, 30.0, 40.0)
PSATS = (0.6112, 1.2281, 2.3392, 4.2460, 7.3849)


class PropertyTableTests(unittest.TestCase):
    def setUp(self):
        self.table = PropertyTable(101.325, TEMPS, PSATS)

    def test_piecewise_linear_interpolation(self):
        self.assertAlmostEqual(
            self.table.saturation_pressure(15.0),
            (1.2281 + 2.3392) / 2,
            places=10,
        )
        self.assertAlmostEqual(self.table.saturation_pressure(0.0), 0.6112, places=12)
        self.assertAlmostEqual(self.table.saturation_pressure(40.0), 7.3849, places=12)

    def test_out_of_range_and_non_finite_rejected(self):
        for bad in (-0.001, 40.001, float("inf"), float("nan")):
            with self.assertRaises(PropertyTableError):
                self.table.saturation_pressure(bad)

    def test_table_validation(self):
        with self.assertRaises(PropertyTableError):
            PropertyTable(101.325, (0.0, 10.0), (2.3, 1.0))
        with self.assertRaises(PropertyTableError):
            PropertyTable(101.325, (20.0, 10.0), (1.0, 2.0))
        with self.assertRaises(PropertyTableError):
            PropertyTable(5.0, (0.0, 10.0), (1.0, 6.0))
        with self.assertRaises(PropertyTableError):
            PropertyTable(-1.0, (0.0, 10.0), (1.0, 2.0))
        with self.assertRaises(PropertyTableError):
            PropertyTable(101.325, (0.0,), (1.0,))


class InletStateTests(unittest.TestCase):
    def setUp(self):
        self.table = PropertyTable(101.325, TEMPS, PSATS)

    def test_dry_air_has_no_vapour(self):
        state = inlet_state(Inlet(25.0, 0.0, 1.0), self.table)
        self.assertEqual(state.vapour_pressure, 0.0)
        self.assertEqual(state.humidity_ratio, 0.0)
        self.assertAlmostEqual(state.enthalpy, 1.006 * 25.0, places=12)

    def test_reference_20c_50_percent(self):
        state = inlet_state(Inlet(20.0, 0.5, 2.0), self.table)
        self.assertAlmostEqual(state.vapour_pressure, 1.1696, places=12)
        expected_w = 0.621945 * 1.1696 / (101.325 - 1.1696)
        self.assertAlmostEqual(state.humidity_ratio, expected_w, places=12)
        expected_h = 1.006 * 20 + expected_w * (2501 + 1.86 * 20)
        self.assertAlmostEqual(state.enthalpy, expected_h, places=10)

    def test_invalid_inlets(self):
        for bad in (Inlet(20, 1.1, 1), Inlet(20, -0.1, 1), Inlet(20, 0.5, 0)):
            with self.assertRaises(InletError):
                inlet_state(bad, self.table)
        with self.assertRaises(PropertyTableError):
            inlet_state(Inlet(50, 0.5, 1), self.table)


class MixingTests(unittest.TestCase):
    def setUp(self):
        self.table = PropertyTable(101.325, TEMPS, PSATS)

    def test_dry_air_streams_weight_by_flow_not_temperature(self):
        result = evaluate_scheme(
            [Inlet(10.0, 0.0, 1.0), Inlet(30.0, 0.0, 3.0)], self.table
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.mixed_humidity_ratio, 0.0)
        self.assertAlmostEqual(
            result.mixed_temperature_c, (10.0 * 1 + 30.0 * 3) / 4, places=10
        )
        self.assertEqual(result.mixed_relative_humidity, 0.0)

    def test_differing_humidity_weighted_and_back_solved(self):
        result = evaluate_scheme(
            [Inlet(10.0, 0.8, 1.0), Inlet(30.0, 0.4, 2.0)], self.table
        )
        self.assertTrue(result.valid)
        s1 = inlet_state(Inlet(10.0, 0.8, 1.0), self.table)
        s2 = inlet_state(Inlet(30.0, 0.4, 2.0), self.table)
        w_mix = (s1.humidity_ratio + 2 * s2.humidity_ratio) / 3
        h_mix = (s1.enthalpy + 2 * s2.enthalpy) / 3
        self.assertAlmostEqual(result.mixed_humidity_ratio, w_mix, places=12)
        self.assertAlmostEqual(result.mixed_enthalpy, h_mix, places=10)
        self.assertAlmostEqual(
            result.mixed_temperature_c,
            temperature_from_enthalpy(h_mix, w_mix),
            places=10,
        )
        p_w = vapour_pressure_from_humidity_ratio(w_mix, 101.325)
        self.assertAlmostEqual(result.mixed_vapour_pressure, p_w, places=10)
        self.assertLess(result.mixed_relative_humidity, 1.0)

    def test_balance_residuals_are_zero(self):
        result = evaluate_scheme(
            [Inlet(10.0, 0.8, 1.0), Inlet(30.0, 0.4, 2.0)], self.table
        )
        for key in ("dry_air_flow", "water_flow", "enthalpy_flow"):
            self.assertAlmostEqual(result.residuals[key], 0.0, places=9)
        self.assertAlmostEqual(result.residuals["dry_air_in"], 3.0, places=12)

    def test_supersaturated_mix_is_flagged_not_clamped(self):
        result = evaluate_scheme(
            [Inlet(0.0, 1.0, 1.0), Inlet(40.0, 1.0, 1.0)], self.table
        )
        self.assertFalse(result.valid)
        self.assertTrue(result.condensation_required)
        self.assertGreater(result.mixed_relative_humidity, 1.0)
        self.assertIsNotNone(result.reason)

    def test_single_inlet_round_trip(self):
        result = evaluate_scheme([Inlet(20.0, 0.6, 2.5)], self.table)
        self.assertTrue(result.valid)
        state = inlet_state(Inlet(20.0, 0.6, 2.5), self.table)
        self.assertAlmostEqual(result.mixed_temperature_c, 20.0, places=10)
        self.assertAlmostEqual(result.mixed_humidity_ratio, state.humidity_ratio, places=12)
        self.assertAlmostEqual(result.mixed_relative_humidity, 0.6, places=10)


class AuditAndCliTests(unittest.TestCase):
    def setUp(self):
        self.table = PropertyTable(101.325, TEMPS, PSATS)

    def _config(self):
        return {
            "property_table": {
                "total_pressure_kpa": 101.325,
                "temperatures_c": list(TEMPS),
                "saturation_pressures_kpa": list(PSATS),
            },
            "schemes": [
                {"name": "ok", "inlets": [
                    {"temperature_c": 20, "relative_humidity": 0.5,
                     "dry_air_flow_kg_s": 1.0}]},
                {"name": "fog", "inlets": [
                    {"temperature_c": 0, "relative_humidity": 1.0,
                     "dry_air_flow_kg_s": 1.0},
                    {"temperature_c": 40, "relative_humidity": 1.0,
                     "dry_air_flow_kg_s": 1.0}]},
                {"name": "broken", "inlets": [
                    {"temperature_c": 20, "relative_humidity": 1.5,
                     "dry_air_flow_kg_s": 1.0}]},
            ],
        }

    def test_one_invalid_scheme_does_not_block_others(self):
        table, schemes = parse_config(self._config())
        reports = run_audit(table, schemes)
        self.assertEqual([r.name for r in reports], ["ok", "fog", "broken"])
        self.assertTrue(reports[0].ok and reports[0].result.valid)
        self.assertTrue(reports[1].ok)
        self.assertTrue(reports[1].result.condensation_required)
        self.assertFalse(reports[2].ok)
        self.assertIn("relative humidity", reports[2].error)
        rows = [report_to_row(r) for r in reports]
        self.assertEqual(len(rows[0]), len(CSV_HEADER))
        payload = [report_to_dict(r) for r in reports]
        json.dumps(payload)

    def test_bad_config_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({"property_table": {}, "schemes": []})

    def test_cli_writes_csv_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = os.path.join(tmp, "config.json")
            csv_path = os.path.join(tmp, "out.csv")
            json_path = os.path.join(tmp, "out.json")
            with open(cfg_path, "w", encoding="utf-8") as handle:
                json.dump(self._config(), handle)
            code = cli_main([cfg_path, "--csv", csv_path, "--json", json_path])
            self.assertEqual(code, 0)
            with open(csv_path, encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], list(CSV_HEADER))
            self.assertEqual(len(rows), 4)
            with open(json_path, encoding="utf-8") as handle:
                payload = json.load(handle)
            self.assertEqual(payload["scheme_count"], 3)
            self.assertEqual(payload["schemes"][2]["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
