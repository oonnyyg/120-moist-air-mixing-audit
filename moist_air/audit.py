"""Load JSON configurations and audit multiple schemes independently."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from .properties import PropertyTable, PropertyTableError
from .psychrometry import Inlet, InletError, MixedResult, evaluate_scheme


class ConfigError(ValueError):
    """Raised when the JSON configuration is structurally invalid."""


@dataclass(frozen=True)
class SchemeReport:
    name: str
    result: MixedResult | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.error is None


def load_config(path: str) -> tuple[PropertyTable, list[tuple[str, list[Inlet]]]]:
    """Parse a config file into a shared table and named schemes."""
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return parse_config(data)


def parse_config(data: object) -> tuple[PropertyTable, list[tuple[str, list[Inlet]]]]:
    if not isinstance(data, dict):
        raise ConfigError("top-level config must be a JSON object")
    table_node = data.get("property_table")
    if not isinstance(table_node, dict):
        raise ConfigError("missing 'property_table' object")
    try:
        total_pressure = float(table_node["total_pressure_kpa"])
        temps = [float(v) for v in table_node["temperatures_c"]]
        psats = [float(v) for v in table_node["saturation_pressures_kpa"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"property table fields invalid: {exc}") from exc
    if not all(math.isfinite(v) for v in temps + psats + [total_pressure]):
        raise ConfigError("property table values must be finite")
    try:
        table = PropertyTable(total_pressure, tuple(temps), tuple(psats))
    except PropertyTableError as exc:
        raise ConfigError(str(exc)) from exc

    schemes_node = data.get("schemes")
    if not isinstance(schemes_node, list) or not schemes_node:
        raise ConfigError("'schemes' must be a non-empty list")
    schemes: list[tuple[str, list[Inlet]]] = []
    for index, node in enumerate(schemes_node):
        if not isinstance(node, dict):
            raise ConfigError(f"scheme #{index + 1} must be an object")
        name = str(node.get("name") or f"scheme-{index + 1}")
        inlets_node = node.get("inlets")
        if not isinstance(inlets_node, list) or not inlets_node:
            raise ConfigError(f"scheme {name!r} needs a non-empty 'inlets' list")
        inlets: list[Inlet] = []
        for j, item in enumerate(inlets_node):
            try:
                inlets.append(
                    Inlet(
                        temperature_c=float(item["temperature_c"]),
                        relative_humidity=float(item["relative_humidity"]),
                        dry_air_flow=float(item["dry_air_flow_kg_s"]),
                        label=str(item.get("label") or f"inlet-{j + 1}"),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ConfigError(
                    f"scheme {name!r} inlet #{j + 1} invalid: {exc}"
                ) from exc
        schemes.append((name, inlets))
    return table, schemes


def run_audit(
    table: PropertyTable, schemes: list[tuple[str, list[Inlet]]]
) -> list[SchemeReport]:
    """Evaluate every scheme; a failure in one never blocks the others."""
    reports: list[SchemeReport] = []
    for name, inlets in schemes:
        try:
            result = evaluate_scheme(inlets, table)
            reports.append(SchemeReport(name=name, result=result, error=None))
        except (InletError, PropertyTableError, OverflowError, ZeroDivisionError) as exc:
            reports.append(SchemeReport(name=name, result=None, error=str(exc)))
    return reports


CSV_HEADER = (
    "scheme",
    "status",
    "condensation_required",
    "mixed_temperature_c",
    "mixed_relative_humidity",
    "mixed_humidity_ratio_kg_per_kg_da",
    "mixed_enthalpy_kj_per_kg_da",
    "mixed_vapour_pressure_kpa",
    "mixed_saturation_pressure_kpa",
    "mixed_dry_air_flow_kg_s",
    "dry_air_residual_kg_s",
    "water_residual_kg_s",
    "enthalpy_residual_kw",
    "reason",
)


def report_to_row(report: SchemeReport) -> list[str]:
    """One CSV row per scheme, regardless of validity."""
    if report.error is not None:
        return [
            report.name, "invalid", "", "", "", "", "", "", "", "", "", "", "",
            report.error,
        ]
    r = report.result
    assert r is not None
    if r.valid:
        status = "valid"
        reason = ""
    else:
        status = "condensation_required"
        reason = r.reason or ""
    return [
        report.name,
        status,
        str(r.condensation_required),
        _num(r.mixed_temperature_c),
        _num(r.mixed_relative_humidity),
        _num(r.mixed_humidity_ratio),
        _num(r.mixed_enthalpy),
        _num(r.mixed_vapour_pressure),
        _num(r.mixed_saturation_pressure),
        _num(r.mixed_dry_air_flow),
        _num(r.residuals["dry_air_flow"]),
        _num(r.residuals["water_flow"]),
        _num(r.residuals["enthalpy_flow"]),
        reason,
    ]


def report_to_dict(report: SchemeReport) -> dict[str, object]:
    """Structured JSON node, including inlet-level state and residuals."""
    if report.error is not None:
        return {"name": report.name, "status": "invalid", "reason": report.error}
    r = report.result
    assert r is not None
    node: dict[str, object] = {
        "name": report.name,
        "status": "valid" if r.valid else "condensation_required",
        "condensation_required": r.condensation_required,
        "reason": r.reason,
        "mixed_state": {
            "dry_air_flow_kg_s": r.mixed_dry_air_flow,
            "humidity_ratio_kg_per_kg_da": r.mixed_humidity_ratio,
            "enthalpy_kj_per_kg_da": r.mixed_enthalpy,
            "temperature_c": r.mixed_temperature_c,
            "vapour_pressure_kpa": r.mixed_vapour_pressure,
            "saturation_pressure_kpa": r.mixed_saturation_pressure,
            "relative_humidity": r.mixed_relative_humidity,
        },
        "residuals": {
            "dry_air_flow_kg_s": r.residuals["dry_air_flow"],
            "water_flow_kg_s": r.residuals["water_flow"],
            "enthalpy_flow_kw": r.residuals["enthalpy_flow"],
        },
        "inlets": [
            {
                "label": label,
                "temperature_c": state.temperature_c,
                "relative_humidity": state.relative_humidity,
                "vapour_pressure_kpa": state.vapour_pressure,
                "humidity_ratio_kg_per_kg_da": state.humidity_ratio,
                "enthalpy_kj_per_kg_da": state.enthalpy,
            }
            for label, state in r.inlet_states
        ],
    }
    return node


def _num(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.10g}"
