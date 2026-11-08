"""Controlled implementation and Railway adapter for one ALE-528 preview pilot."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import inspect
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

try:
    from .sergey_delivery import DeliveryBlocked, ROOT, digest, verify_diff
    from .sergey_intake import Store, safe_text
    from .sergey_analyst import CodexAnalyst
except ImportError:
    from sergey_delivery import DeliveryBlocked, ROOT, digest, verify_diff
    from sergey_intake import Store, safe_text
    from sergey_analyst import CodexAnalyst


PROJECT = "3da1bf74-6643-4f0b-a662-37ee009bee6e"
SERVICE = "5d6c8710-eee5-4adc-bb0e-d2ad53035e26"
ENVIRONMENT = "c9060444-0680-4baf-aa63-621b85c1aee8"
VOLUME = "3cce871a-8598-405f-8335-5a3b575a7c9f"
ORIGIN = "https://kavaleris-rewards.up.railway.app"

def media_check_mode(config, pilot):
    proof = config.get("full_media_checksum")
    if proof is None or proof is False:
        return "sample"
    if (not isinstance(proof, dict) or proof.get("kind") not in {"owner_request", "media_lifecycle_risk"}
            or len(proof.get("evidence", "")) < 16 or proof.get("contract_hash") != pilot["contract_hash"]):
        raise DeliveryBlocked("full_media_checksum_requires_scoped_evidence")
    return "full"


def media_fingerprint(root, mode):
    """Bounded samples by default; full traversal only for an explicit risk gate."""
    import hashlib
    import itertools
    if mode not in {"sample", "full"}:
        raise ValueError("Unknown media check mode")
    files = []
    for name in ["Source", "SourceMark", "GuideImages", "default"]:
        base = root / name
        if base.is_symlink() or not base.is_dir():
            continue
        if mode == "full":
            files.extend(p for p in base.rglob("*") if p.is_file())
            continue
        queue = [base]
        selected = 0
        visited = 0
        while queue and visited < 16 and selected < 2:
            folder = queue.pop(0)
            visited += 1
            for p in sorted(itertools.islice(folder.iterdir(), 256), key=lambda p: p.name):
                if p.is_symlink():
                    continue
                if p.is_dir() and len(queue) < 16:
                    queue.append(p)
                elif p.is_file() and p.stat().st_size <= 8 * 1024 * 1024:
                    files.append(p)
                    selected += 1
                    if selected == 2:
                        break
    digest = hashlib.sha256()
    for p in sorted(files):
        with p.open("rb") as f:
            checksum = hashlib.file_digest(f, "sha256").hexdigest()
        digest.update((p.relative_to(root).as_posix() + "\0" + checksum + "\n").encode())
    return {"media_count": len(files), "media_sha256": digest.hexdigest(), "media_check_scope": mode,
            "media_tree_byte_parity_checked": mode == "full"}


FINGERPRINT = inspect.getsource(media_fingerprint) + r'''
from pathlib import Path
import sqlite3,json,hashlib,os
root=Path('/data/rewards');db=root/'database/MyDatabase.sqlite'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as c:
 assert c.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
 counts={t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['person','rewards']}
 snapshot=hashlib.sha256(c.serialize()).hexdigest()
media_state=media_fingerprint(root,MEDIA_MODE)
keys=sorted(Path('/data/state/fedorinov-biography-enrichment').glob('*/signing.key'))
assert len(keys)==1 and keys[0].stat().st_size==32
result={'sqlite_snapshot':snapshot,'counts':counts,**media_state,
 'signing_state':sha(keys[0]),'auth_state':hashlib.sha256(os.environ['PREVIEW_AUTH_SHA256'].encode()).hexdigest()}
identity=Path('/app/delivery_identity.json')
if identity.exists():
 meta=json.loads(identity.read_text());actual={p:sha(Path('/app')/p) if (Path('/app')/p).is_file() else None for p in meta['files']}
 result['source_head']=meta['source_head'];result['code_matches_manifest']=actual==meta['files']
print(json.dumps(result,sort_keys=True))
'''


class PreviewAdapter:
    def __init__(self, state, config, credentials):
        self.state, self.config, self.credentials = state, config, credentials
        self.pilot = config["pilot"]
        self.folder = Path(config["work_root"]) / self.pilot["issue_id"]
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.runner = CodexAnalyst(ROOT, self.folder / "model", None, redactor=safe_text)
        self.intake = Store(Path(config["intake_state"]))

    def cancel(self):
        self.runner.cancel()

    def guard(self, job):
        current = self.state.job()
        if (not current or current["owner"] != job["owner"] or current["fence"] != job["fence"]
                or current["status"] != "active" or current["lease_until"] <= time.time()):
            raise DeliveryBlocked("lease_lost")
        if self.intake.meta("delivery_cancel:" + self.pilot["issue_id"]) == "1":
            raise DeliveryBlocked("cancelled")
        if self.intake.meta("paused") == "1" or self.intake.meta("delivery_paused") == "1":
            raise DeliveryBlocked("paused")

    def command(self, args, cwd=None, timeout=60):
        # Only code-controlled argv; no shell or commands from issue descriptions.
        return self.runner.run(args, timeout=timeout, cwd=cwd).stdout

    def git(self, worktree, *args):
        return self.command(["git", *args], cwd=worktree).strip()

    def implement(self, job):
        self.guard(job)
        p = self.pilot
        worktree = self.folder / "source"
        if not worktree.exists():
            self.command(["git", "worktree", "add", "-b", p["branch"], str(worktree), p["base_head"]], cwd=ROOT)
        if self.git(worktree, "branch", "--show-current") != p["branch"]:
            raise DeliveryBlocked("isolated_branch_mismatch")
        head = self.git(worktree, "rev-parse", "HEAD")
        plan_path = self.folder / "proposal.json"
        if head == p["base_head"] and not plan_path.exists():
            schema = {"type": "object", "additionalProperties": False,
                      "properties": {k: {"type": "string"} for k in ["path", "old", "new", "tier", "reason"]},
                      "required": ["path", "old", "new", "tier", "reason"]}
            schema_path = self.folder / "proposal-schema.json";schema_path.write_text(json.dumps(schema))
            prompt = ("Ты изолированный read-only delivery planner. Не используй инструменты, не создавай задачи, "
                      "не меняй файлы и не выполняй команды. Верни JSON: точная минимальная замена справочного текста "
                      "по подтверждённому pilot contract. Разрешён только этот path/old/new. "
                      "Проверь tier по риску: plain documentation copy без markup/logic — T1. "
                      "Никакого updater/schema/auth/data/signing/Windows/release.\n"
                      + json.dumps({"issue": p["issue_id"], "revision": p["revision"], "branch": p["branch"],
                                    "base": p["base_head"], "approved_patch": p["patch"],
                                    "contract": p["description"]}, ensure_ascii=False))
            args = ["codex", "exec", "--sandbox", "read-only", "--ephemeral", "--skip-git-repo-check",
                    "--disable", "shell_tool", "--disable", "apps", "--disable", "multi_agent",
                    "-c", 'web_search="disabled"', "--output-schema", str(schema_path), "-o", str(plan_path), "--json"]
            for name in self.runner.config.get("mcp_servers", {}):args += ["-c", f"mcp_servers.{name}.enabled=false"]
            with tempfile.TemporaryDirectory(prefix="ale528-delivery-plan-") as tmp:
                args += ["-C", tmp, "-"]
                env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in ["TOKEN", "API_KEY", "SERGEY_", "TELEGRAM", "LINEAR"])}
                self.runner.run(args, input=prompt, env=env, timeout=150)
            plan_path.chmod(0o600)
        if not plan_path.exists():raise DeliveryBlocked("proposal_receipt_missing")
        plan = json.loads(plan_path.read_text())
        if any(plan.get(k) != p["patch"][k] for k in ["path", "old", "new"]) or plan.get("tier") != p["tier"]:
            raise DeliveryBlocked("planner_outside_exact_scope")
        target = worktree / p["patch"]["path"]
        before = self.command(["git", "show", f"{p['base_head']}:{p['patch']['path']}"], cwd=worktree)
        expected = before.replace(p["patch"]["old"], p["patch"]["new"], 1)
        self.guard(job)
        actual = target.read_text()
        if actual == before:
            target.write_text(expected)
        elif actual != expected:
            raise DeliveryBlocked("worktree_unexpected_content")
        risk = verify_diff(worktree, p["base_head"], p)
        # Meaningful focused check: the entire Jinja template must still parse.
        self.command([self.config["test_python"], "-c",
                      "from pathlib import Path;from jinja2 import Environment;import sys;Environment().parse(Path(sys.argv[1]).read_text());print('Jinja parse PASS')",
                      str(target)], timeout=30)
        self.guard(job)
        if head == p["base_head"]:
            self.git(worktree, "add", "--", p["patch"]["path"])
            self.git(worktree, "commit", "-m", f"docs({p['issue_id']}): clarify backup guidance [DELIVERY PILOT r{p['revision']}]")
            head = self.git(worktree, "rev-parse", "HEAD")
        elif self.git(worktree, "rev-parse", "HEAD^") != p["base_head"]:
            raise DeliveryBlocked("unexpected_commit_ancestry")
        if self.git(worktree, "status", "--porcelain"):
            raise DeliveryBlocked("worker_tree_not_clean")
        self.guard(job)
        remote = self.git(worktree, "ls-remote", "origin", "refs/heads/" + p["branch"])
        if remote and remote.split()[0] != head:raise DeliveryBlocked("published_branch_diverged")
        if not remote:self.git(worktree, "push", "origin", "HEAD:refs/heads/" + p["branch"])
        result = {"source_head": head, "worktree": str(worktree), "actual_diff": risk,
                  "url": ORIGIN, "implementation_receipt": "exact guarded copy + Jinja parse PASS"}
        self.state.operation(job["id"], "implementation", "sent", result)
        return result

    def railway(self, args, cwd=None, timeout=60):
        return self.command(["railway", *args], cwd=cwd or self.config["linked_directory"], timeout=timeout)

    def status(self):
        value = json.loads(self.railway(["status", "--json"]))
        if value["id"] != PROJECT:raise DeliveryBlocked("wrong_railway_project")
        env = next(n["node"] for n in value["environments"]["edges"] if n["node"]["id"] == ENVIRONMENT)
        service = next(n["node"] for n in env["serviceInstances"]["edges"] if n["node"]["serviceId"] == SERVICE)
        volumes = [n["node"] for n in env["volumeInstances"]["edges"] if n["node"]["serviceId"] == SERVICE]
        if len(volumes) != 1 or volumes[0]["volume"]["id"] != VOLUME or volumes[0]["mountPath"] != "/data":
            raise DeliveryBlocked("preview_volume_changed")
        return service

    def fingerprint(self):
        if self.status()["id"] != self.config["ssh_user"]:
            raise DeliveryBlocked("ssh_service_instance_changed")
        output = self.command(["ssh", "-T", "-i", self.config["ssh_key"], "-o", "IdentitiesOnly=yes",
                               "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + self.config["ssh_known_hosts"],
                               "-o", "ConnectTimeout=10", self.config["ssh_user"] + "@ssh.railway.com",
                               shlex.join(["python", "-c", FINGERPRINT.replace("MEDIA_MODE", repr(media_check_mode(self.config, self.pilot)))])], timeout=60)
        for line in reversed(output.splitlines()):
            if line.startswith("{"):return json.loads(line)
        raise DeliveryBlocked("remote_fingerprint_missing")

    def package(self, job, body):
        staging = self.folder / "deployment"
        if staging.exists():return staging
        staging.mkdir(mode=0o700)
        archive = subprocess.run(["git", "archive", body["source_head"], "backend"], cwd=body["worktree"], capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(staging, filter="data")
        infra = Path(self.config["infrastructure"])
        for name in ["Dockerfile", "railway.toml", "railway_preview.py", "seed_preview.py", "start-preview.sh"]:
            data = (infra / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != self.config["infrastructure_hashes"][name]:
                raise DeliveryBlocked("accepted_infrastructure_changed")
            (staging / name).write_bytes(data)
        files = {p.relative_to(staging).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted((staging / "backend").rglob("*")) if p.is_file()}
        descriptor = {"source_head": body["source_head"], "delivery_issue": self.pilot["issue_id"],
                      "contract_revision": self.pilot["revision"], "files": files}
        (staging / "delivery_identity.json").write_text(json.dumps(descriptor, sort_keys=True))
        wrapper = (staging / "railway_preview.py").read_text()
        old = "'zip_sha256': PACKAGE_SHA256}"
        if wrapper.count(old) != 1:raise DeliveryBlocked("identity_adapter_shape_changed")
        wrapper = "import json\nfrom pathlib import Path\n" + wrapper.replace(old, "'zip_sha256': PACKAGE_SHA256, **json.loads(Path('/app/delivery_identity.json').read_text())}", 1)
        compile(wrapper, "railway_preview.py", "exec")
        (staging / "railway_preview.py").write_text(wrapper)
        docker = (staging / "Dockerfile").read_text()
        (staging / "Dockerfile").write_text(docker.replace("ENV PYTHONDONTWRITEBYTECODE", "COPY delivery_identity.json ./\nENV PYTHONDONTWRITEBYTECODE", 1))
        return staging

    def deploy(self, job):
        self.guard(job)
        body = json.loads(job["body"])
        op = self.state.operation(job["id"], "deployment")
        marker = f"ALE-528 DELIVERY {self.pilot['issue_id']} r{self.pilot['revision']} HEAD {body['source_head']}"
        marker = op["body"]["marker"] if op else marker + f" build {self.config.get('build_revision', 1)}"
        if not op:
            current = self.status()
            if current["latestDeployment"]["id"] != self.config["expected_deployment"] or current["latestDeployment"]["status"] != "SUCCESS":
                raise DeliveryBlocked("competing_or_unexpected_deployment")
            self.config["before_fingerprint"] = self.fingerprint()
            self.state.operation(job["id"], "before", "sent", self.config["before_fingerprint"])
            staging = self.package(job, body)
            # This context contains only git-exported backend and the fixed infrastructure.
            # Source-controlled app PNG/JPG must not inherit the parent repo's data ignore rules.
            allowed = {"Dockerfile", "railway.toml", "railway_preview.py", "seed_preview.py", "start-preview.sh", "delivery_identity.json"}
            for path in staging.rglob("*"):
                if path.is_file():
                    relative = path.relative_to(staging).as_posix()
                    if not (relative.startswith("backend/") or relative in allowed) or path.name == ".env" or path.suffix in {".db", ".sqlite", ".zip"}:
                        raise DeliveryBlocked("unsafe_deployment_payload")
            self.guard(job)
            self.state.operation(job["id"], "deployment", "started", {"marker": marker, "at": time.time()})
            try:self.railway(["up", str(staging), "--path-as-root", "--no-gitignore", "--detach", "--json", "--project", PROJECT,
                              "--service", SERVICE, "--environment", ENVIRONMENT, "--message", marker], cwd=staging, timeout=120)
            except Exception:
                # The request might have succeeded. Reconcile by the exact cliMessage, never repeat up.
                self.state.event("deployment_result_uncertain", job["id"])
            return None
        deployments = json.loads(self.railway(["deployment", "list", "--service", SERVICE, "--environment", ENVIRONMENT, "--limit", "20", "--json"]))
        matches = [d for d in deployments if (d.get("meta") or {}).get("cliMessage") == marker]
        if len(matches) > 1:raise DeliveryBlocked("duplicate_deployment_marker")
        if not matches:
            if time.time() - op["body"]["at"] > 90:raise DeliveryBlocked("deployment_uncertain_no_retry")
            return None
        deployment = matches[0]
        self.state.operation(job["id"], "deployment", "started", {**op["body"], "id": deployment["id"]})
        if deployment["status"] in {"FAILED", "CRASHED", "REMOVED"}:raise DeliveryBlocked("railway_deployment_failed")
        if deployment["status"] != "SUCCESS":return None
        if self.status()["latestDeployment"]["id"] != deployment["id"]:raise DeliveryBlocked("competing_deployment_after_upload")
        self.state.operation(job["id"], "deployment", "sent", {**op["body"], "id": deployment["id"]})
        return {"deployment_id": deployment["id"]}

    def http(self, path, authenticated=True):
        request = urllib.request.Request(ORIGIN + path)
        if authenticated:
            c = self.credentials["preview_auth"]
            auth = base64.b64encode((c["username"] + ":" + c["password"]).encode()).decode()
            request.add_header("Authorization", "Basic " + auth)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:return response.status, response.read()
        except urllib.error.HTTPError as response:return response.code, response.read()

    def verify(self, job):
        self.guard(job)
        body = json.loads(job["body"])
        before = self.state.operation(job["id"], "before")["body"]
        after = self.fingerprint()
        if before.get("media_check_scope") != after.get("media_check_scope"):
            raise DeliveryBlocked("media_policy_changed_reconcile_required")
        for key in ["sqlite_snapshot", "counts", "media_count", "media_sha256", "signing_state", "auth_state"]:
            if before[key] != after[key]:raise DeliveryBlocked("preview_data_or_credentials_changed")
        if after.get("source_head") != body["source_head"] or not after.get("code_matches_manifest"):
            raise DeliveryBlocked("deployed_code_parity_failed")
        status, raw = self.http("/preview/identity")
        identity = json.loads(raw)
        if status != 200 or identity.get("source_head") != body["source_head"] or identity.get("delivery_issue") != self.pilot["issue_id"]:
            raise DeliveryBlocked("https_identity_mismatch")
        if self.http("/legacy?tab=about", False)[0] != 401 or self.http("/health", False)[0] != 401:
            raise DeliveryBlocked("preview_guest_access_changed")
        if self.http("/updates/check")[0] != 404:raise DeliveryBlocked("updater_not_disabled")
        status, html = self.http("/legacy?tab=about")
        if status != 200 or self.pilot["patch"]["new"].encode() not in html:
            raise DeliveryBlocked("preview_copy_check_failed")
        self.state.operation(job["id"], "verification", "sent", {"before": before, "after": after})
        return {"deployed_head": after["source_head"], "data_preserved": True, "verification": "SSH code/data/auth parity + HTTPS copy/guest/updater PASS"}
