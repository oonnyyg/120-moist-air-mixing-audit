"""Command line entry point."""

from __future__ import annotations

import argparse
import sys

from .config import load_config
from .mixing import mix_streams
from .report import write_csv, write_json


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="moist-air-mixing",
        description="Offline moist air mixing audit (dry-air mass basis).",
    )
    parser.add_argument("config", help="JSON configuration file")
    parser.add_argument("--csv", default="conditions.csv",
                        help="output CSV condition table path")
    parser.add_argument("--json", default="balance.json",
                        help="output JSON balance report path")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except (ValueError, OSError, KeyError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    results = [
        mix_streams(scheme.name, scheme.inlets, config.table, config.total_pressure)
        for scheme in config.schemes
    ]
    for r in results:
        if not r.valid:
            print(f"[invalid] {r.name}: {r.error}")
        elif r.supersaturated:
            print(f"[supersaturated] {r.name}: condensation handling required")
        else:
            print(f"[ok] {r.name}: T={r.mixed.temperature:.3f} C, "
                  f"RH={r.mixed.relative_humidity:.4f}")

    write_csv(results, args.csv)
    write_json(results, config.total_pressure, args.json)
    print(f"wrote {args.csv} and {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
