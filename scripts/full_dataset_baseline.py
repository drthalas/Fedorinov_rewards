#!/usr/bin/env python3
"""Collect privacy-safe HTTP timings for an already running full-data fixture."""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from pathlib import Path
from typing import Any


PERSON_MEDIA_FIELDS = (
    "person_foto",
    "main_foto",
    "rewards_foto",
    "book1_foto",
    "book2_foto",
    "card1_foto",
    "card2_foto",
)


def fixture_targets(db_path: Path) -> dict[str, Any]:
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        reward_counts = connection.execute(
            """
            select p.id, count(r.id) as reward_count
            from person p
            left join rewards r on r.person_id = p.id
            group by p.id
            order by reward_count, p.id
            """
        ).fetchall()
        if not reward_counts:
            raise RuntimeError("The fixture has no person rows.")
        no_rewards = next((row for row in reward_counts if row[1] == 0), reward_counts[0])
        ordinary_rows = [row for row in reward_counts if 1 <= row[1] <= 5]
        ordinary = ordinary_rows[len(ordinary_rows) // 2] if ordinary_rows else reward_counts[len(reward_counts) // 2]
        heavy = max(reward_counts, key=lambda row: (row[1], -row[0]))

        columns = {
            row[1]
            for row in connection.execute("pragma table_info(person)").fetchall()
        }
        media_fields = [field for field in PERSON_MEDIA_FIELDS if field in columns]
        media_path = None
        for field in media_fields:
            row = connection.execute(
                f"""
                select "{field}"
                from person
                where "{field}" is not null and trim("{field}") <> ''
                order by id
                limit 1
                """
            ).fetchone()
            if row:
                media_path = str(row[0])
                break
    return {
        "no_rewards_id": int(no_rewards[0]),
        "ordinary_id": int(ordinary[0]),
        "heavy_id": int(heavy[0]),
        "heavy_reward_count": int(heavy[1]),
        "media_path": media_path,
    }


def timed_request(base_url: str, route: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        urllib.parse.urljoin(base_url.rstrip("/") + "/", route.lstrip("/")),
        headers={"User-Agent": "Fedorinov-full-dataset-baseline/1"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return {
                "seconds": round(time.perf_counter() - started, 6),
                "status": response.status,
                "bytes": len(body),
                "error": None,
            }
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        return {
            "seconds": round(time.perf_counter() - started, 6),
            "status": None,
            "bytes": 0,
            "error": type(error).__name__,
        }


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    durations = [sample["seconds"] for sample in samples]
    return {
        "cold_seconds": durations[0],
        "warm_p50_seconds": round(statistics.median(durations[1:]), 6),
        "warm_max_seconds": max(durations[1:]),
        "statuses": sorted({sample["status"] for sample in samples if sample["status"] is not None}),
        "response_bytes": samples[-1]["bytes"],
        "errors": [sample["error"] for sample in samples if sample["error"]],
    }


def collect(
    base_url: str,
    db_path: Path,
    *,
    warm_runs: int,
    timeout: float,
    label: str,
) -> dict[str, Any]:
    targets = fixture_targets(db_path)
    routes = {
        "main": "/legacy?tab=rewards",
        "ordinary_card": f"/legacy?tab=rewards&person_id={targets['ordinary_id']}",
        "no_rewards_card": f"/legacy?tab=rewards&person_id={targets['no_rewards_id']}",
        "heavy_card": f"/legacy?tab=rewards&person_id={targets['heavy_id']}",
        "guides": "/legacy?tab=guides",
        "search_initial": "/legacy?tab=search",
        "summary_initial": "/legacy?tab=summary",
    }
    if targets["media_path"]:
        routes["media_open"] = "/media?path=" + urllib.parse.quote(
            targets["media_path"], safe=""
        )

    results = {}
    for name, route in routes.items():
        samples = [
            timed_request(base_url, route, timeout)
            for _ in range(warm_runs + 1)
        ]
        results[name] = summarize(samples)
    return {
        "schema": 1,
        "profile": "sergey-full",
        "label": label,
        "warm_runs": warm_runs,
        "heavy_reward_count": targets["heavy_reward_count"],
        "operations": results,
        "pass": all(
            not operation["errors"] and operation["statuses"] == [200]
            for operation in results.values()
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--warm-runs", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--label", default="unlabeled")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.warm_runs < 1:
        raise SystemExit("--warm-runs must be at least 1")
    result = collect(
        args.base_url,
        args.db,
        warm_runs=args.warm_runs,
        timeout=args.timeout,
        label=args.label,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
