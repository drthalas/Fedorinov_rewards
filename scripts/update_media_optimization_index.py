#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from backend.app.services.media_image_policy import JPEG_POLICY_VERSION
from backend.app.services.media_optimization_index import (
    build_index_from_manifest,
    run_incremental_index,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or update the persistent media optimization index.")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--policy-version", default=JPEG_POLICY_VERSION)
    subparsers = parser.add_subparsers(dest="command", required=True)
    baseline = subparsers.add_parser("baseline")
    baseline.add_argument("--analysis-manifest", type=Path, required=True)
    baseline.add_argument("--conversion-manifest", type=Path)
    subparsers.add_parser("update")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "baseline":
        result = build_index_from_manifest(
            args.data_root,
            args.analysis_manifest,
            args.index,
            conversion_manifest=args.conversion_manifest,
            policy_version=args.policy_version,
        )
    else:
        result = run_incremental_index(
            args.data_root,
            args.index,
            database=args.database,
            policy_version=args.policy_version,
        )
    print(json.dumps(result.as_dict(), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
