"""JSON configuration loading and validation."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from .mixing import InletStream
from .physics import SaturationTable


@dataclass(frozen=True)
class Scheme:
    name: str
    inlets: list[InletStream]


@dataclass(frozen=True)
class Config:
    total_pressure: float  # kPa
    table: SaturationTable
    schemes: list[Scheme]


def _finite_number(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} must be a number, got {value!r}")
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"{what} must be finite, got {value!r}")
    return v


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    p_total = _finite_number(raw.get("total_pressure_kpa"), "total_pressure_kpa")
    if p_total <= 0:
        raise ValueError("total_pressure_kpa must be positive")

    tbl = raw.get("saturation_table")
    if not isinstance(tbl, dict):
        raise ValueError("config requires 'saturation_table'")
    table = SaturationTable.from_lists(
        [_finite_number(t, "table temperature") for t in tbl.get("temperatures_c", [])],
        [_finite_number(p, "table pressure") for p in tbl.get("pressures_kpa", [])],
    )
    if p_total <= table.pressures[-1]:
        raise ValueError(
            "total pressure must exceed every saturation pressure in the table"
        )

    schemes = []
    for i, item in enumerate(raw.get("schemes", [])):
        name = str(item.get("name", f"scheme-{i + 1}"))
        inlets = []
        for j, s in enumerate(item.get("inlets", [])):
            inlets.append(InletStream(
                name=str(s.get("name", f"inlet-{j + 1}")),
                temperature=_finite_number(s.get("temperature_c"), "temperature_c"),
                relative_humidity=_finite_number(
                    s.get("relative_humidity"), "relative_humidity"),
                mass_flow_dry=_finite_number(
                    s.get("mass_flow_dry_kg_s"), "mass_flow_dry_kg_s"),
            ))
        schemes.append(Scheme(name=name, inlets=inlets))
    if not schemes:
        raise ValueError("config requires at least one scheme")
    return Config(total_pressure=p_total, table=table, schemes=schemes)
