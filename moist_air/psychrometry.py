"""Per-inlet moist-air state and multi-inlet mixing calculations."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .properties import PropertyTable, PropertyTableError

HUMIDITY_RATIO_CONSTANT = 0.621945
DRY_AIR_CP = 1.006
WATER_VAPOUR_CP = 1.86
WATER_ENTHALPY_0C = 2501.0


class InletError(ValueError):
    """Raised when an inlet specification is invalid."""


@dataclass(frozen=True)
class Inlet:
    """One inlet air stream.

    temperature_c: dry-bulb temperature in degrees Celsius.
    relative_humidity: dimensionless 0..1 (phi = p_w / p_ws).
    dry_air_flow: dry-air mass flow in kg/s (any consistent unit works).
    """

    temperature_c: float
    relative_humidity: float
    dry_air_flow: float
    label: str = ""


@dataclass(frozen=True)
class AirState:
    """Thermodynamic state of one air stream per kg of dry air."""

    temperature_c: float
    relative_humidity: float
    vapour_pressure: float
    humidity_ratio: float
    enthalpy: float


def _finite(value: float, name: str) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise InletError(f"{name} must be a finite number")
    return float(value)


def validate_inlet(inlet: Inlet) -> None:
    t = _finite(inlet.temperature_c, "temperature")
    rh = _finite(inlet.relative_humidity, "relative humidity")
    flow = _finite(inlet.dry_air_flow, "dry-air flow")
    if not (0.0 <= rh <= 1.0):
        raise InletError(f"relative humidity {rh} is outside [0, 1]")
    if flow <= 0.0:
        raise InletError(f"dry-air flow {flow} must be positive")


def inlet_state(inlet: Inlet, table: PropertyTable) -> AirState:
    """Compute vapour pressure, humidity ratio and enthalpy for one inlet."""
    validate_inlet(inlet)
    t = float(inlet.temperature_c)
    phi = float(inlet.relative_humidity)
    p_ws = table.saturation_pressure(t)
    p_w = phi * p_ws
    if p_w >= table.total_pressure:
        raise InletError(
            "water vapour pressure reaches or exceeds the total pressure"
        )
    w = HUMIDITY_RATIO_CONSTANT * p_w / (table.total_pressure - p_w)
    h = DRY_AIR_CP * t + w * (WATER_ENTHALPY_0C + WATER_VAPOUR_CP * t)
    return AirState(
        temperature_c=t,
        relative_humidity=phi,
        vapour_pressure=p_w,
        humidity_ratio=w,
        enthalpy=h,
    )


def humidity_ratio_from_vapour_pressure(p_w: float, total_pressure: float) -> float:
    """w = 0.621945 * p_w / (p - p_w)."""
    if p_w <= 0:
        return 0.0
    if p_w >= total_pressure:
        raise InletError("vapour pressure must stay below the total pressure")
    return HUMIDITY_RATIO_CONSTANT * p_w / (total_pressure - p_w)


def vapour_pressure_from_humidity_ratio(w: float, total_pressure: float) -> float:
    """Invert the humidity-ratio formula."""
    if w <= 0:
        return 0.0
    return total_pressure * w / (HUMIDITY_RATIO_CONSTANT + w)


def enthalpy_per_kg(temperature_c: float, humidity_ratio: float) -> float:
    """h = 1.006*t + w*(2501 + 1.86*t), kJ per kg of dry air."""
    return (
        DRY_AIR_CP * temperature_c
        + humidity_ratio * (WATER_ENTHALPY_0C + WATER_VAPOUR_CP * temperature_c)
    )


def temperature_from_enthalpy(enthalpy: float, humidity_ratio: float) -> float:
    """Invert h(t, w) for t in degrees Celsius."""
    denominator = DRY_AIR_CP + WATER_VAPOUR_CP * humidity_ratio
    return (enthalpy - WATER_ENTHALPY_0C * humidity_ratio) / denominator


@dataclass(frozen=True)
class MixedResult:
    """Outcome of mixing several inlet streams."""

    valid: bool
    reason: str | None
    mixed_dry_air_flow: float
    mixed_humidity_ratio: float
    mixed_enthalpy: float
    mixed_temperature_c: float | None
    mixed_vapour_pressure: float | None
    mixed_saturation_pressure: float | None
    mixed_relative_humidity: float | None
    condensation_required: bool
    residuals: dict[str, float]
    inlet_states: tuple[tuple[str, AirState], ...]


def evaluate_scheme(inlets: list[Inlet], table: PropertyTable) -> MixedResult:
    """Mix inlets by dry-air-weighted humidity ratio and enthalpy.

    The mixed temperature is back-solved from h_mix(T, w_mix); temperatures and
    relative humidities are never averaged directly. A scheme whose mixed state
    lies above saturation is flagged for condensation handling instead of
    clamping the relative humidity to 1.
    """
    if not inlets:
        raise InletError("a scheme needs at least one inlet stream")

    labelled: tuple[tuple[str, AirState], ...] = tuple(
        (
            inlet.label or f"inlet-{index + 1}",
            inlet_state(inlet, table),
        )
        for index, inlet in enumerate(inlets)
    )

    flows = tuple(float(i.dry_air_flow) for i in inlets)
    total_da = math.fsum(flows)
    water_flows = tuple(
        flow * state.humidity_ratio for flow, (_, state) in zip(flows, labelled)
    )
    enthalpy_flows = tuple(
        flow * state.enthalpy for flow, (_, state) in zip(flows, labelled)
    )
    w_mix = math.fsum(water_flows) / total_da
    h_mix = math.fsum(enthalpy_flows) / total_da
    t_mix = temperature_from_enthalpy(h_mix, w_mix)
    p_w_mix = vapour_pressure_from_humidity_ratio(w_mix, table.total_pressure)

    residuals = _residuals(
        flows, labelled, total_da, w_mix, h_mix, water_flows, enthalpy_flows
    )

    try:
        p_ws_mix = table.saturation_pressure(t_mix)
    except PropertyTableError:
        return MixedResult(
            valid=False,
            reason=(
                f"mixed temperature {t_mix:.3f} C falls outside the property "
                "table range; extend the table"
            ),
            mixed_dry_air_flow=total_da,
            mixed_humidity_ratio=w_mix,
            mixed_enthalpy=h_mix,
            mixed_temperature_c=t_mix,
            mixed_vapour_pressure=p_w_mix,
            mixed_saturation_pressure=None,
            mixed_relative_humidity=None,
            condensation_required=False,
            residuals=residuals,
            inlet_states=labelled,
        )

    phi_mix = p_w_mix / p_ws_mix if p_ws_mix > 0 else float("inf")
    oversaturated = phi_mix > 1.0
    return MixedResult(
        valid=not oversaturated,
        reason="mixed state is above saturation; condensation treatment required"
        if oversaturated
        else None,
        mixed_dry_air_flow=total_da,
        mixed_humidity_ratio=w_mix,
        mixed_enthalpy=h_mix,
        mixed_temperature_c=t_mix,
        mixed_vapour_pressure=p_w_mix,
        mixed_saturation_pressure=p_ws_mix,
        # Report the unclamped phi even above 1: it is an audit flag, not a
        # pretend operating point.
        mixed_relative_humidity=phi_mix,
        condensation_required=oversaturated,
        residuals=residuals,
        inlet_states=labelled,
    )


def _residuals(
    flows: tuple[float, ...],
    labelled: tuple[tuple[str, AirState], ...],
    total_da: float,
    w_mix: float,
    h_mix: float,
    water_flows: tuple[float, ...],
    enthalpy_flows: tuple[float, ...],
) -> dict[str, float]:
    """Balance residuals: sum(in) - mixed outgoing stream."""
    da_in = math.fsum(flows)
    water_in = math.fsum(water_flows)
    enthalpy_in = math.fsum(enthalpy_flows)
    return {
        "dry_air_flow": da_in - total_da,
        "water_flow": water_in - total_da * w_mix,
        "enthalpy_flow": enthalpy_in - total_da * h_mix,
        "dry_air_in": da_in,
        "water_in": water_in,
        "enthalpy_in": enthalpy_in,
    }
