import unittest

from moist_air.mixing import InletStream, mix_streams
from moist_air.physics import SaturationTable, enthalpy, humidity_ratio

# Simplified saturation table, roughly matching real moist air (kPa).
TABLE = SaturationTable.from_lists(
    [0.0, 10.0, 20.0, 30.0, 40.0],
    [0.611, 1.228, 2.339, 4.246, 7.384],
)
P_TOTAL = 101.325


def make_inlet(name, t, rh, m):
    return InletStream(name=name, temperature=t, relative_humidity=rh,
                       mass_flow_dry=m)


class MixingTests(unittest.TestCase):
    def test_two_dry_streams_energy_balance(self):
        # RH = 0: pure sensible mixing, W = 0 everywhere.
        result = mix_streams("dry", [
            make_inlet("a", 10.0, 0.0, 2.0),
            make_inlet("b", 30.0, 0.0, 1.0),
        ], TABLE, P_TOTAL)
        self.assertTrue(result.valid)
        self.assertAlmostEqual(result.mixed.humidity_ratio, 0.0)
        # h = 1.006 t, flow-weighted: t = (2*10 + 1*30) / 3
        self.assertAlmostEqual(result.mixed.temperature, (2 * 10.0 + 30.0) / 3.0)
        self.assertAlmostEqual(result.mixed.relative_humidity, 0.0)
        for value in result.residuals.values():
            self.assertAlmostEqual(value, 0.0)

    def test_different_humidity_weighted_mix(self):
        inlets = [
            make_inlet("humid", 30.0, 0.8, 1.0),
            make_inlet("dry", 20.0, 0.2, 3.0),
        ]
        result = mix_streams("mix", inlets, TABLE, P_TOTAL)
        self.assertTrue(result.valid)
        self.assertFalse(result.supersaturated)

        ws, hs = [], []
        for s in inlets:
            pv = s.relative_humidity * TABLE.saturation_pressure(s.temperature)
            w = humidity_ratio(pv, P_TOTAL)
            ws.append(w)
            hs.append(enthalpy(s.temperature, w))
        w_mix = (1.0 * ws[0] + 3.0 * ws[1]) / 4.0
        h_mix = (1.0 * hs[0] + 3.0 * hs[1]) / 4.0
        self.assertAlmostEqual(result.mixed.humidity_ratio, w_mix)
        self.assertAlmostEqual(result.mixed.enthalpy, h_mix)
        # Temperature must come from inverting h(W, t), not averaging.
        t_naive = (1.0 * 30.0 + 3.0 * 20.0) / 4.0
        self.assertNotAlmostEqual(result.mixed.temperature, t_naive, places=6)
        self.assertLess(result.mixed.relative_humidity, 1.0)
        for value in result.residuals.values():
            self.assertAlmostEqual(value, 0.0)

    def test_supersaturated_mix_flagged_not_clipped(self):
        # Warm saturated air mixed with cold saturated air crosses saturation.
        result = mix_streams("fog", [
            make_inlet("warm", 30.0, 1.0, 1.0),
            make_inlet("cold", 0.0, 1.0, 1.0),
        ], TABLE, P_TOTAL)
        self.assertTrue(result.valid)
        self.assertTrue(result.supersaturated)
        self.assertGreater(result.mixed.relative_humidity, 1.0)

    def test_invalid_streams_reported_independently(self):
        bad_rh = mix_streams("bad-rh", [
            make_inlet("a", 20.0, 1.5, 1.0),
            make_inlet("b", 20.0, 0.5, 1.0),
        ], TABLE, P_TOTAL)
        self.assertFalse(bad_rh.valid)
        self.assertIn("relative humidity", bad_rh.error)

        bad_flow = mix_streams("bad-flow", [
            make_inlet("a", 20.0, 0.5, 0.0),
            make_inlet("b", 20.0, 0.5, 1.0),
        ], TABLE, P_TOTAL)
        self.assertFalse(bad_flow.valid)

        out_of_range = mix_streams("oor", [
            make_inlet("a", 50.0, 0.5, 1.0),
            make_inlet("b", 20.0, 0.5, 1.0),
        ], TABLE, P_TOTAL)
        self.assertFalse(out_of_range.valid)

        too_few = mix_streams("one", [make_inlet("a", 20.0, 0.5, 1.0)],
                              TABLE, P_TOTAL)
        self.assertFalse(too_few.valid)

        # One invalid scheme does not block a valid one.
        good = mix_streams("good", [
            make_inlet("a", 20.0, 0.5, 1.0),
            make_inlet("b", 25.0, 0.5, 1.0),
        ], TABLE, P_TOTAL)
        self.assertTrue(good.valid)


if __name__ == "__main__":
    unittest.main()
