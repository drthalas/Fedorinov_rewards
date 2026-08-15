#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from backend.app.services.media_optimization import ConversionPolicy, build_optimized_copy


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and verify a separate optimized media workspace.")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-database", type=Path, required=True)
    parser.add_argument("--analysis-manifest", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--jpeg-quality", type=int, default=90)
    parser.add_argument("--policy-version", default="jpeg-q90-opaque-photo-v1")
    parser.add_argument("--restart-incomplete", action="store_true")
    args = parser.parse_args(argv)
    if args.jpeg_quality < 1 or args.jpeg_quality > 100:
        parser.error("JPEG quality must be between 1 and 100")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_optimized_copy(
        args.source_root,
        args.source_database,
        args.analysis_manifest,
        args.destination,
        ConversionPolicy(version=args.policy_version, jpeg_quality=args.jpeg_quality),
        restart_incomplete=args.restart_incomplete,
    )
    print(json.dumps(result.as_dict(), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
