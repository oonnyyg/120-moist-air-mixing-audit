"""Moist air property helpers (standard library only).

Units: temperature degC, pressure kPa, humidity ratio kg/kg dry air,
enthalpy kJ/kg dry air.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

W_RATIO = 0.621945  # water/dry-air molar mass ratio
CP_DRY = 1.006      # dry air specific heat kJ/(kg K)
H_FG0 = 2501.0      # latent heat at 0 degC kJ/kg
CP_VAP = 1.86       # water vapor specific heat kJ/(kg K)


def _require_finite(name: str, value: float) -> float:
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return v


@dataclass(frozen=True)
class SaturationTable:
    """Saturation vapor pressure table with linear interpolation."""

    temperatures: tuple[float, ...]
    pressures: tuple[float, ...]

    @classmethod
    def from_lists(cls, temperatures, pressures) -> "SaturationTable":
        temps = tuple(_require_finite("temperature", t) for t in temperatures)
        psats = tuple(_require_finite("saturation pressure", p) for p in pressures)
        if len(temps) < 2 or len(temps) != len(psats):
            raise ValueError("table needs >=2 points and equal lengths")
        for a, b in zip(temps, temps[1:]):
            if not b > a:
                raise ValueError("temperatures must be strictly increasing")
        for a, b in zip(psats, psats[1:]):
            if not b > a:
                raise ValueError("pressures must be strictly increasing")
        if psats[0] <= 0:
            raise ValueError("pressures must be positive")
        return cls(temps, psats)

    def saturation_pressure(self, t: float) -> float:
        t = _require_finite("temperature", t)
        temps, psats = self.temperatures, self.pressures
        if t < temps[0] or t > temps[-1]:
            raise ValueError(
                f"temperature {t} degC outside table range "
                f"[{temps[0]}, {temps[-1]}] degC"
            )
        for i in range(len(temps) - 1):
            t0, t1 = temps[i], temps[i + 1]
            if t0 <= t <= t1:
                frac = (t - t0) / (t1 - t0)
                return psats[i] + frac * (psats[i + 1] - psats[i])
        return psats[-1]


def humidity_ratio(p_vapor: float, p_total: float) -> float:
    """W = 0.621945 * pv / (p - pv)."""
    if p_vapor < 0 or p_vapor >= p_total:
        raise ValueError(
            f"vapor pressure {p_vapor} must satisfy 0 <= pv < total {p_total}"
        )
    return W_RATIO * p_vapor / (p_total - p_vapor)


def enthalpy(t: float, w: float) -> float:
    """h = 1.006 t + W (2501 + 1.86 t), kJ/kg dry air."""
    return CP_DRY * t + w * (H_FG0 + CP_VAP * t)


def vapor_pressure_from_w(w: float, p_total: float) -> float:
    return p_total * w / (W_RATIO + w)


def temperature_from_enthalpy(h: float, w: float) -> float:
    """t = (h - 2501 W) / (1.006 + 1.86 W)."""
    denom = CP_DRY + CP_VAP * w
    return (h - H_FG0 * w) / denom
