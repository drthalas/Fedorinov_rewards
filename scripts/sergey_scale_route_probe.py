#!/usr/bin/env python3
"""Measure one application route in an isolated Sergey-scale subprocess."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import contextvars
import cProfile
import io
import json
import os
from pathlib import Path
import pstats
import resource
import sqlite3
import statistics
import sys
import time
from typing import Any
from urllib.parse import urlsplit


CURRENT_METRICS: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "ale302_metrics",
    default=None,
)
ORIGINAL_CONNECT = sqlite3.connect
ORIGINAL_PATH_METHODS = {
    name: getattr(Path, name)
    for name in ("exists", "is_file", "stat", "iterdir", "rglob")
}
ORIGINAL_OS_WALK = os.walk


def _statement_kind(sql: object) -> str:
    text = str(sql or "").lstrip()
    while text.startswith("--"):
        text = text.split("\n", 1)[1].lstrip() if "\n" in text else ""
    token = text.split(None, 1)[0].upper() if text else "OTHER"
    if token in {"SELECT", "WITH"}:
        return "SELECT"
    if token == "PRAGMA":
        return "PRAGMA"
    return "OTHER"


def _normalize_sql(sql: object) -> str:
    return " ".join(str(sql or "").split())[:2_000]


class CountingConnection(sqlite3.Connection):
    def execute(self, sql: object, parameters: object = (), /):  # type: ignore[override]
        started = time.perf_counter()
        try:
            return super().execute(sql, parameters)
        finally:
            elapsed = time.perf_counter() - started
            metrics = CURRENT_METRICS.get()
            if metrics is not None:
                kind = _statement_kind(sql)
                metrics["sql_counts"][kind] += 1
                metrics["sql_seconds"] += elapsed
                normalized = _normalize_sql(sql)
                entry = metrics["sql_statements"].setdefault(
                    normalized,
                    {"kind": kind, "count": 0, "seconds": 0.0},
                )
                entry["count"] += 1
                entry["seconds"] += elapsed

    def executemany(self, sql: object, seq_of_parameters: object, /):  # type: ignore[override]
        started = time.perf_counter()
        try:
            return super().executemany(sql, seq_of_parameters)
        finally:
            elapsed = time.perf_counter() - started
            metrics = CURRENT_METRICS.get()
            if metrics is not None:
                kind = _statement_kind(sql)
                metrics["sql_counts"][kind] += 1
                metrics["sql_seconds"] += elapsed


def _counting_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
    kwargs.setdefault("factory", CountingConnection)
    return ORIGINAL_CONNECT(*args, **kwargs)


def _patch_path_method(name: str) -> None:
    original = ORIGINAL_PATH_METHODS[name]

    def wrapper(self: Path, *args: object, **kwargs: object):
        metrics = CURRENT_METRICS.get()
        if metrics is not None:
            metrics["filesystem_counts"][name] += 1
        return original(self, *args, **kwargs)

    setattr(Path, name, wrapper)


def _counting_walk(*args: object, **kwargs: object):
    metrics = CURRENT_METRICS.get()
    if metrics is not None:
        metrics["filesystem_counts"]["walk"] += 1
    return ORIGINAL_OS_WALK(*args, **kwargs)


def install_instrumentation() -> None:
    sqlite3.connect = _counting_connect  # type: ignore[assignment]
    for name in ORIGINAL_PATH_METHODS:
        _patch_path_method(name)
    os.walk = _counting_walk  # type: ignore[assignment]


def new_metrics() -> dict[str, Any]:
    return {
        "sql_counts": Counter(),
        "sql_seconds": 0.0,
        "sql_statements": {},
        "filesystem_counts": Counter(),
    }


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile + 0.999999)))
    return ordered[rank]


def _rss_bytes() -> int:
    maximum = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return maximum if sys.platform == "darwin" else maximum * 1024


def _top_sql(metrics: dict[str, Any]) -> list[dict[str, object]]:
    rows = [
        {"sql": sql, **values}
        for sql, values in metrics["sql_statements"].items()
    ]
    rows.sort(key=lambda item: float(item["seconds"]), reverse=True)
    for row in rows:
        row["seconds"] = round(float(row["seconds"]), 6)
    return rows[:10]


async def _asgi_get(app: Any, target: str) -> tuple[int | None, bytes]:
    parsed = urlsplit(target)
    request_sent = False
    status: int | None = None
    body_parts: list[bytes] = []

    async def receive() -> dict[str, object]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.sleep(3600)
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        nonlocal status
        if message["type"] == "http.response.start":
            status = int(message["status"])
        elif message["type"] == "http.response.body":
            body_parts.append(bytes(message.get("body", b"")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": parsed.path or "/",
        "raw_path": (parsed.path or "/").encode("utf-8"),
        "query_string": parsed.query.encode("utf-8"),
        "root_path": "",
        "headers": [(b"host", b"ale302.test")],
        "client": ("127.0.0.1", 30200),
        "server": ("ale302.test", 80),
        "state": {},
    }
    await app(scope, receive, send)
    return status, b"".join(body_parts)


async def _request_once(app: Any, path: str, timeout_seconds: float, profile: bool) -> dict[str, object]:
    metrics = new_metrics()
    token = CURRENT_METRICS.set(metrics)
    profiler = cProfile.Profile() if profile else None
    started = time.perf_counter()
    rss_before = _rss_bytes()
    response_status: int | None = None
    response_body = b""
    error: str | None = None
    timed_out = False
    try:
        if profiler is not None:
            profiler.enable()
        response_status, response_body = await asyncio.wait_for(
            _asgi_get(app, path),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        timed_out = True
        error = f"timeout>{timeout_seconds:g}s"
    except Exception as exc:  # Benchmark evidence must retain the exact failure class.
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if profiler is not None:
            profiler.disable()
        elapsed = time.perf_counter() - started
        CURRENT_METRICS.reset(token)

    profile_top = ""
    if profiler is not None:
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(25)
        profile_top = stream.getvalue()
    sql_seconds = float(metrics["sql_seconds"])
    return {
        "wall_seconds": round(elapsed, 6),
        "sql_seconds": round(sql_seconds, 6),
        "python_render_seconds": round(max(0.0, elapsed - sql_seconds), 6),
        "sql_counts": dict(metrics["sql_counts"]),
        "filesystem_counts": dict(metrics["filesystem_counts"]),
        "top_sql": _top_sql(metrics),
        "status": response_status,
        "response_bytes": len(response_body),
        "rss_before_bytes": rss_before,
        "rss_peak_bytes": _rss_bytes(),
        "timed_out": timed_out,
        "error": error,
        "profile_top": profile_top,
    }


async def run_probe(args: argparse.Namespace) -> dict[str, object]:
    app_root = args.app_root.resolve()
    data_root = args.data_root.resolve()
    sys.path.insert(0, str(app_root))
    os.environ.update(
        {
            "REWARDS_DATA_DIR": str(data_root),
            "REWARDS_DB_PATH": str(data_root / "database/MyDatabase.sqlite"),
            "READ_ONLY": "true",
            "WRITE_MODE": "false",
            "REQUIRE_BACKUP_BEFORE_WRITE": "false",
            "REQUIRE_BACKUP_BEFORE_DANGEROUS_ACTIONS": "false",
            "UPDATE_CHECK_ENABLED": "false",
        }
    )
    install_instrumentation()

    from backend.app.main import app

    cold = await _request_once(app, args.path, args.timeout, args.profile)
    warm: list[dict[str, object]] = []
    if not cold["timed_out"]:
        for _ in range(args.warm_runs):
            warm.append(await _request_once(app, args.path, args.timeout, False))

    warm_wall = [float(item["wall_seconds"]) for item in warm if not item["timed_out"]]
    aggregate = {
        "p50_seconds": round(statistics.median(warm_wall), 6) if warm_wall else None,
        "p95_seconds": round(float(_percentile(warm_wall, 0.95)), 6) if warm_wall else None,
        "max_seconds": round(max(warm_wall), 6) if warm_wall else None,
        "successful_warm_runs": len(warm_wall),
        "requested_warm_runs": args.warm_runs,
    }
    return {
        "route": args.route_name,
        "path": args.path,
        "app_root": str(app_root),
        "data_root": str(data_root),
        "cold": cold,
        "warm": warm,
        "aggregate": aggregate,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--route-name", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--warm-runs", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--profile", action="store_true")
    return parser.parse_args()


def main() -> int:
    result = asyncio.run(run_probe(parse_args()))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
