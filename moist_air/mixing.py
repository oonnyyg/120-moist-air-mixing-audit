"""Mixing of moist air streams on a dry-air mass basis."""

from __future__ import annotations

from dataclasses import dataclass, field

from .physics import (
    SaturationTable,
    enthalpy,
    humidity_ratio,
    temperature_from_enthalpy,
    vapor_pressure_from_w,
    _require_finite,
)


@dataclass(frozen=True)
class InletStream:
    name: str
    temperature: float      # degC
    relative_humidity: float  # 0..1
    mass_flow_dry: float    # kg/s dry air, > 0


@dataclass
class StreamState:
    name: str
    temperature: float
    relative_humidity: float
    mass_flow_dry: float
    vapor_pressure: float
    humidity_ratio: float
    enthalpy: float
    dry_air_flow: float
    vapor_flow: float
    enthalpy_flow: float


@dataclass
class MixResult:
    name: str
    valid: bool
    error: str | None = None
    inlets: list[StreamState] = field(default_factory=list)
    mixed: StreamState | None = None
    supersaturated: bool = False
    residuals: dict[str, float] = field(default_factory=dict)


def _inlet_state(s: InletStream, table: SaturationTable, p_total: float) -> StreamState:
    t = _require_finite("temperature", s.temperature)
    rh = _require_finite("relative_humidity", s.relative_humidity)
    m = _require_finite("mass_flow_dry", s.mass_flow_dry)
    if not 0.0 <= rh <= 1.0:
        raise ValueError(f"stream {s.name}: relative humidity {rh} outside [0, 1]")
    if m <= 0:
        raise ValueError(f"stream {s.name}: dry air mass flow must be positive")
    p_sat = table.saturation_pressure(t)
    p_v = rh * p_sat
    w = humidity_ratio(p_v, p_total)
    h = enthalpy(t, w)
    return StreamState(
        name=s.name, temperature=t, relative_humidity=rh, mass_flow_dry=m,
        vapor_pressure=p_v, humidity_ratio=w, enthalpy=h,
        dry_air_flow=m, vapor_flow=m * w, enthalpy_flow=m * h,
    )


def mix_streams(
    name: str,
    inlets: list[InletStream],
    table: SaturationTable,
    p_total: float,
) -> MixResult:
    try:
        if len(inlets) < 2:
            raise ValueError("a scheme needs at least two inlet streams")
        states = [_inlet_state(s, table, p_total) for s in inlets]
    except ValueError as exc:
        return MixResult(name=name, valid=False, error=str(exc))

    m_dry = sum(s.dry_air_flow for s in states)
    m_vap = sum(s.vapor_flow for s in states)
    h_flow = sum(s.enthalpy_flow for s in states)

    w_mix = m_vap / m_dry
    h_mix = h_flow / m_dry
    t_mix = temperature_from_enthalpy(h_mix, w_mix)

    supersaturated = False
    error = None
    try:
        p_sat_mix = table.saturation_pressure(t_mix)
    except ValueError as exc:
        return MixResult(name=name, valid=False, error=str(exc), inlets=states)
    p_v_mix = vapor_pressure_from_w(w_mix, p_total)
    rh_mix = p_v_mix / p_sat_mix
    if rh_mix > 1.0:
        supersaturated = True

    mixed = StreamState(
        name=f"{name}-mixed", temperature=t_mix, relative_humidity=rh_mix,
        mass_flow_dry=m_dry, vapor_pressure=p_v_mix, humidity_ratio=w_mix,
        enthalpy=h_mix, dry_air_flow=m_dry, vapor_flow=m_vap,
        enthalpy_flow=h_flow,
    )
    residuals = {
        "dry_air_flow": m_dry - sum(s.dry_air_flow for s in states),
        "vapor_flow": m_vap - sum(s.vapor_flow for s in states),
        "enthalpy_flow": h_flow - sum(s.enthalpy_flow for s in states),
    }
    return MixResult(
        name=name, valid=True, error=error, inlets=states, mixed=mixed,
        supersaturated=supersaturated, residuals=residuals,
    )
