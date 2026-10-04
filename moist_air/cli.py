"""Command-line entry point: audit a config, emit CSV table and JSON report."""

from __future__ import annotations

import argparse
import csv
import json
import sys

from .audit import (
    CSV_HEADER,
    ConfigError,
    load_config,
    report_to_dict,
    report_to_row,
    run_audit,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="moist-air-mix-audit",
        description="Audit multi-inlet moist-air mixing on a dry-air basis.",
    )
    parser.add_argument("config", help="path to the JSON configuration file")
    parser.add_argument("--csv", required=True, help="output CSV condition table")
    parser.add_argument("--json", required=True, help="output JSON balance report")
    args = parser.parse_args(argv)

    try:
        table, schemes = load_config(args.config)
    except (OSError, ConfigError, json.JSONDecodeError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    reports = run_audit(table, schemes)

    with open(args.csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(CSV_HEADER)
        for report in reports:
            writer.writerow(report_to_row(report))

    payload = {
        "total_pressure_kpa": table.total_pressure,
        "table_range_c": [table.t_min, table.t_max],
        "scheme_count": len(reports),
        "schemes": [report_to_dict(report) for report in reports],
    }
    with open(args.json, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    invalid = sum(1 for r in reports if not r.ok)
    condensing = sum(
        1 for r in reports if r.ok and r.result is not None and r.result.condensation_required
    )
    print(
        f"audited {len(reports)} scheme(s): "
        f"{len(reports) - invalid - condensing} valid, "
        f"{condensing} condensation-required, {invalid} invalid"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
