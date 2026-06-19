#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ATLAS_DIR = "project-atlas"

EXISTING_REQUIRED_FILES = [
    "project-atlas/README.md",
    "project-atlas/agent-playbook.md",
    "project-atlas/project-overview.md",
    "project-atlas/stack.md",
    "project-atlas/architecture.md",
    "project-atlas/code-map.md",
    "project-atlas/feature-index.md",
    "project-atlas/database.md",
    "project-atlas/auth-and-access.md",
    "project-atlas/conventions.md",
    "project-atlas/dependency-map.md",
    "project-atlas/testing.md",
    "project-atlas/deployment.md",
    "project-atlas/known-risks.md",
    "project-atlas/glossary.md",
    "project-atlas/open-questions.md",
    "project-atlas/maintenance-log.md",
    "project-atlas/.project-atlasignore",
    "project-atlas/decisions/README.md",
    "project-atlas/handoffs/README.md",
    "project-atlas/snapshots/README.md",
]

EXISTING_REQUIRED_DIRS = [
    "project-atlas/platforms",
    "project-atlas/decisions",
    "project-atlas/handoffs",
    "project-atlas/snapshots",
]

PLATFORM_FILE_MAP = {
    "cfml": "project-atlas/platforms/cfml.md",
    "php": "project-atlas/platforms/php.md",
    "node-js": "project-atlas/platforms/node-js.md",
    "python": "project-atlas/platforms/python.md",
    "mysql": "project-atlas/platforms/mysql.md",
    "mssql": "project-atlas/platforms/mssql.md",
    "docker": "project-atlas/platforms/docker.md",
}

# Root-level files the skill generates at the repository root (not inside project-atlas/).
# These tell AI agents (Claude Code, OpenAI Agents, etc.) to read agent-playbook.md.
ROOT_GENERATED_FILES = ["CLAUDE.md", "AGENTS.md"]

# Root-level files generated at the repository root (not inside project-atlas/).
# These instruct AI agents (Claude Code, OpenAI Agents, etc.) to read agent-playbook.md.
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
    "project-atlas/schema.md": ["project-atlas/database.md"],
}

# These files are intentionally lightweight scaffolds. They create durable locations for
# future human or agent notes and are expected to remain even when empty except README text.
ALLOWED_SCAFFOLD_FILES = {
    "project-atlas/decisions/README.md",
    "project-atlas/handoffs/README.md",
    "project-atlas/snapshots/README.md",
    "project-atlas/.project-atlasignore",
    "project-atlas/maintenance-log.md",
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

DEFAULT_IGNORE_DIRS = {
    ".git", "node_modules", "vendor", "venv", ".venv", "__pycache__", "dist", "build",
    "coverage", ".cache", ".next", ".nuxt", "target", "bin", "obj", "WEB-INF/lucee",
}

SECRET_FILE_PATTERNS = [
    re.compile(r"(^|/)\.env($|\.)", re.I),
    re.compile(r"\.(pem|key|p12|pfx)$", re.I),
]

SECRET_VALUE_PATTERN = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|private[_-]?key|connectionstring)\s*[:=]\s*([^\s'\"#]+|'[^']*'|\"[^\"]*\")"
)


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


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
                    patterns.append(line.rstrip("/"))
    return patterns


def should_ignore(rel_path: str, is_dir: bool, extra_patterns: Iterable[str] = ()) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    if any(part in DEFAULT_IGNORE_DIRS for part in parts):
        return True
    if rel_path.startswith("project-atlas/snapshots/generated"):
        return True
    normalized = rel_path.rstrip("/")
    for pattern in extra_patterns:
        p = pattern.strip().rstrip("/")
        if not p:
            continue
        if normalized == p or normalized.startswith(p + "/"):
            return True
        if p.startswith("*") and normalized.endswith(p[1:]):
            return True
    return False


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
    path.write_text(content, encoding="utf-8")
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
    for key in ["cfml", "php", "node-js", "python", "mysql", "mssql", "docker"]:
        if stack.get(key):
            platforms.append(key)
    return platforms


def verify_existing_atlas(repo: Path, stack: Dict[str, Any] | None = None, scan: Dict[str, Any] | None = None, selected_platforms: Iterable[str] = ()) -> Dict[str, Any]:
    repo = Path(repo).resolve()
    required_platforms = set(selected_platforms or []) | set(detect_required_platforms(stack or {}))

    missing_files = [p for p in EXISTING_REQUIRED_FILES if not (repo / p).is_file()]
    missing_dirs = [p for p in EXISTING_REQUIRED_DIRS if not (repo / p).is_dir()]
    missing_platform_files = [PLATFORM_FILE_MAP[p] for p in sorted(required_platforms) if p in PLATFORM_FILE_MAP and not (repo / PLATFORM_FILE_MAP[p]).is_file()]
    missing_root_files = [f for f in ROOT_GENERATED_FILES if not (repo / f).is_file()]
    forbidden_paths = [p for p in FORBIDDEN_GENERATED_PATHS if (repo / p).exists()]
    invalid_aliases = [p for p in ALIAS_FILES if (repo / p).exists()]
    scaffold_leftovers = detect_scaffold_leftovers(repo)
    unexpected_platforms = unexpected_platform_files(repo, required_platforms)

    cfc_inventory_gaps: List[str] = []
    if scan:
        cfc_items = scan.get("cfc_inventory", []) or []
        if cfc_items:
            code_text = ""
            code_candidates = [repo / "project-atlas/code-map.md", repo / "project-atlas/platforms/cfml.md"]
            for candidate in code_candidates:
                if candidate.exists():
                    code_text += "\n" + candidate.read_text(encoding="utf-8", errors="ignore")
            cfc_index = repo / "project-atlas/cfc-index.md"
            if cfc_index.exists() and "cfc-index.md" in code_text:
                code_text += "\n" + cfc_index.read_text(encoding="utf-8", errors="ignore")
            for item in cfc_items:
                rel = item.get("path", "")
                if rel and rel not in code_text:
                    cfc_inventory_gaps.append(rel)

    status = "passed"
    if (
        missing_files or missing_dirs or missing_platform_files or missing_root_files or
        forbidden_paths or invalid_aliases or scaffold_leftovers or unexpected_platforms or
        cfc_inventory_gaps
    ):
        status = "failed"

    return {
        "status": status,
        "missing_required_files": missing_files,
        "missing_required_directories": missing_dirs,
        "missing_platform_files": missing_platform_files,
        "missing_root_files": missing_root_files,
        "forbidden_generated_paths": forbidden_paths,
        "invalid_aliases_detected": invalid_aliases,
        "scaffold_leftovers": scaffold_leftovers,
        "unexpected_platform_files": unexpected_platforms,
        "cfc_inventory_gaps": cfc_inventory_gaps,
    }
