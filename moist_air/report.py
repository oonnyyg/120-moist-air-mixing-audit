"""CSV condition table and JSON balance report export."""

from __future__ import annotations

import csv
import json

from .mixing import MixResult

CSV_FIELDS = [
    "scheme", "stream", "role", "temperature_c", "relative_humidity",
    "vapor_pressure_kpa", "humidity_ratio_kg_per_kg", "enthalpy_kj_per_kg",
    "dry_air_flow_kg_s", "vapor_flow_kg_s", "enthalpy_flow_kw",
    "supersaturated",
]


def _row(scheme: str, state, role: str, supersaturated: bool) -> dict:
    return {
        "scheme": scheme,
        "stream": state.name,
        "role": role,
        "temperature_c": f"{state.temperature:.6f}",
        "relative_humidity": f"{state.relative_humidity:.6f}",
        "vapor_pressure_kpa": f"{state.vapor_pressure:.6f}",
        "humidity_ratio_kg_per_kg": f"{state.humidity_ratio:.8f}",
        "enthalpy_kj_per_kg": f"{state.enthalpy:.6f}",
        "dry_air_flow_kg_s": f"{state.dry_air_flow:.6f}",
        "vapor_flow_kg_s": f"{state.vapor_flow:.8f}",
        "enthalpy_flow_kw": f"{state.enthalpy_flow:.6f}",
        "supersaturated": "yes" if supersaturated else "no",
    }


def write_csv(results: list[MixResult], path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in results:
            if not r.valid:
                writer.writerow({
                    "scheme": r.name, "stream": "", "role": "invalid",
                    "temperature_c": "", "relative_humidity": "",
                    "vapor_pressure_kpa": "", "humidity_ratio_kg_per_kg": "",
                    "enthalpy_kj_per_kg": "", "dry_air_flow_kg_s": "",
                    "vapor_flow_kg_s": "", "enthalpy_flow_kw": "",
                    "supersaturated": "",
                })
                continue
            for s in r.inlets:
                writer.writerow(_row(r.name, s, "inlet", False))
            writer.writerow(_row(r.name, r.mixed, "mixed", r.supersaturated))


def _state_dict(state) -> dict:
    return {
        "name": state.name,
        "temperature_c": state.temperature,
        "relative_humidity": state.relative_humidity,
        "vapor_pressure_kpa": state.vapor_pressure,
        "humidity_ratio_kg_per_kg": state.humidity_ratio,
        "enthalpy_kj_per_kg": state.enthalpy,
        "dry_air_flow_kg_s": state.dry_air_flow,
        "vapor_flow_kg_s": state.vapor_flow,
        "enthalpy_flow_kw": state.enthalpy_flow,
    }


def build_report(results: list[MixResult], total_pressure: float) -> dict:
    schemes = []
    for r in results:
        entry = {"name": r.name, "valid": r.valid}
        if not r.valid:
            entry["error"] = r.error
        else:
            entry["inlets"] = [_state_dict(s) for s in r.inlets]
            entry["mixed"] = _state_dict(r.mixed)
            entry["supersaturated"] = r.supersaturated
            if r.supersaturated:
                entry["note"] = (
                    "mixed state exceeds saturation; condensation handling "
                    "required (not simulated)"
                )
            entry["balance_residuals"] = {
                "dry_air_flow_kg_s": r.residuals["dry_air_flow"],
                "vapor_flow_kg_s": r.residuals["vapor_flow"],
                "enthalpy_flow_kw": r.residuals["enthalpy_flow"],
            }
        schemes.append(entry)
    return {"total_pressure_kpa": total_pressure, "schemes": schemes}


def write_json(results: list[MixResult], total_pressure: float, path: str) -> None:
    report = build_report(results, total_pressure)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
