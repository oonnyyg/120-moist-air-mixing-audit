# Moist Air Mixing Audit

Offline comparison tool for ventilation schemes that mix several moist air
streams. All balances are computed on a **dry air mass basis**. The tool does
no equipment selection and no real control simulation. Standard library only.

## Usage

```
python -m moist_air examples/config.json --csv conditions.csv --json balance.json
```

- `--csv`: condition table with one row per inlet and per mixed state.
- `--json`: balance report with per-scheme states and flow residuals.

Invalid schemes are reported independently and do not block other schemes.

## Configuration

```json
{
  "total_pressure_kpa": 101.325,
  "saturation_table": {
    "temperatures_c": [0.0, 10.0, 20.0],
    "pressures_kpa": [0.611, 1.228, 2.339]
  },
  "schemes": [
    {
      "name": "scheme-a",
      "inlets": [
        {"name": "fresh", "temperature_c": 35.0,
         "relative_humidity": 0.6, "mass_flow_dry_kg_s": 0.8}
      ]
    }
  ]
}
```

Rules:

- The saturation table needs at least two points; temperatures and
  saturation pressures must both be strictly increasing. Pressures are
  positive, and the total pressure must exceed every table entry.
- Saturation pressure is found by piecewise linear interpolation;
  out-of-range temperatures and non-finite numbers are rejected.
- Each inlet gives temperature (degC), relative humidity (0..1) and a
  positive dry air mass flow (kg/s). All inlets share one table and one
  total pressure.

## Formulas and units

Units: temperature `t` in degC, pressures in kPa, humidity ratio `W` in
kg/kg dry air, enthalpy `h` in kJ/kg dry air, flows in kg/s (enthalpy flow
in kW).

- Vapor pressure: `pv = RH * psat(t)`
- Humidity ratio: `W = 0.621945 * pv / (p_total - pv)`
- Enthalpy: `h = 1.006 t + W (2501 + 1.86 t)`
- Mixing (dry-air-flow weighted):
  `W_mix = sum(m_i W_i) / sum(m_i)`, `h_mix = sum(m_i h_i) / sum(m_i)`
- Mixed temperature is recovered by inverting the enthalpy relation,
  `t = (h - 2501 W) / (1.006 + 1.86 W)`; temperature and humidity are
  never averaged directly.
- Mixed relative humidity: `RH = pv(W_mix) / psat(t_mix)`.

## Balances and supersaturation

Dry air, water vapor and enthalpy flows are checked as
`mixed - sum(inlets)` and reported as residuals (numerically zero).

If the mixed state exceeds saturation (`RH > 1`), the scheme is flagged
`supersaturated` and marked as needing condensation handling. The relative
humidity is **not** clipped to 1.0 and condensate is not simulated.

## Tests

```
python -m unittest discover -s tests -v
```

Covers dry-air mixing, unequal humidity ratios, supersaturated mixing,
table validation and the CLI end to end.
