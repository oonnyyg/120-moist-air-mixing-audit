"""Saturation-pressure property table with piecewise-linear interpolation."""

from __future__ import annotations

import math
from dataclasses import dataclass


class PropertyTableError(ValueError):
    """Raised when the saturation-pressure table or total pressure is invalid."""


@dataclass(frozen=True)
class PropertyTable:
    """Saturation water-vapour pressure table valid at one total pressure.

    Temperatures are in degrees Celsius and pressures in kPa. Both sequences
    must be strictly increasing, and the total pressure must be greater than
    every tabulated saturation pressure.
    """

    total_pressure: float
    temperatures: tuple[float, ...]
    saturation_pressures: tuple[float, ...]

    def __post_init__(self) -> None:
        if not _is_finite(self.total_pressure) or self.total_pressure <= 0:
            raise PropertyTableError("total pressure must be a positive finite kPa value")
        if len(self.temperatures) < 2:
            raise PropertyTableError("at least two table points are required")
        if len(self.temperatures) != len(self.saturation_pressures):
            raise PropertyTableError("temperature and saturation pressure lengths differ")
        if not all(_is_finite(t) for t in self.temperatures):
            raise PropertyTableError("all temperatures must be finite")
        if not all(_is_finite(p) for p in self.saturation_pressures):
            raise PropertyTableError("all saturation pressures must be finite")
        if any(b <= a for a, b in zip(self.temperatures, self.temperatures[1:])):
            raise PropertyTableError("temperatures must be strictly increasing")
        if any(b <= a for a, b in zip(self.saturation_pressures, self.saturation_pressures[1:])):
            raise PropertyTableError("saturation pressures must be strictly increasing")
        if any(p <= 0 for p in self.saturation_pressures):
            raise PropertyTableError("saturation pressures must be positive")
        if self.total_pressure <= max(self.saturation_pressures):
            raise PropertyTableError(
                "total pressure must be greater than every tabulated saturation pressure"
            )

    @property
    def t_min(self) -> float:
        return self.temperatures[0]

    @property
    def t_max(self) -> float:
        return self.temperatures[-1]

    def saturation_pressure(self, temperature: float) -> float:
        """Piecewise-linear interpolation of p_ws(t); out-of-range is rejected."""
        if not _is_finite(temperature):
            raise PropertyTableError("temperature must be finite")
        if temperature < self.t_min or temperature > self.t_max:
            raise PropertyTableError(
                f"temperature {temperature} C is outside the table range "
                f"[{self.t_min}, {self.t_max}]"
            )
        ts = self.temperatures
        ps = self.saturation_pressures
        lo, hi = 0, len(ts) - 1
        if temperature == ts[hi]:
            return ps[hi]
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if ts[mid] <= temperature:
                lo = mid
            else:
                hi = mid
        fraction = (temperature - ts[lo]) / (ts[hi] - ts[lo])
        return ps[lo] + fraction * (ps[hi] - ps[lo])

    def invert_saturation_pressure(self, pressure: float) -> float:
        """Invert the table: temperature whose saturation pressure equals *pressure*."""
        if not _is_finite(pressure) or pressure <= 0:
            raise PropertyTableError("vapour pressure must be a positive finite value")
        ps = self.saturation_pressures
        if pressure < ps[0] or pressure > ps[-1]:
            raise PropertyTableError(
                f"vapour pressure {pressure} kPa is outside the table range "
                f"[{ps[0]}, {ps[-1]}]"
            )
        ts = self.temperatures
        lo, hi = 0, len(ps) - 1
        if pressure == ps[hi]:
            return ts[hi]
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if ps[mid] <= pressure:
                lo = mid
            else:
                hi = mid
        fraction = (pressure - ps[lo]) / (ps[hi] - ps[lo])
        return ts[lo] + fraction * (ts[hi] - ts[lo])


def _is_finite(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))
