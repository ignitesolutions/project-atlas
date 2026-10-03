#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import json
import os
import re
import shutil
import hashlib
import subprocess
import fnmatch
import tempfile
import fcntl
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ATLAS_DIR = "project-atlas"

EXISTING_REQUIRED_FILES = [
    "project-atlas/README.md",
    "project-atlas/agent-playbook.md",
    "project-atlas/.project-atlasignore",
    "project-atlas/project-overview.md",
    "project-atlas/architecture.md",
    "project-atlas/code-map.md",
    "project-atlas/operations.md",
    "project-atlas/open-questions.md",
    "project-atlas/maintenance-log.md",
    "project-atlas/decisions/README.md",
    "project-atlas/decisions/TEMPLATE.md",
    "project-atlas/sql/README.md",
    "project-atlas/plans/in-flight/README.md",
    "project-atlas/plans/completed/README.md",
    "project-atlas/atlas.json",
]

EXISTING_REQUIRED_DIRS = [
    "project-atlas",
    "project-atlas/sql",
    "project-atlas/plans",
    "project-atlas/plans/in-flight",
    "project-atlas/plans/completed",
]

GREENFIELD_REQUIRED_FILES = [
    "project-atlas/README.md", "project-atlas/agent-playbook.md", "project-atlas/atlas.json",
    "project-atlas/plan/product-brief.md", "project-atlas/plan/stack-proposal.md",
    "project-atlas/plan/architecture-plan.md", "project-atlas/plan/data-model-plan.md",
    "project-atlas/plan/auth-plan.md", "project-atlas/plan/feature-plan.md",
    "project-atlas/plan/implementation-roadmap.md", "project-atlas/plan/open-questions.md",
    "project-atlas/context/project-overview.md", "project-atlas/context/architecture.md",
    "project-atlas/context/code-map.md", "project-atlas/context/open-questions.md",
    "project-atlas/plans/in-flight/README.md", "project-atlas/plans/completed/README.md",
]

GREENFIELD_REQUIRED_DIRS = [
    "project-atlas", "project-atlas/plan", "project-atlas/context",
    "project-atlas/plans", "project-atlas/plans/in-flight", "project-atlas/plans/completed",
]

PLATFORM_FILE_MAP = {
    "cfml": "project-atlas/platforms/cfml.md",
    "php": "project-atlas/platforms/php.md",
    "node-js": "project-atlas/platforms/node-js.md",
    "python": "project-atlas/platforms/python.md",
    "mysql": "project-atlas/platforms/mysql.md",
    "mssql": "project-atlas/platforms/mssql.md",
    "docker": "project-atlas/platforms/docker.md",
    "postgresql": "project-atlas/platforms/postgresql.md",
    "redis": "project-atlas/platforms/redis.md",
    "mongodb": "project-atlas/platforms/mongodb.md",
    "oracle-db": "project-atlas/platforms/oracle-db.md",
    "ci_cd": "project-atlas/platforms/ci-cd.md",     # covers jenkins, circleci, azure-pipelines, github-actions, gitlab-ci
    "testing": "project-atlas/platforms/testing.md",  # covers jest, playwright, cypress, vitest, mocha
}

# detect_stack.py exposes each CI tool and test framework as its own boolean; these two
# platform keys are true when any one of their underlying tool flags is true.
CI_CD_STACK_KEYS = ["github-actions", "gitlab-ci", "jenkins", "circleci", "azure-pipelines"]
TESTING_STACK_KEYS = ["jest", "playwright", "cypress", "vitest", "mocha"]

# Root-level files the skill generates at the repository root (not inside project-atlas/).
# These tell AI agents (Claude Code, OpenAI Agents, etc.) to read agent-playbook.md.
ROOT_GENERATED_FILES = ["CLAUDE.md", "AGENTS.md"]

FORBIDDEN_GENERATED_PATHS = [
    "project-atlas/references",
    "project-atlas/scripts",
    "project-atlas/templates",
    "project-atlas/agents",
    "project-atlas/SKILL.md",
]

ALIAS_FILES = {
    "project-atlas/application.md": ["project-atlas/project-overview.md", "project-atlas/stack.md", "project-atlas/architecture.md"],
    "project-atlas/auth.md": ["project-atlas/auth-and-access.md"],
    "project-atlas/api-catalog.md": ["project-atlas/code-map.md", "project-atlas/feature-index.md"],
    "project-atlas/project-atlas-index.md": ["project-atlas/README.md"],
    "project-atlas/workflows.md": ["project-atlas/agent-playbook.md", "project-atlas/handoffs/README.md"],
    "project-atlas/go-live-checklist.md": ["project-atlas/launch-checklist.md"],
    "project-atlas/deployment-checklist.md": ["project-atlas/launch-checklist.md", "project-atlas/deployment.md"],
}

# These files are intentionally lightweight scaffolds. They create durable locations for
# future human or agent notes and are expected to remain even when empty except README text.
ALLOWED_SCAFFOLD_FILES = {
    "project-atlas/decisions/README.md",
    "project-atlas/decisions/TEMPLATE.md",
    "project-atlas/handoffs/README.md",
    "project-atlas/snapshots/README.md",
    "project-atlas/plans/in-flight/README.md",
    "project-atlas/plans/completed/README.md",
    "project-atlas/.project-atlasignore",
    "project-atlas/maintenance-log.md",
    "project-atlas/tasks.md",
    "project-atlas/launch-checklist.md",
}

# Existing-codebase docs outside ALLOWED_SCAFFOLD_FILES must contain repo-specific content.
# These marker phrases indicate a generic scaffold was accidentally left behind.
SCAFFOLD_MARKERS = [
    "atlas scaffold",
    "generated placeholder",
    "greenfield project atlas placeholder",
    "replace with confirmed project details",
    "update with confirmed project context",
]

# This optional file is allowed when it is generated as an auxiliary CFML index. It never
# replaces the required CFC inventory coverage in code-map.md or platforms/cfml.md.
OPTIONAL_GENERATED_FILES = {
    "project-atlas/cfc-index.md",
}

def _read_skill_version() -> str:
    try:
        return (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


SKILL_VERSION = _read_skill_version()
ATLAS_SCHEMA_VERSION = 3
SUPPORTED_MANIFEST_VERSIONS = {2, 3}
LIFECYCLE_STATES = {"scaffolded", "evidence-generated", "enrichment-required", "verified", "stale"}
GENERATION_MODES = {"existing", "greenfield"}
MANAGED_START = "<!-- project-atlas:generated:{name}:start -->"
MANAGED_END = "<!-- project-atlas:generated:{name}:end -->"
CONTRACT_PATTERN = re.compile(r"<!--\s*project-atlas:contract\s+(\{.*?\})\s*-->", re.S)

DEFAULT_IGNORE_DIRS = {
    ".git", "node_modules", "vendor", "venv", ".venv", "__pycache__", "dist", "build",
    "coverage", ".cache", ".next", ".nuxt", "target", "bin", "obj", "WEB-INF",
}

SECRET_FILE_PATTERNS = [
    re.compile(r"(^|/)\.env($|\.)", re.I),
    re.compile(r"\.(pem|key|p12|pfx)$", re.I),
]

SECRET_VALUE_PATTERN = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|private[_-]?key|connectionstring)\s*[:=]\s*([^\s'\"#]+|'[^']*'|\"[^\"]*\")"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_commit(repo: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
            text=True, timeout=5, check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def repository_fingerprint(files: Iterable[str]) -> str:
    payload = "\n".join(sorted(files)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def content_digest(content: str | bytes) -> str:
    raw = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(raw).hexdigest()


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


@contextmanager
def atlas_lock(repo: Path, timeout_seconds: float = 10.0):
    lock_path = Path(repo) / "project-atlas/.update.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if datetime.now(timezone.utc).timestamp() >= deadline:
                    raise TimeoutError(f"Timed out waiting for Atlas lock: {lock_path}")
                import time
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def upsert_managed_section(text: str, name: str, content: str) -> Tuple[str, bool]:
    start = MANAGED_START.format(name=name)
    end = MANAGED_END.format(name=name)
    block = f"{start}\n{content.rstrip()}\n{end}"
    starts = [m.start() for m in re.finditer(re.escape(start), text)]
    ends = [m.start() for m in re.finditer(re.escape(end), text)]
    if len(starts) != len(ends) or len(starts) > 1 or (starts and starts[0] > ends[0]):
        raise ValueError(f"Malformed managed section: {name}")
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if pattern.search(text):
        updated = pattern.sub(block, text, count=1)
    else:
        updated = text.rstrip() + "\n\n" + block + "\n"
    return updated, updated != text


def managed_section_content(text: str, name: str) -> str | None:
    start = MANAGED_START.format(name=name)
    end = MANAGED_END.format(name=name)
    if text.count(start) != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
        return None
    return text.split(start, 1)[1].split(end, 1)[0].strip()


def root_has_valid_sentinels(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    start = "<!-- project-atlas:start -->"
    end = "<!-- project-atlas:end -->"
    return text.count(start) == 1 and text.count(end) == 1 and text.index(start) < text.index(end)


def posix(path: Path | str) -> str:
    return Path(path).as_posix()


def rel_posix(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def is_secret_path(rel_path: str) -> bool:
    rel_path = rel_path.replace("\\", "/")
    return any(pattern.search(rel_path) for pattern in SECRET_FILE_PATTERNS)


def redact_secrets(text: str) -> str:
    return SECRET_VALUE_PATTERN.sub(lambda m: f"{m.group(1)}=<redacted>", text)


def read_text_limited(path: Path, max_bytes: int = 200_000) -> Tuple[str, str]:
    """Return (text, status). Status is extracted, too large, unreadable, secret skipped."""
    try:
        size = path.stat().st_size
        if size > max_bytes:
            return "", "too large"
        raw = path.read_bytes()
        if b"\x00" in raw[:4096]:
            return "", "binary skipped"
        text = raw.decode("utf-8", errors="replace")
        return redact_secrets(text), "extracted"
    except Exception as exc:
        return "", f"unreadable: {exc}"


def load_ignore_patterns(repo: Path) -> List[str]:
    patterns: List[str] = []
    for name in [".project-atlasignore", "project-atlas/.project-atlasignore", ".gitignore"]:
        path = repo / name
        if path.exists() and path.is_file():
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    return patterns


def should_ignore(rel_path: str, is_dir: bool, extra_patterns: Iterable[str] = ()) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    if any(part in DEFAULT_IGNORE_DIRS for part in parts):
        return True
    if rel_path.startswith("project-atlas/snapshots/generated"):
        return True
    if rel_path.startswith("project-atlas/local"):
        return True
    if rel_path == "project-atlas/.update.lock":
        return True
    normalized = rel_path.rstrip("/")
    ignored = False
    for pattern in extra_patterns:
        p = pattern.strip()
        if not p:
            continue
        negated = p.startswith("!")
        if negated:
            p = p[1:]
        directory_only = p.endswith("/")
        p = p.rstrip("/")
        anchored = p.startswith("/")
        p = p.lstrip("/")
        basename = Path(normalized).name
        matched = (
            fnmatch.fnmatch(normalized, p) or
            (not anchored and fnmatch.fnmatch(basename, p)) or
            normalized == p or normalized.startswith(p + "/")
        )
        if directory_only and not (is_dir or normalized.startswith(p + "/")):
            matched = False
        if matched:
            ignored = not negated
    return ignored


def is_scaffold_placeholder(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in SCAFFOLD_MARKERS)


def detect_scaffold_leftovers(repo: Path) -> List[str]:
    leftovers: List[str] = []
    for rel in EXISTING_REQUIRED_FILES:
        if rel in ALLOWED_SCAFFOLD_FILES:
            continue
        path = repo / rel
        if path.is_file():
            try:
                if is_scaffold_placeholder(path.read_text(encoding="utf-8", errors="ignore")):
                    leftovers.append(rel)
            except Exception:
                pass
    return leftovers


SLOT_PATTERN = re.compile(r"\{\{[a-z0-9_]+\}\}")


def detect_unresolved_slots(repo: Path) -> List[str]:
    """Generated files must not retain {{slot}} placeholders from templates.
    Only required/platform files are checked; free-form folders like handoffs/
    may legitimately contain braces (e.g. code snippets)."""
    hits: List[str] = []
    candidates = [rel for rel in EXISTING_REQUIRED_FILES if rel.endswith(".md")]
    platform_dir = repo / "project-atlas/platforms"
    if platform_dir.is_dir():
        candidates += [p.relative_to(repo).as_posix() for p in platform_dir.glob("*.md")]
    for rel in candidates:
        path = repo / rel
        if path.is_file():
            try:
                if SLOT_PATTERN.search(path.read_text(encoding="utf-8", errors="ignore")):
                    hits.append(rel)
            except Exception:
                pass
    return sorted(set(hits))


def unexpected_platform_files(repo: Path, required_platforms: Iterable[str]) -> List[str]:
    allowed = {PLATFORM_FILE_MAP[p] for p in required_platforms if p in PLATFORM_FILE_MAP}
    platform_dir = repo / "project-atlas/platforms"
    if not platform_dir.is_dir():
        return []
    unexpected: List[str] = []
    for path in platform_dir.glob("*.md"):
        rel = path.relative_to(repo).as_posix()
        if rel not in allowed and rel not in OPTIONAL_GENERATED_FILES and path.name.lower() != "readme.md":
            unexpected.append(rel)
    return sorted(unexpected)


def write_file_once(path: Path, content: str, created=None, skipped=None) -> None:
    """For living, freeform documents (tasks.md, launch-checklist.md) that accumulate arbitrary
    hand-authored prose for the life of a project. Unlike write_file(), this never re-examines or
    overwrites existing content — not via the scaffold-placeholder heuristic (which is a substring
    match against a handful of generic phrases and can misfire on real prose that happens to
    contain one), and not even via --force. Once the file exists, the only way to reach it again is
    a managed section within it (already digest-protected) or a deliberate manual edit/delete."""
    if path.exists():
        if skipped is not None:
            skipped.append(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, content)
    if created is not None:
        created.append(path)


def write_file(path: Path, content: str, force: bool = False, backup: bool = False, created=None, skipped=None, updated=None, backed_up=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        try:
            existing_text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            existing_text = ""
        # Do not overwrite hand-authored Atlas content by default, but do repair known
        # generic scaffolds/placeholders. This prevents files like architecture.md from
        # being left as scaffold while still respecting real user edits.
        if not is_scaffold_placeholder(existing_text):
            if skipped is not None:
                skipped.append(path)
            return
    if path.exists() and backup:
        backup_path = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup_path)
        if backed_up is not None:
            backed_up.append(backup_path)
    existed = path.exists()
    atomic_write_text(path, content)
    if existed:
        if updated is not None:
            updated.append(path)
    else:
        if created is not None:
            created.append(path)


def append_log(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n")


def dump_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def detect_required_platforms(stack: Dict[str, Any] | None) -> List[str]:
    if not stack:
        return []
    platforms = []
    for key in [
        "cfml", "php", "node-js", "python", "mysql", "mssql", "docker",
        "postgresql", "redis", "mongodb", "oracle-db",
    ]:
        if stack.get(key):
            platforms.append(key)
    if any(stack.get(k) for k in CI_CD_STACK_KEYS):
        platforms.append("ci_cd")
    if any(stack.get(k) for k in TESTING_STACK_KEYS):
        platforms.append("testing")
    return platforms


SEMANTIC_FILES = {
    "project-atlas/project-overview.md": ["purpose", "users", "workflows"],
    "project-atlas/architecture.md": ["request flow", "boundaries"],
}


def _diagnostic(code: str, paths: Iterable[str], message: str, repair: str) -> Dict[str, Any]:
    return {"code": code, "paths": sorted(set(paths)), "message": message, "suggested_repair": repair}


def load_manifest(repo: Path) -> Tuple[Dict[str, Any], str | None]:
    path = repo / "project-atlas/atlas.json"
    try:
        return (json.loads(path.read_text(encoding="utf-8")), None) if path.is_file() else ({}, "missing")
    except json.JSONDecodeError as exc:
        return {}, f"invalid-json:{exc.msg}"
    except OSError as exc:
        return {}, f"unreadable:{exc}"


def migrate_manifest(data: Dict[str, Any], repo: Path | None = None) -> Dict[str, Any]:
    migrated = dict(data)
    migrated.setdefault("skill_version", "0.0.0")
    version = migrated.get("schema_version")
    if version == 2:
        migrated["schema_version"] = 3
        migrated.setdefault("last_verified_state", None)
        old_sections = migrated.get("managed_sections", {}) or {}
        artifacts: Dict[str, Any] = {}
        for rel, names in old_sections.items():
            name = names[0] if names else "evidence"
            digest = None
            if repo and (repo / rel).is_file():
                section = managed_section_content((repo / rel).read_text(encoding="utf-8", errors="ignore"), name)
                digest = content_digest(section) if section is not None else None
            artifacts[rel] = {"kind": "section", "section": name, "digest": digest}
        if repo:
            candidates = ["project-atlas/cfc-index.md"] + [p for p in PLATFORM_FILE_MAP.values()]
            for rel in candidates:
                if (repo / rel).is_file():
                    artifacts[rel] = {"kind": "file", "digest": content_digest((repo / rel).read_bytes())}
        migrated["managed_artifacts"] = artifacts
        migrated.pop("managed_sections", None)
    return migrated


def validate_manifest(data: Dict[str, Any]) -> List[Tuple[str, str]]:
    errors: List[Tuple[str, str]] = []
    required = {
        "schema_version": int, "generation_mode": str, "generated_at": str,
        "lifecycle_state": str, "repository_fingerprint": str,
        "detected_platforms": list, "selected_platforms": list,
        "managed_artifacts": dict, "sources": dict, "file_fingerprints": dict,
        "scan": dict, "warnings": list, "last_verified_state": (str, type(None)),
        "skill_version": str,
    }
    for key, expected in required.items():
        if key not in data:
            errors.append(("MANIFEST_FIELD_MISSING", key))
        elif not isinstance(data[key], expected):
            errors.append(("MANIFEST_FIELD_INVALID", key))
    version = data.get("schema_version")
    if isinstance(version, int) and version not in SUPPORTED_MANIFEST_VERSIONS:
        errors.append(("MANIFEST_SCHEMA_UNSUPPORTED", str(version)))
    if data.get("generation_mode") not in GENERATION_MODES:
        errors.append(("MANIFEST_FIELD_INVALID", "generation_mode"))
    if data.get("lifecycle_state") not in LIFECYCLE_STATES:
        errors.append(("MANIFEST_FIELD_INVALID", "lifecycle_state"))
    fingerprint = data.get("repository_fingerprint")
    if isinstance(fingerprint, str) and not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        errors.append(("MANIFEST_FIELD_INVALID", "repository_fingerprint"))
    for rel, digest in (data.get("file_fingerprints", {}) or {}).items():
        if not isinstance(rel, str) or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(("MANIFEST_FIELD_INVALID", f"file_fingerprints.{rel}"))
    for rel, owner in (data.get("managed_artifacts", {}) or {}).items():
        if not isinstance(owner, dict) or owner.get("kind") not in {"file", "section"}:
            errors.append(("MANIFEST_FIELD_INVALID", f"managed_artifacts.{rel}"))
            continue
        digest = owner.get("digest")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(("MANIFEST_FIELD_INVALID", f"managed_artifacts.{rel}.digest"))
        if owner.get("kind") == "section" and not isinstance(owner.get("section"), str):
            errors.append(("MANIFEST_FIELD_INVALID", f"managed_artifacts.{rel}.section"))
    return errors


def _contract_diagnostics(repo: Path, rel: str, criteria: Iterable[str]) -> List[Dict[str, Any]]:
    path = repo / rel
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    matches = CONTRACT_PATTERN.findall(text)
    if len(matches) != 1:
        return [_diagnostic("CONTRACT_INVALID", [rel], "Exactly one semantic contract marker is required.", "Restore the template contract marker and complete each criterion.")]
    try:
        contract = json.loads(matches[0])
    except json.JSONDecodeError:
        return [_diagnostic("CONTRACT_INVALID", [rel], "Semantic contract JSON is invalid.", "Repair the contract marker JSON.")]
    diagnostics: List[Dict[str, Any]] = []
    prose = CONTRACT_PATTERN.sub("", text)
    for start in re.findall(r"<!-- project-atlas:generated:([^:]+):start -->", prose):
        pattern = re.compile(re.escape(MANAGED_START.format(name=start)) + r".*?" + re.escape(MANAGED_END.format(name=start)), re.S)
        prose = pattern.sub("", prose)
    substantive = len(re.sub(r"[#*_`\s-]", "", prose)) >= 80
    for criterion in criteria:
        item = contract.get(criterion)
        if not isinstance(item, dict) or item.get("status") not in {"complete", "unknown", "pending"}:
            diagnostics.append(_diagnostic("CONTRACT_CRITERION_INVALID", [f"{rel}:{criterion}"], "Criterion is missing or has an invalid state.", "Set status to complete, unknown, or pending."))
            continue
        status = item.get("status")
        evidence = item.get("evidence", [])
        note = str(item.get("note", "")).strip()
        if status == "pending":
            diagnostics.append(_diagnostic("ENRICHMENT_REQUIRED", [f"{rel}:{criterion}"], "Semantic criterion is still pending.", "Complete it or record an explicit unknown with impact."))
        elif status == "complete":
            invalid = [p for p in evidence if not isinstance(p, str) or not (repo / p).exists()]
            if not substantive or len(note) < 20 or not evidence or invalid:
                diagnostics.append(_diagnostic("CONTRACT_EVIDENCE_INVALID", [f"{rel}:{criterion}"] + [str(p) for p in invalid], "Complete criteria require a substantive criterion note, document prose, and valid evidence paths.", "Add a supported criterion note, prose, and at least one repository-relative evidence path."))
        elif status == "unknown" and len(note) < 10:
            diagnostics.append(_diagnostic("CONTRACT_UNKNOWN_INCOMPLETE", [f"{rel}:{criterion}"], "Unknown criteria must explain why the fact matters.", "Add a meaningful impact note."))
    return diagnostics


def verify_existing_atlas(repo: Path, stack: Dict[str, Any] | None = None, scan: Dict[str, Any] | None = None, selected_platforms: Iterable[str] = (), level: str = "semantic", generation_mode: str = "auto") -> Dict[str, Any]:
    repo = Path(repo).resolve()
    raw_manifest, manifest_error = load_manifest(repo)
    manifest = migrate_manifest(raw_manifest, repo) if raw_manifest else {}
    mode = manifest.get("generation_mode") if generation_mode == "auto" and manifest else generation_mode
    if mode == "auto":
        mode = "greenfield" if (repo / "project-atlas/plan").is_dir() else "existing"
    required_files = GREENFIELD_REQUIRED_FILES if mode == "greenfield" else EXISTING_REQUIRED_FILES
    required_dirs = GREENFIELD_REQUIRED_DIRS if mode == "greenfield" else EXISTING_REQUIRED_DIRS
    effective_stack = stack or ((scan or {}).get("stack", {}) if scan else {})
    required_platforms = set() if mode == "greenfield" else set(selected_platforms or []) | set(detect_required_platforms(effective_stack))

    missing_files = [p for p in required_files if not (repo / p).is_file()]
    missing_dirs = [p for p in required_dirs if not (repo / p).is_dir()]
    missing_platform_files = [PLATFORM_FILE_MAP[p] for p in sorted(required_platforms) if p in PLATFORM_FILE_MAP and not (repo / PLATFORM_FILE_MAP[p]).is_file()]
    missing_root_files = [f for f in ROOT_GENERATED_FILES if not (repo / f).is_file()]
    invalid_root_sentinels = [f for f in ROOT_GENERATED_FILES if (repo / f).is_file() and not root_has_valid_sentinels(repo / f)]
    forbidden_paths = [p for p in FORBIDDEN_GENERATED_PATHS if (repo / p).exists()]
    invalid_aliases = [p for p in ALIAS_FILES if (repo / p).exists()] if mode == "existing" else []
    scaffold_leftovers = detect_scaffold_leftovers(repo) if mode == "existing" else []
    unexpected_platforms = unexpected_platform_files(repo, required_platforms) if mode == "existing" else []
    unresolved_slots = detect_unresolved_slots(repo) if mode == "existing" else []
    diagnostics: List[Dict[str, Any]] = []

    if missing_files or missing_dirs or missing_platform_files or missing_root_files:
        diagnostics.append(_diagnostic("STRUCTURE_MISSING", missing_files + missing_dirs + missing_platform_files + missing_root_files, "Required Atlas structure is incomplete.", "Run an Atlas update or bootstrap repair."))
    if invalid_root_sentinels:
        diagnostics.append(_diagnostic("MANAGED_SENTINEL_INVALID", invalid_root_sentinels, "Root agent sentinel pairs are missing, duplicated, or reversed.", "Restore exactly one ordered project-atlas sentinel pair."))
    if manifest_error and manifest_error != "missing":
        diagnostics.append(_diagnostic("MANIFEST_INVALID_JSON", ["project-atlas/atlas.json"], manifest_error, "Repair or regenerate the manifest."))
    elif manifest:
        for code, field in validate_manifest(manifest):
            diagnostics.append(_diagnostic(code, [f"project-atlas/atlas.json:{field}"], "Manifest validation failed.", "Migrate or regenerate the manifest."))
        if manifest.get("skill_version") != SKILL_VERSION:
            diagnostics.append(_diagnostic(
                "SKILL_VERSION_STALE", ["project-atlas/atlas.json:skill_version"],
                f"Atlas was generated by skill version {manifest.get('skill_version')!r}; installed skill is {SKILL_VERSION!r}.",
                "Run `maintain_atlas.py --mode reconcile` (or a normal --mode update) to bring the Atlas current.",
            ))
    if forbidden_paths:
        diagnostics.append(_diagnostic("FORBIDDEN_PATH", forbidden_paths, "Skill-internal paths were copied into the repository.", "Remove these generated paths."))
    if invalid_aliases:
        diagnostics.append(_diagnostic("INVALID_ALIAS", invalid_aliases, "Legacy alias documents are present.", "Move durable content to the canonical document."))
    if scaffold_leftovers or unresolved_slots:
        diagnostics.append(_diagnostic("UNRESOLVED_SCAFFOLD", scaffold_leftovers + unresolved_slots, "Generated placeholders remain.", "Complete enrichment or record explicit unknowns."))
    if unexpected_platforms:
        diagnostics.append(_diagnostic("UNEXPECTED_PLATFORM", unexpected_platforms, "Unexpected platform documents were found.", "Remove them or explicitly select their platforms."))

    cfc_inventory_gaps: List[str] = []
    stale_sources: List[str] = []
    generated_drift: List[str] = []
    if manifest:
        for rel, owner in (manifest.get("managed_artifacts", {}) or {}).items():
            path = repo / rel
            expected = owner.get("digest") if isinstance(owner, dict) else None
            actual = None
            if path.is_file() and isinstance(owner, dict) and owner.get("kind") == "section":
                section = managed_section_content(path.read_text(encoding="utf-8", errors="ignore"), owner.get("section", "evidence"))
                if section is None:
                    diagnostics.append(_diagnostic("MANAGED_SENTINEL_INVALID", [rel], "Managed section sentinels are missing, duplicated, or reversed.", "Restore exactly one ordered sentinel pair."))
                actual = content_digest(section) if section is not None else None
            elif path.is_file():
                actual = content_digest(path.read_bytes())
            if expected and actual != expected:
                diagnostics.append(_diagnostic("GENERATED_CONTENT_MODIFIED", [rel], "Generated content differs from its recorded digest.", "Restore it, accept it as hand-authored, or regenerate with explicit force."))

    if level in {"evidence", "semantic"} and scan and mode == "existing":
        cfc_items = scan.get("cfc_inventory", []) or []
        if cfc_items:
            cfc_index = repo / "project-atlas/cfc-index.md"
            map_text = (repo / "project-atlas/code-map.md").read_text(encoding="utf-8", errors="ignore")
            code_text = cfc_index.read_text(encoding="utf-8", errors="ignore") if cfc_index.exists() else map_text
            cfc_inventory_gaps = [item.get("path", "") for item in cfc_items if item.get("path") and item.get("path") not in code_text]
            if cfc_index.exists() and any(item.get("path") in map_text for item in cfc_items):
                diagnostics.append(_diagnostic("CFC_INVENTORY_DUPLICATED", ["project-atlas/code-map.md", "project-atlas/cfc-index.md"], "Complete CFML inventory appears in more than one location.", "Keep the full inventory only in cfc-index.md and link to it from code-map.md."))
        for sources in (manifest.get("sources", {}) or {}).values():
            stale_sources.extend(rel for rel in sources if not (repo / rel).exists())
        app_fingerprints = {p: v for p, v in (scan.get("file_fingerprints", {}) or {}).items() if not p.startswith("project-atlas/") and p not in ROOT_GENERATED_FILES}
        current_fingerprint = repository_fingerprint(f"{p}:{value}" for p, value in app_fingerprints.items())
        if manifest.get("repository_fingerprint") and manifest.get("repository_fingerprint") != current_fingerprint:
            generated_drift.append("project-atlas/atlas.json")
        if cfc_inventory_gaps:
            diagnostics.append(_diagnostic("CFC_INVENTORY_GAP", cfc_inventory_gaps, "CFML inventory is incomplete.", "Run an evidence update."))
        if stale_sources:
            diagnostics.append(_diagnostic("STALE_SOURCE", stale_sources, "Atlas evidence points to missing source paths.", "Update or remove stale evidence references."))
        if generated_drift:
            diagnostics.append(_diagnostic("GENERATED_DRIFT", generated_drift, "Repository contents changed after the last Atlas update.", "Run an Atlas update."))
        if scan.get("truncated"):
            diagnostics.append(_diagnostic("PARTIAL_SCAN", [str(scan.get("truncated_at", "unknown"))], "Repository scan was truncated.", "Increase --max-files."))

    semantic_gaps: List[str] = []
    if level == "semantic":
        semantic_files = SEMANTIC_FILES if mode == "existing" else {
            "project-atlas/plan/product-brief.md": ["purpose", "users", "outcomes"],
            "project-atlas/plan/architecture-plan.md": ["request flow", "boundaries"],
        }
        before = len(diagnostics)
        for rel, criteria in semantic_files.items():
            diagnostics.extend(_contract_diagnostics(repo, rel, criteria))
        semantic_gaps = sorted({path for diagnostic in diagnostics[before:] for path in diagnostic["paths"]})

    status = "failed" if diagnostics else "passed"
    if stale_sources or generated_drift:
        lifecycle_state = "stale"
    elif level == "semantic" and semantic_gaps:
        lifecycle_state = "enrichment-required"
    elif status == "passed" and level == "semantic":
        lifecycle_state = "verified"
    elif manifest:
        lifecycle_state = "evidence-generated"
    else:
        lifecycle_state = "scaffolded"
    return {
        "status": status, "generation_mode": mode, "level": level,
        "lifecycle_state": lifecycle_state, "diagnostics": diagnostics,
        "missing_required_files": missing_files, "missing_required_directories": missing_dirs,
        "missing_platform_files": missing_platform_files, "missing_root_files": missing_root_files,
        "invalid_root_sentinels": invalid_root_sentinels,
        "forbidden_generated_paths": forbidden_paths, "invalid_aliases_detected": invalid_aliases,
        "scaffold_leftovers": scaffold_leftovers, "unexpected_platform_files": unexpected_platforms,
        "cfc_inventory_gaps": cfc_inventory_gaps, "unresolved_slots": unresolved_slots,
        "stale_sources": sorted(set(stale_sources)), "generated_drift": generated_drift,
        "semantic_gaps": semantic_gaps,
    }
