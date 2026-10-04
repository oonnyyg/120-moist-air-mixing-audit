import math
import unittest

from moist_air.physics import (
    SaturationTable,
    enthalpy,
    humidity_ratio,
    temperature_from_enthalpy,
    vapor_pressure_from_w,
)


class SaturationTableTests(unittest.TestCase):
    def test_interpolation_midpoint(self):
        table = SaturationTable.from_lists([0.0, 10.0, 20.0], [0.6, 1.2, 2.3])
        self.assertAlmostEqual(table.saturation_pressure(5.0), 0.9)
        self.assertAlmostEqual(table.saturation_pressure(0.0), 0.6)
        self.assertAlmostEqual(table.saturation_pressure(20.0), 2.3)

    def test_rejects_out_of_range(self):
        table = SaturationTable.from_lists([0.0, 10.0], [0.6, 1.2])
        with self.assertRaises(ValueError):
            table.saturation_pressure(-0.1)
        with self.assertRaises(ValueError):
            table.saturation_pressure(10.1)

    def test_rejects_non_finite(self):
        table = SaturationTable.from_lists([0.0, 10.0], [0.6, 1.2])
        for bad in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                table.saturation_pressure(bad)

    def test_rejects_unsorted_or_short_tables(self):
        with self.assertRaises(ValueError):
            SaturationTable.from_lists([10.0, 0.0], [0.6, 1.2])
        with self.assertRaises(ValueError):
            SaturationTable.from_lists([0.0, 10.0], [1.2, 0.6])
        with self.assertRaises(ValueError):
            SaturationTable.from_lists([0.0], [0.6])
        with self.assertRaises(ValueError):
            SaturationTable.from_lists([0.0, 10.0], [0.6])


class PropertyTests(unittest.TestCase):
    def test_humidity_ratio_round_trip(self):
        w = humidity_ratio(1.5, 101.325)
        self.assertAlmostEqual(w, 0.621945 * 1.5 / (101.325 - 1.5))
        self.assertAlmostEqual(vapor_pressure_from_w(w, 101.325), 1.5)

    def test_humidity_ratio_rejects_bad_vapor_pressure(self):
        with self.assertRaises(ValueError):
            humidity_ratio(101.325, 101.325)
        with self.assertRaises(ValueError):
            humidity_ratio(-0.1, 101.325)

    def test_enthalpy_formula_and_inverse(self):
        h = enthalpy(25.0, 0.010)
        self.assertAlmostEqual(h, 1.006 * 25.0 + 0.010 * (2501.0 + 1.86 * 25.0))
        self.assertAlmostEqual(temperature_from_enthalpy(h, 0.010), 25.0)

    def test_dry_air_zero_humidity(self):
        self.assertAlmostEqual(humidity_ratio(0.0, 101.325), 0.0)
        self.assertAlmostEqual(enthalpy(30.0, 0.0), 1.006 * 30.0)


if __name__ == "__main__":
    unittest.main()
