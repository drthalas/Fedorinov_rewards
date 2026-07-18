#!/usr/bin/env python3
"""Run the deterministic ALE-302 route matrix across release worktrees."""

from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


VERSION_REFS = {
    "v2.0.0": "v2.0.0",
    "v2.0.1": "v2.0.1",
    "v2.0.2": "v2.0.2",
    "v2.0.3": "v2.0.3",
    "main": "origin/main",
}


def _run(command: list[str], *, cwd: Path, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def _git(repo: Path, *args: str) -> str:
    return _run(["git", *args], cwd=repo).stdout.strip()


def prepare_worktrees(repo: Path, root: Path, versions: list[str]) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    worktrees: dict[str, Path] = {}
    for version in versions:
        ref = VERSION_REFS[version]
        expected = _git(repo, "rev-parse", f"{ref}^{{}}")
        target = root / version
        if not target.exists():
            _run(["git", "worktree", "add", "--detach", str(target), ref], cwd=repo)
        actual = _git(target, "rev-parse", "HEAD")
        if actual != expected:
            raise RuntimeError(f"Worktree mismatch for {version}: {actual} != {expected}")
        worktrees[version] = target
    return worktrees


def _manifest(root: Path) -> dict[str, Any]:
    return json.loads((root / "benchmark_manifest.json").read_text(encoding="utf-8"))


def collect_query_plans(data_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    fixture = manifest["fixture_ids"]
    db_path = (data_root / "database/MyDatabase.sqlite").resolve()
    uri = f"file:{db_path}?mode=ro"
    queries = {
        "person_list": (
            """
            select p.id, p.fio, count(r.id)
            from person p
            left join rewards r on r.person_id = p.id
            group by p.id
            order by lower(coalesce(p.fio, '')), p.id
            """,
            (),
        ),
        "person_rewards": (
            "select * from rewards where person_id = ? order by id",
            (int(fixture["heavy_person"]),),
        ),
        "guide_name_usage": (
            "select count(*) from rewards where id_name = ?",
            (int(fixture["guide_name"]),),
        ),
        "rank_usage": (
            "select count(*) from person where id_rank = ?",
            (int(fixture["blocked_rank"]),),
        ),
        "person_exact_search": (
            "select id from person where lower(fio) = lower(?)",
            ("Тестовый Кавалер 00002",),
        ),
        "person_contains_search": (
            "select id from person where lower(fio) like ?",
            ("%кавалер%",),
        ),
        "media_reference_scan": (
            "select id, front_foto from rewards where front_foto is not null and trim(front_foto) != ''",
            (),
        ),
    }
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        plans = {
            name: [
                {"id": int(row[0]), "parent": int(row[1]), "detail": str(row[3])}
                for row in connection.execute("explain query plan " + sql, params).fetchall()
            ]
            for name, (sql, params) in queries.items()
        }
        indexes = [
            {"name": str(row[0]), "table": str(row[1]), "sql": row[2]}
            for row in connection.execute(
                "select name, tbl_name, sql from sqlite_master where type = 'index' order by tbl_name, name"
            ).fetchall()
        ]
        row_counts = {
            table: int(connection.execute(f"select count(*) from {table}").fetchone()[0])
            for table in ("person", "rewards", "mark", "person_media", "guide", "guide_lev_3")
        }
    return {"plans": plans, "indexes": indexes, "row_counts": row_counts}


def route_specs(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    fixture = manifest["fixture_ids"]
    zero_person = int(fixture["zero_person"])
    ordinary_person = int(fixture["ordinary_person"])
    many_person = int(fixture["many_person"])
    heavy_person = int(fixture["heavy_person"])
    ordinary_reward = int(fixture["ordinary_reward"])
    heavy_reward = int(fixture["heavy_reward"])
    mark_id = int(fixture["mark"])
    query = "%D0%A2%D0%B5%D1%81%D1%82%D0%BE%D0%B2%D1%8B%D0%B9%20%D0%9A%D0%B0%D0%B2%D0%B0%D0%BB%D0%B5%D1%80%2000002"
    return [
        ("main", "/legacy?tab=rewards"),
        ("person_zero", f"/legacy?tab=rewards&person_id={zero_person}"),
        ("person_ordinary", f"/legacy?tab=rewards&person_id={ordinary_person}"),
        ("person_many", f"/legacy?tab=rewards&person_id={many_person}"),
        ("person_heavy", f"/legacy?tab=rewards&person_id={heavy_person}"),
        ("person_delete_preflight", f"/persons/{ordinary_person}/delete-preview"),
        ("person_delete_preflight_heavy", f"/persons/{heavy_person}/delete-preview"),
        ("reward_delete_preflight", f"/rewards/{ordinary_reward}/delete-preview"),
        ("reward_delete_preflight_heavy", f"/rewards/{heavy_reward}/delete-preview"),
        ("mark_delete_preflight", f"/marks/{mark_id}/delete-preview"),
        ("guides", "/guides"),
        ("guides_selected", "/guides?open=l0-1%2Cl1-1%2Cl2-1&focus=l3-1"),
        ("guide_form", "/guides/levels/3/1/edit?return_to=%2Fguides"),
        ("reward_form_cascade", f"/persons/{ordinary_person}/rewards/new"),
        ("search_initial", "/legacy?tab=search"),
        ("search_exact", f"/legacy?tab=search&q={query}&scope=persons&mode=exact"),
        ("search_contains", "/legacy?tab=search&q=%D0%9A%D0%B0%D0%B2%D0%B0%D0%BB%D0%B5%D1%80&scope=persons&mode=contains"),
        ("marks", "/legacy?tab=marks"),
        ("summary", "/legacy?tab=summary"),
    ]


def run_route_probe(
    python: Path,
    probe: Path,
    app_root: Path,
    data_root: Path,
    route_name: str,
    path: str,
    warm_runs: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    command = [
        str(python),
        str(probe),
        "--app-root",
        str(app_root),
        "--data-root",
        str(data_root),
        "--route-name",
        route_name,
        "--path",
        path,
        "--warm-runs",
        str(warm_runs),
        "--timeout",
        str(timeout_seconds),
    ]
    if route_name in {"main", "person_heavy", "guides"}:
        command.append("--profile")
    started = time.perf_counter()
    try:
        completed = _run(
            command,
            cwd=probe.parent.parent,
            timeout=max(45.0, timeout_seconds * 3.0),
        )
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        result["probe_process_seconds"] = round(time.perf_counter() - started, 6)
        return result
    except subprocess.TimeoutExpired:
        return {
            "route": route_name,
            "path": path,
            "process_timed_out": True,
            "probe_process_seconds": round(time.perf_counter() - started, 6),
            "error": "probe subprocess timeout",
        }
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        return {
            "route": route_name,
            "path": path,
            "process_timed_out": False,
            "probe_process_seconds": round(time.perf_counter() - started, 6),
            "error": f"{type(exc).__name__}: {exc}",
            "stderr": getattr(exc, "stderr", "")[-4_000:],
        }


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_runtime(
    python: Path,
    app_root: Path,
    data_root: Path,
    output_root: Path,
    label: str,
) -> tuple[subprocess.Popen[str], dict[str, Any], Any]:
    port = _free_port()
    log_path = output_root / f"runtime-{label}.log"
    log_handle = log_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(app_root),
            "REWARDS_DATA_DIR": str(data_root),
            "REWARDS_DB_PATH": str(data_root / "database/MyDatabase.sqlite"),
            "READ_ONLY": "true",
            "WRITE_MODE": "false",
            "REQUIRE_BACKUP_BEFORE_WRITE": "false",
            "REQUIRE_BACKUP_BEFORE_DANGEROUS_ACTIONS": "false",
            "UPDATE_CHECK_ENABLED": "false",
            "APP_PORT": str(port),
        }
    )
    started = time.perf_counter()
    process = subprocess.Popen(
        [
            str(python),
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=app_root,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    ready_seconds: float | None = None
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            with urlopen(f"http://127.0.0.1:{port}/version", timeout=0.5) as response:
                if response.status == 200:
                    ready_seconds = time.perf_counter() - started
                    break
        except (URLError, TimeoutError, OSError):
            time.sleep(0.05)
    identity = {
        "port": port,
        "pid": process.pid,
        "ready_seconds": round(ready_seconds, 6) if ready_seconds is not None else None,
        "ready": ready_seconds is not None,
        "log_path": str(log_path),
    }
    return process, identity, log_handle


def _decode_raw_json(output: str) -> Any:
    value = json.loads(output.strip())
    return json.loads(value) if isinstance(value, str) else value


def playwright_command(wrapper: Path, session: str, *args: str, cwd: Path, timeout: float = 60.0) -> str:
    completed = _run(
        [str(wrapper), f"-s={session}", *args],
        cwd=cwd,
        timeout=timeout,
    )
    return completed.stdout.strip()


def browser_probe(
    wrapper: Path,
    session: str,
    base_url: str,
    manifest: dict[str, Any],
    cwd: Path,
) -> dict[str, Any]:
    fixture = manifest["fixture_ids"]
    paths = {
        "main": "/legacy?tab=rewards",
        "ordinary": f"/legacy?tab=rewards&person_id={fixture['ordinary_person']}",
        "heavy": f"/legacy?tab=rewards&person_id={fixture['heavy_person']}",
        "guides": "/guides",
    }
    results: dict[str, Any] = {"route_errors": {}}
    try:
        playwright_command(wrapper, session, "open", base_url + paths["main"], "--headed", cwd=cwd, timeout=90)
        for name, path in paths.items():
            try:
                if name != "main":
                    playwright_command(wrapper, session, "goto", base_url + path, cwd=cwd, timeout=35)
                raw = playwright_command(
                    wrapper,
                    session,
                    "--raw",
                    "eval",
                    "() => JSON.stringify((() => { const n = performance.getEntriesByType('navigation')[0]; return {navigation_ms:n.duration,dom_content_loaded_ms:n.domContentLoadedEventEnd,load_ms:n.loadEventEnd,html_bytes:document.documentElement.outerHTML.length,person_rows:document.querySelectorAll('[data-person-list] .legacy-list-row').length}; })())",
                    cwd=cwd,
                )
                results[name] = _decode_raw_json(raw)
            except Exception as exc:
                results["route_errors"][name] = f"{type(exc).__name__}: {exc}"
        playwright_command(wrapper, session, "goto", base_url + paths["main"], cwd=cwd, timeout=35)
        code = """
async (page) => {
  const rows = page.locator('[data-person-list] .legacy-list-row');
  const first = rows.nth(1);
  const second = rows.nth(2);
  const firstUrl = await first.getAttribute('data-select-url');
  const secondUrl = await second.getAttribute('data-select-url');
  const started = Date.now();
  await first.click();
  await page.waitForFunction((url) => location.pathname + location.search === url && document.querySelector('[data-legacy-person-workspace]')?.getAttribute('aria-busy') === 'false', firstUrl);
  const firstMs = Date.now() - started;
  const secondStarted = Date.now();
  await second.click();
  await page.waitForFunction((url) => location.pathname + location.search === url && document.querySelector('[data-legacy-person-workspace]')?.getAttribute('aria-busy') === 'false', secondUrl);
  return JSON.stringify({first_ms:firstMs,second_ms:Date.now()-secondStarted,url:page.url()});
}
""".strip()
        raw = playwright_command(wrapper, session, "--raw", "run-code", code, cwd=cwd, timeout=90)
        results["rapid_selection"] = _decode_raw_json(raw)
        results["error"] = None
    except Exception as exc:
        results["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            playwright_command(wrapper, session, "close", cwd=cwd, timeout=30)
        except Exception:
            pass
    return results


def _write_results(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--worktrees-root", type=Path, required=True)
    parser.add_argument("--datasets-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--versions", nargs="+", choices=tuple(VERSION_REFS), default=list(VERSION_REFS))
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=("sergey-count-matched", "sergey-stress"),
        default=["sergey-count-matched", "sergey-stress"],
    )
    parser.add_argument("--warm-runs", type=int, default=5)
    parser.add_argument("--route-timeout", type=float, default=15.0)
    parser.add_argument("--playwright-wrapper", type=Path)
    parser.add_argument("--skip-browser", action="store_true")
    parser.add_argument("--browser-only", action="store_true")
    parser.add_argument("--plans-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    results_path = output_root / "benchmark-results.json"
    worktrees = prepare_worktrees(repo, args.worktrees_root.resolve(), args.versions)
    python = Path(sys.executable)
    probe = repo / "scripts/sergey_scale_route_probe.py"
    if (args.browser_only or args.plans_only) and results_path.exists():
        results = json.loads(results_path.read_text(encoding="utf-8"))
    else:
        results = {
            "generated_at_epoch": time.time(),
            "versions": {},
            "datasets": {},
        }
    for profile_name in args.profiles:
        data_root = args.datasets_root.resolve() / profile_name
        results["datasets"][profile_name] = _manifest(data_root)
    results["query_plans"] = {
        profile_name: collect_query_plans(
            args.datasets_root.resolve() / profile_name,
            results["datasets"][profile_name],
        )
        for profile_name in args.profiles
    }
    if args.plans_only:
        _write_results(results_path, results)
        print(json.dumps({"results": str(results_path), "query_plans": args.profiles}))
        return 0

    for version in args.versions:
        app_root = worktrees[version]
        version_sha = _git(app_root, "rev-parse", "HEAD")
        if version not in results["versions"]:
            results["versions"][version] = {"sha": version_sha, "profiles": {}}
        for profile_name in args.profiles:
            data_root = args.datasets_root.resolve() / profile_name
            manifest = results["datasets"][profile_name]
            profile_result = results["versions"][version]["profiles"].setdefault(profile_name, {"routes": {}})
            if not args.browser_only:
                print(f"[{version}/{profile_name}] route matrix", file=sys.stderr, flush=True)
                for route_name, path in route_specs(manifest):
                    print(f"  {route_name}", file=sys.stderr, flush=True)
                    profile_result["routes"][route_name] = run_route_probe(
                        python,
                        probe,
                        app_root,
                        data_root,
                        route_name,
                        path,
                        args.warm_runs,
                        args.route_timeout,
                    )
                    _write_results(results_path, results)

            process, startup, log_handle = start_runtime(
                python,
                app_root,
                data_root,
                output_root,
                f"{version}-{profile_name}",
            )
            profile_result["startup"] = startup
            try:
                if startup["ready"] and not args.skip_browser and args.playwright_wrapper:
                    profile_result["browser"] = browser_probe(
                        args.playwright_wrapper.resolve(),
                        f"ale302-{version.replace('.', '')}-{profile_name}",
                        f"http://127.0.0.1:{startup['port']}",
                        manifest,
                        output_root,
                    )
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                log_handle.close()
            _write_results(results_path, results)

    print(json.dumps({"results": str(results_path), "versions": args.versions, "profiles": args.profiles}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
