#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from scan_repo import scan_repository
    from utils import (
        EXISTING_REQUIRED_FILES, EXISTING_REQUIRED_DIRS, PLATFORM_FILE_MAP,
        FORBIDDEN_GENERATED_PATHS, ALIAS_FILES, append_log, detect_required_platforms,
        dump_json, now_iso, verify_existing_atlas, write_file, write_file_once,
        ROOT_GENERATED_FILES, ATLAS_SCHEMA_VERSION, SKILL_VERSION, repository_fingerprint,
        git_commit, upsert_managed_section, managed_section_content, content_digest,
        atomic_write_text, load_manifest, migrate_manifest, atlas_lock,
        root_has_valid_sentinels
    )
except ImportError:
    from .scan_repo import scan_repository
    from .utils import (
        EXISTING_REQUIRED_FILES, EXISTING_REQUIRED_DIRS, PLATFORM_FILE_MAP,
        FORBIDDEN_GENERATED_PATHS, ALIAS_FILES, append_log, detect_required_platforms,
        dump_json, now_iso, verify_existing_atlas, write_file, write_file_once,
        ROOT_GENERATED_FILES, ATLAS_SCHEMA_VERSION, SKILL_VERSION, repository_fingerprint,
        git_commit, upsert_managed_section, managed_section_content, content_digest,
        atomic_write_text, load_manifest, migrate_manifest, atlas_lock,
        root_has_valid_sentinels
    )


# Templates are the source of truth for generated Atlas content. They live in the
# Skill package (next to scripts/), never in the target repository.
SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = SKILL_DIR / "templates"

SLOT_RE = re.compile(r"\{\{([a-z0-9_]+)\}\}")
CONTRACT_RE = re.compile(r"<!--\s*project-atlas:contract\s+\{.*?\}\s*-->", re.S)
CONTRACT_DEFAULTS = {
    "project-atlas/project-overview.md": ["purpose", "users", "workflows"],
    "project-atlas/architecture.md": ["request flow", "boundaries"],
    "project-atlas/plan/product-brief.md": ["purpose", "users", "outcomes"],
    "project-atlas/plan/architecture-plan.md": ["request flow", "boundaries"],
}


def resolve_site_url(repo: Path, site_url: str) -> str:
    """An explicitly-passed --site-url always wins. Otherwise, reuse whatever is already recorded
    in agent-playbook.md so repeated update/reconcile/convert runs that don't re-supply it can't
    regress a real URL back to the placeholder text."""
    if site_url:
        return site_url
    playbook_path = repo / "project-atlas/agent-playbook.md"
    if playbook_path.is_file():
        match = re.search(r"^Public-facing site URL:\s*(.+)$", playbook_path.read_text(encoding="utf-8", errors="ignore"), re.M)
        if match and not match.group(1).strip().startswith("_Not yet provided"):
            return match.group(1).strip()
    return ""


def load_template(mode: str, rel: str) -> Optional[str]:
    path = TEMPLATES_DIR / mode / rel
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except Exception:
        pass
    return None


def render_template(text: str, context: Dict[str, str]) -> str:
    return SLOT_RE.sub(lambda m: context.get(m.group(1), m.group(0)), text)


def ensure_contract_marker(repo: Path, rel: str, updated: List[Path]) -> None:
    path = repo / rel
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="ignore")
    if CONTRACT_RE.search(text):
        return
    contract = {criterion: {"status": "pending", "evidence": [], "note": ""} for criterion in CONTRACT_DEFAULTS[rel]}
    lines = text.splitlines()
    marker = "<!-- project-atlas:contract " + json.dumps(contract, separators=(",", ":")) + " -->"
    lines.insert(1 if lines else 0, "\n" + marker)
    atomic_write_text(path, "\n".join(lines).rstrip() + "\n")
    updated.append(path)


def generic_placeholder(rel: str) -> str:
    return f"# {Path(rel).stem.replace('-', ' ').title()}\n\nGenerated placeholder. Update with confirmed project context.\n"


def bullet(items: Iterable[str], limit: int = 50) -> str:
    items = list(items)[:limit]
    if not items:
        return "- none detected\n"
    return "".join(f"- `{item}`\n" for item in items)


def table(rows: List[List[str]], headers: List[str]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        out.append("| " + " | ".join(str(c).replace("\n", "<br>") for c in row) + " |")
    return "\n".join(out) + "\n"


STACK_CATEGORIES = [
    ("Languages / runtimes", ["cfml", "php", "node-js", "typescript", "python", "ruby", "java", "dotnet", "go", "rust", "elixir"]),
    ("Backend frameworks / CMS", ["laravel", "symfony", "wordpress", "drupal", "rails", "spring", "django", "flask", "fastapi", "phoenix"]),
    ("Frontend frameworks", ["react", "vue", "angular", "svelte", "nextjs", "nuxt", "tailwindcss", "graphql"]),
    ("Databases", ["mysql", "mssql", "postgresql", "mongodb", "redis", "sqlite", "oracle-db"]),
    ("Infrastructure / deployment", ["docker", "kubernetes", "terraform", "serverless", "rabbitmq", "kafka", "elasticsearch"]),
]


def stack_lines(stack: Dict[str, Any]) -> str:
    sections = []
    for category, keys in STACK_CATEGORIES:
        rows = [[key, "yes" if stack.get(key) else "no"] for key in keys]
        sections.append(f"### {category}\n\n" + table(rows, ["Platform", "Detected"]))
    return "\n".join(sections)


def cfc_inventory_markdown(scan: Dict[str, Any]) -> str:
    cfc_items = scan.get("cfc_inventory", []) or []
    if not cfc_items:
        return "No `.cfc` files detected.\n"
    rows = []
    for item in cfc_items:
        methods = item.get("methods") or []
        method_text = ", ".join(f"`{m}`" for m in methods) if methods else "_none listed_"
        rows.append([item.get("path", ""), item.get("role", "component"), method_text, item.get("status", "unknown")])
    return table(rows, ["CFC", "Likely role", "Functions / methods", "Extraction status"])


def third_party_indicators_markdown(scan: Dict[str, Any]) -> str:
    items = scan.get("third_party_indicators", []) or []
    if not items:
        return "- none detected by scan\n"
    out = []
    for item in items:
        files = ", ".join(f"`{p}`" for p in item.get("files", []))
        out.append(f"- **{item.get('service', 'unknown')}** — seen in: {files}\n")
    return "".join(out)


def cfc_index_content(scan: Dict[str, Any]) -> str:
    cfc_items = scan.get("cfc_inventory", []) or []
    if not cfc_items:
        return ""
    return f"""
# CFML Component / Method Index

This optional generated index supports `code-map.md` and `platforms/cfml.md`. It does not replace them.

{cfc_inventory_markdown(scan)}
"""


def generated_code_map(scan: Dict[str, Any], external_cfc_index: bool = False) -> str:
    context = build_context(scan)
    buckets = scan.get("buckets", {}) or {}
    service_paths = buckets.get("services", []) + buckets.get("repositories", []) + buckets.get("components", [])
    if external_cfc_index:
        service_paths = [path for path in service_paths if not path.lower().endswith(".cfc")]
    return "\n".join([
        "## Generated navigation evidence",
        f"- Files scanned: {context['file_count']}",
        f"- Directories scanned: {context['dir_count']}",
        "### Entry points", context["entry_points_list"].rstrip(),
        "### Routes and controllers", context["controllers_routes_handlers_list"].rstrip(),
        "### Services and data access", bullet(service_paths, limit=120).rstrip(),
    ])


def manifest_content(repo: Path, scan: Dict[str, Any], lifecycle_state: str, selected_platforms: Iterable[str], managed_artifacts: Dict[str, Any], generation_mode: str = "existing", last_verified_state: str | None = None) -> str:
    buckets = scan.get("buckets", {}) or {}
    sources = {
        "project-overview.md": (buckets.get("docs", []) or [])[:20],
        "architecture.md": (buckets.get("entry_points", []) + buckets.get("controllers", []) + buckets.get("services", []))[:50],
        "code-map.md": (buckets.get("entry_points", []) + buckets.get("routes", []) + buckets.get("services", []))[:100],
        "operations.md": (buckets.get("config", []) + buckets.get("deployment", []) + buckets.get("ci_cd", []))[:80],
    }
    warnings = []
    if scan.get("truncated"):
        warnings.append({"code": "PARTIAL_SCAN", "path": scan.get("truncated_at")})
    for item in scan.get("cfc_inventory", []) or []:
        if item.get("status") not in {"extracted", "no methods found"}:
            warnings.append({"code": "EXTRACTION_WARNING", "path": item.get("path"), "status": item.get("status")})
    app_fingerprints = {p: v for p, v in (scan.get("file_fingerprints", {}) or {}).items() if not p.startswith("project-atlas/") and p not in ROOT_GENERATED_FILES}
    data = {
        "schema_version": ATLAS_SCHEMA_VERSION,
        "skill_version": SKILL_VERSION,
        "generation_mode": generation_mode,
        "generated_at": now_iso(),
        "lifecycle_state": lifecycle_state,
        "repository_fingerprint": repository_fingerprint(f"{p}:{value}" for p, value in app_fingerprints.items()),
        "git_commit": git_commit(repo),
        "detected_platforms": detect_required_platforms(scan.get("stack", {}) or {}),
        "selected_platforms": sorted(set(selected_platforms)),
        "last_verified_state": last_verified_state,
        "managed_artifacts": managed_artifacts,
        "sources": sources,
        "file_fingerprints": app_fingerprints,
        "scan": {"file_count": scan.get("file_count", 0), "truncated": bool(scan.get("truncated")), "truncated_at": scan.get("truncated_at")},
        "warnings": warnings,
    }
    return json.dumps(data, indent=2, sort_keys=True) + "\n"



# ---------------------------------------------------------------------------
# Root file generation (CLAUDE.md and AGENTS.md at the repository root)
# ---------------------------------------------------------------------------

_ATLAS_SECTION_START = "<!-- project-atlas:start -->"
_ATLAS_SECTION_END   = "<!-- project-atlas:end -->"


def _claude_md_section(repo_name: str) -> str:
    return f"""{_ATLAS_SECTION_START}
## Project Atlas — Claude Code instructions

This repository uses **Project Atlas** for AI-readable project context.

### Required reading at every session start

Before writing or editing any code, read these files:

1. `project-atlas/agent-playbook.md` — rules, conventions, and what to update
2. `project-atlas/project-overview.md` — what this project does
3. `project-atlas/architecture.md` — request flow and boundaries
4. `project-atlas/operations.md` — testing, deployment, and recovery context

### After every task

Check whether code, architecture, auth, database, deployment, or features changed durably.
If yes, update the relevant Atlas files and append a new entry to
`project-atlas/maintenance-log.md` — add it at the end; don't read or rewrite the rest of the
file for a routine entry. Follow the table in `project-atlas/agent-playbook.md` to know which
file to update.

If the change introduced anything that differs between dev, stage, and live — env vars,
keys, config values, folders, scheduled tasks, SQL to run, or third-party service setup
(Stripe, Authorize.net, APIs, webhooks) — add an item to `project-atlas/launch-checklist.md`.

Do not update Atlas for formatting-only, comment-only, debug, or reverted changes.
{_ATLAS_SECTION_END}
"""


def _agents_md_section(repo_name: str) -> str:
    return f"""{_ATLAS_SECTION_START}
## Project Atlas — Agent instructions

This repository uses **Project Atlas** for AI-readable project context.

### Required reading at every session start

Before writing or editing any code, read these files:

1. `project-atlas/agent-playbook.md` — rules, conventions, and what to update
2. `project-atlas/project-overview.md` — what this project does
3. `project-atlas/architecture.md` — request flow and boundaries
4. `project-atlas/operations.md` — testing, deployment, and recovery context

### After every task

Check whether code, architecture, auth, database, deployment, or features changed durably.
If yes, update the relevant Atlas files and append a new entry to
`project-atlas/maintenance-log.md` — add it at the end; don't read or rewrite the rest of the
file for a routine entry. Follow the table in `project-atlas/agent-playbook.md` to know which
file to update.

If the change introduced anything that differs between dev, stage, and live — env vars,
keys, config values, folders, scheduled tasks, SQL to run, or third-party service setup
(Stripe, Authorize.net, APIs, webhooks) — add an item to `project-atlas/launch-checklist.md`.

Do not update Atlas for formatting-only, comment-only, debug, or reverted changes.
{_ATLAS_SECTION_END}
"""


_ROOT_SECTIONS = {
    "CLAUDE.md": _claude_md_section,
    "AGENTS.md": _agents_md_section,
}


def _greenfield_agent_section(repo_name: str) -> str:
    return f"""{_ATLAS_SECTION_START}
## Project Atlas — Greenfield instructions

This repository uses Project Atlas for product and implementation planning. Before implementation,
read `project-atlas/plan/product-brief.md`, `architecture-plan.md`, `feature-plan.md`,
`implementation-roadmap.md`, and `open-questions.md`. Do not invent unresolved facts.

Update plan contracts and context as decisions become supported. Convert the Atlas to existing-codebase
mode when implementation evidence exists.
{_ATLAS_SECTION_END}
"""


def write_root_agent_file(path: Path, repo_name: str, created: list, updated: list, skipped: list, generation_mode: str = "existing") -> None:
    """Create or update CLAUDE.md / AGENTS.md with our Project Atlas section.

    - File absent  → create it containing just our section.
    - File present, section absent  → append our section.
    - File present, section present → replace our section in-place.
    """
    fn = path.name
    section_fn = _ROOT_SECTIONS.get(fn)
    if section_fn is None:
        return
    section = (_greenfield_agent_section(repo_name) if generation_mode == "greenfield" else section_fn(repo_name)).strip() + "\n"

    if not path.exists():
        atomic_write_text(path, section)
        created.append(path)
        return

    existing = path.read_text(encoding="utf-8", errors="ignore")
    if (_ATLAS_SECTION_START in existing or _ATLAS_SECTION_END in existing) and not root_has_valid_sentinels(path):
        skipped.append(path)
        return
    if _ATLAS_SECTION_START in existing and _ATLAS_SECTION_END in existing:
        # Replace existing section
        before = existing[:existing.index(_ATLAS_SECTION_START)]
        after  = existing[existing.index(_ATLAS_SECTION_END) + len(_ATLAS_SECTION_END):]
        new_text = before + section + after.lstrip("\n")
        if new_text != existing:
            atomic_write_text(path, new_text)
            updated.append(path)
        else:
            skipped.append(path)
    else:
        # Append our section
        new_text = existing.rstrip() + "\n\n" + section
        atomic_write_text(path, new_text)
        updated.append(path)


def build_context(scan: Dict[str, Any], site_url: str = "") -> Dict[str, str]:
    """Flat string context for {{slot}} substitution in templates."""
    stack = scan.get("stack", {}) or {}
    buckets = scan.get("buckets", {}) or {}
    markers = stack.get("markers", []) or []
    files = scan.get("files", []) or []
    manifest_names = {"box.json", "server.json", "composer.json", "package.json", "pyproject.toml", "requirements.txt"}

    def yes_no(key: str) -> str:
        return "yes" if stack.get(key) else "no"

    db_flag_labels = [
        ("mssql", "MSSQL"), ("mysql", "MySQL"), ("postgresql", "PostgreSQL"),
        ("mongodb", "MongoDB"), ("redis", "Redis"), ("sqlite", "SQLite"), ("oracle-db", "Oracle"),
    ]
    db_indicators = " ".join(label for key, label in db_flag_labels if stack.get(key)) or "none detected"

    return {
        "generated": now_iso(),
        "repo_name": Path(scan.get("repo", ".")).name,
        "repo_path": str(scan.get("repo", ".")),
        "site_url": site_url or "_Not yet provided — ask the user and record it here._",
        "file_count": str(scan.get("file_count", 0)),
        "dir_count": str(scan.get("dir_count", 0)),
        "stack_table": stack_lines(stack),
        "markers_list": bullet(markers),
        "dependency_markers_list": bullet([p for p in markers if Path(p).name.lower() in manifest_names]),
        "cfc_inventory_table": cfc_inventory_markdown(scan),
        "cfml_files_list": bullet([p for p in files if p.lower().endswith((".cfc", ".cfm"))], limit=200),
        "cfm_pages_list": bullet(scan.get("cfm_pages", []) or [p for p in files if p.lower().endswith(".cfm")], limit=150),
        "datasources_list": bullet(scan.get("datasources", [])) if scan.get("datasources") else "No datasource names extracted. Check `Application.cfc` and query calls, then record names here (never connection values).\n",
        "cfc_syntax_summary": scan.get("cfc_syntax_summary", "Not analyzed."),
        "entry_points_list": bullet(buckets.get("entry_points", [])),
        "routes_list": bullet(buckets.get("routes", [])),
        "controllers_list": bullet(buckets.get("controllers", [])),
        "handlers_list": bullet(buckets.get("handlers", [])),
        "services_list": bullet(buckets.get("services", [])),
        "repositories_list": bullet(buckets.get("repositories", [])),
        "models_components_list": bullet(buckets.get("models", []) + buckets.get("entities", []) + buckets.get("components", [])),
        "controllers_routes_handlers_list": bullet(buckets.get("controllers", []) + buckets.get("routes", []) + buckets.get("handlers", []), limit=100),
        "services_data_components_list": bullet(buckets.get("services", []) + buckets.get("repositories", []) + buckets.get("components", []), limit=120),
        "feature_candidates_list": bullet(buckets.get("controllers", []) + buckets.get("handlers", []) + buckets.get("views", []) + buckets.get("routes", []), limit=120),
        "database_candidates_list": bullet(buckets.get("database", []) + buckets.get("migrations", []), limit=120),
        "auth_candidates_list": bullet(buckets.get("auth_candidates", []) + buckets.get("permission_candidates", []), limit=120),
        "tests_list": bullet(buckets.get("tests", []), limit=120),
        "deployment_candidates_list": bullet(buckets.get("deployment", []) + buckets.get("ci_cd", []), limit=120),
        "launch_config_candidates_list": bullet(buckets.get("config", []) + buckets.get("deployment", []) + buckets.get("ci_cd", []), limit=80),
        "third_party_indicators_list": third_party_indicators_markdown(scan),
        "cfml_detected": yes_no("cfml"),
        "php_detected": yes_no("php"),
        "node_detected": yes_no("node-js"),
        "python_detected": yes_no("python"),
        "mysql_detected": yes_no("mysql"),
        "mssql_detected": yes_no("mssql"),
        "postgresql_detected": yes_no("postgresql"),
        "mongodb_detected": yes_no("mongodb"),
        "redis_detected": yes_no("redis"),
        "oracle_db_detected": yes_no("oracle-db"),
        "db_indicators": db_indicators,
    }


def existing_file_content(rel: str, context: Dict[str, str]) -> str:
    """Content for a generated file, loaded from templates/existing/ (source of truth)."""
    template = load_template("existing", rel)
    if template is None:
        return generic_placeholder(rel)
    return render_template(template, context)

def platform_file_content(platform: str, context: Dict[str, str]) -> str:
    """Content for platforms/<platform>.md, loaded from templates/existing/platforms/."""
    template = load_template("existing", f"platforms/{platform}.md")
    if template is None:
        return f"# {platform} Platform Notes\n\nDetected platform file for `{platform}`. Add confirmed implementation details here.\n"
    return render_template(template, context)


def write_generated_artifact(repo: Path, rel: str, content: str, old_manifest: Dict[str, Any], force: bool, created: List[Path], updated: List[Path], diagnostics: List[Dict[str, Any]]) -> bool:
    path = repo / rel
    owner = (old_manifest.get("managed_artifacts", {}) or {}).get(rel, {})
    expected = owner.get("digest") if isinstance(owner, dict) else None
    if path.exists() and old_manifest and not expected and not force:
        diagnostics.append({"code": "GENERATED_OWNERSHIP_UNKNOWN", "paths": [rel], "message": "Existing generated artifact has no recorded digest.", "suggested_repair": "Review it and rerun with --force to establish ownership."})
        return False
    if path.exists() and expected and content_digest(path.read_bytes()) != expected and not force:
        diagnostics.append({"code": "GENERATED_CONTENT_MODIFIED", "paths": [rel], "message": "Generated content was modified outside Atlas maintenance.", "suggested_repair": "Use --force to accept regeneration or move hand-authored content elsewhere."})
        return False
    existed = path.exists()
    if not existed or path.read_text(encoding="utf-8", errors="ignore") != content:
        atomic_write_text(path, content)
        (updated if existed else created).append(path)
    return True


def update_managed_artifact(repo: Path, rel: str, section_name: str, content: str, old_manifest: Dict[str, Any], force: bool, updated: List[Path], diagnostics: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    path = repo / rel
    existing = path.read_text(encoding="utf-8", errors="ignore")
    owner = (old_manifest.get("managed_artifacts", {}) or {}).get(rel, {})
    expected = owner.get("digest") if isinstance(owner, dict) and owner.get("kind") == "section" else None
    current = managed_section_content(existing, section_name)
    if expected and (current is None or content_digest(current) != expected) and not force:
        diagnostics.append({"code": "GENERATED_CONTENT_MODIFIED", "paths": [rel], "message": "Managed section differs from its recorded digest.", "suggested_repair": "Use --force to regenerate or move hand-authored content outside the managed block."})
        return None
    try:
        new_text, changed = upsert_managed_section(existing, section_name, content)
    except ValueError as exc:
        diagnostics.append({"code": "MANAGED_SENTINEL_INVALID", "paths": [rel], "message": str(exc), "suggested_repair": "Restore exactly one ordered sentinel pair."})
        return None
    if changed:
        atomic_write_text(path, new_text)
        updated.append(path)
    return {"kind": "section", "section": section_name, "digest": content_digest(content.strip())}


# Skill-authored guidance that must reach every repo, including ones bootstrapped by an older
# skill version whose whole-file templates (agent-playbook.md, tasks.md) already exist and are
# otherwise left untouched. Applied as digest-tracked managed sections, same mechanism as
# code-map.md's evidence block: only ever appended if missing or refreshed if unmodified since
# last sync; a hand-edited block blocks further sync until --force.
#
# NOTE: fragment file content is rendered verbatim into the target repo (render_template() only
# does slot substitution, it does not strip comments) — never put skill-maintainer notes inside a
# fragment's own text; put them here instead.
#
# templates/{existing,greenfield}/fragments/agent-playbook-skill-guidance.md are near-identical
# by design, not accidentally duplicated: the site-URL/testing paragraph and the audit_plans.py
# mechanics should stay word-for-word identical between the two. Only these are meant to differ:
# the deployment-status clause ("once something is deployed" — greenfield-only, since existing
# repos are already deployed), the plan/ (singular, greenfield-only) vs plans/ (plural, both)
# disambiguation note, context/ path prefixes (greenfield-only), and the "## Atlas Maintenance"
# table (existing-mode fragment only — greenfield's equivalent table lives directly in its
# whole-file templates/greenfield/agent-playbook.md instead, with context/-prefixed paths, since
# greenfield's table predates this fragment-based sync mechanism).
SKILL_MANAGED_SECTIONS = [
    ("project-atlas/agent-playbook.md", "skill-guidance", "fragments/agent-playbook-skill-guidance.md"),
    ("project-atlas/tasks.md", "plan-link-convention", "fragments/tasks-plan-link-convention.md"),
]


def apply_skill_managed_sections(repo: Path, mode: str, context: Dict[str, str], old_manifest: Dict[str, Any], force: bool, updated: List[Path], diagnostics: List[Dict[str, Any]], managed_artifacts: Dict[str, Any]) -> None:
    for rel, section, fragment in SKILL_MANAGED_SECTIONS:
        template = load_template(mode, fragment)
        if template is None or not (repo / rel).is_file():
            continue
        content = render_template(template, context)
        owner = update_managed_artifact(repo, rel, section, content, old_manifest, force, updated, diagnostics)
        if owner:
            managed_artifacts[rel] = owner


def _create_existing(repo: Path, scan: Dict[str, Any], force: bool = False, backup: bool = False, selected_platforms: Iterable[str] = (), update: bool = False, domains: Iterable[str] = (), cfc_index_threshold: int = 25, site_url: str = "") -> Dict[str, Any]:
    repo_name = Path(scan.get("repo", str(repo))).name
    created: List[Path] = []
    skipped: List[Path] = []
    updated: List[Path] = []
    backed_up: List[Path] = []
    diagnostics: List[Dict[str, Any]] = []
    generated_written: set[str] = set()
    old_manifest_raw, _manifest_error = load_manifest(repo)
    old_manifest = migrate_manifest(old_manifest_raw, repo) if old_manifest_raw else {}
    if update and old_manifest.get("repository_fingerprint") != scan.get("manifest_fingerprint_at_scan"):
        return {
            "status": "failed", "generation_mode": "existing", "lifecycle_state": "stale",
            "created": [], "updated": [], "skipped": [], "backed_up": [],
            "diagnostics": [{"code": "SCAN_STALE_CONCURRENT_UPDATE", "paths": ["project-atlas/atlas.json"], "message": "The Atlas changed after this scan began.", "suggested_repair": "Rescan and retry the update."}],
            "verification": None,
        }

    # ── Directories ──────────────────────────────────────────────────────────
    for d in EXISTING_REQUIRED_DIRS:
        (repo / d).mkdir(parents=True, exist_ok=True)

    # ── Required Atlas files ─────────────────────────────────────────────────
    context = build_context(scan, site_url=resolve_site_url(repo, site_url))
    for rel in EXISTING_REQUIRED_FILES:
        if rel.endswith("atlas.json"):
            continue
        sub = rel.replace("project-atlas/", "")
        write_file(repo / rel, existing_file_content(sub, context), force=force, backup=backup, created=created, skipped=skipped, updated=updated, backed_up=backed_up)
    for rel in ["project-atlas/project-overview.md", "project-atlas/architecture.md"]:
        ensure_contract_marker(repo, rel, updated)

    # ── Single-source CFML inventory ─────────────────────────────────────────
    inventory = scan.get("cfc_inventory", []) or []
    cfc_index_rel = "project-atlas/cfc-index.md"
    if len(inventory) >= cfc_index_threshold:
        if write_generated_artifact(repo, cfc_index_rel, cfc_index_content(scan), old_manifest, force, created, updated, diagnostics):
            generated_written.add(cfc_index_rel)
    elif (repo / cfc_index_rel).exists():
        owner = (old_manifest.get("managed_artifacts", {}) or {}).get(cfc_index_rel, {})
        expected = owner.get("digest") if isinstance(owner, dict) else None
        actual = content_digest((repo / cfc_index_rel).read_bytes())
        if force or (expected and expected == actual):
            (repo / cfc_index_rel).unlink()
            updated.append(repo / cfc_index_rel)
        else:
            diagnostics.append({"code": "GENERATED_CONTENT_MODIFIED", "paths": [cfc_index_rel], "message": "Obsolete generated index has unrecognized edits.", "suggested_repair": "Move hand-authored content, then rerun with --force."})

    # ── Platform files ───────────────────────────────────────────────────────
    required_platforms = set(selected_platforms or []) | set(detect_required_platforms(scan.get("stack", {}) or {}))
    for platform in sorted(required_platforms):
        rel = PLATFORM_FILE_MAP.get(platform)
        if rel:
            if write_generated_artifact(repo, rel, platform_file_content(Path(rel).stem, context), old_manifest, force, created, updated, diagnostics):
                generated_written.add(rel)
    for rel in PLATFORM_FILE_MAP.values():
        if rel in {PLATFORM_FILE_MAP.get(platform) for platform in required_platforms} or not (repo / rel).exists():
            continue
        owner = (old_manifest.get("managed_artifacts", {}) or {}).get(rel, {})
        expected = owner.get("digest") if isinstance(owner, dict) else None
        actual = content_digest((repo / rel).read_bytes())
        if force or (expected and expected == actual):
            (repo / rel).unlink()
            updated.append(repo / rel)
        else:
            diagnostics.append({"code": "GENERATED_CONTENT_MODIFIED", "paths": [rel], "message": "Obsolete platform artifact has unrecognized edits.", "suggested_repair": "Move hand-authored content, then rerun with --force."})

    # ── Evidence-driven specialized documents ───────────────────────────────
    buckets = scan.get("buckets", {}) or {}
    specialized = []
    if buckets.get("auth_candidates") or buckets.get("permission_candidates"):
        specialized.append("auth-and-access.md")
    if buckets.get("database") or buckets.get("migrations") or any((scan.get("stack", {}) or {}).get(k) for k in ["mysql", "mssql", "postgresql", "mongodb", "redis", "oracle-db"]):
        specialized.append("database.md")
        specialized.append("schema.md")
    if buckets.get("deployment") or buckets.get("ci_cd"):
        specialized.append("deployment.md")
    if buckets.get("tests"):
        specialized.append("testing.md")
    if scan.get("third_party_indicators"):
        specialized.append("known-risks.md")
        # launch-checklist.md is a living document (accumulates hand-authored, freeform entries
        # for the life of the project) — never whole-file regenerated once it exists, not even
        # with --force. See write_file_once().
        write_file_once(repo / "project-atlas/launch-checklist.md", existing_file_content("launch-checklist.md", context), created=created, skipped=skipped)
    for sub in sorted(set(specialized)):
        write_file(repo / "project-atlas" / sub, existing_file_content(sub, context), force=force, backup=backup, created=created, skipped=skipped, updated=updated, backed_up=backed_up)

    # ── Root agent instruction files (CLAUDE.md, AGENTS.md) ─────────────────
    for fname in ROOT_GENERATED_FILES:
        write_root_agent_file(repo / fname, repo_name, created=created, updated=updated, skipped=skipped)

    # ── Managed evidence sections preserve all hand-authored prose ───────────
    managed_artifacts = dict(old_manifest.get("managed_artifacts", {}) or {})
    domain_set = set(domains or [])
    if not domain_set or domain_set.intersection({"code", "architecture", "all"}):
        path = repo / "project-atlas/code-map.md"
        existing = path.read_text(encoding="utf-8", errors="ignore")
        inventory_note = "See `cfc-index.md` for the complete generated inventory." if len(inventory) >= cfc_index_threshold else cfc_inventory_markdown(scan)
        content = generated_code_map(scan, external_cfc_index=len(inventory) >= cfc_index_threshold) + "\n\n### CFML inventory\n\n" + inventory_note.rstrip()
        owner = update_managed_artifact(repo, "project-atlas/code-map.md", "evidence", content, old_manifest, force, updated, diagnostics)
        if owner:
            managed_artifacts["project-atlas/code-map.md"] = owner
    if not domain_set or domain_set.intersection({"operations", "database", "auth", "deployment", "all"}):
        path = repo / "project-atlas/operations.md"
        existing = path.read_text(encoding="utf-8", errors="ignore")
        operations_evidence = "\n".join([
            "## Generated operations evidence",
            "### Configuration and deployment candidates",
            context["deployment_candidates_list"].rstrip(),
            "### External and environment-sensitive integrations",
            context["third_party_indicators_list"].rstrip(),
        ])
        owner = update_managed_artifact(repo, "project-atlas/operations.md", "evidence", operations_evidence, old_manifest, force, updated, diagnostics)
        if owner:
            managed_artifacts["project-atlas/operations.md"] = owner
    domain_evidence = {
        "auth": ("auth-and-access.md", "## Generated authentication evidence\n" + context["auth_candidates_list"].rstrip()),
        "database": ("database.md", "## Generated database evidence\n" + context["database_candidates_list"].rstrip()),
        "deployment": ("deployment.md", "## Generated deployment evidence\n" + context["deployment_candidates_list"].rstrip()),
    }
    for domain, (sub, content) in domain_evidence.items():
        path = repo / "project-atlas" / sub
        if path.is_file() and (not domain_set or domain in domain_set or "all" in domain_set):
            rel = f"project-atlas/{sub}"
            owner = update_managed_artifact(repo, rel, "evidence", content, old_manifest, force, updated, diagnostics)
            if owner:
                managed_artifacts[rel] = owner

    # ── Skill-authored guidance, kept current even on repos bootstrapped earlier ────────────
    apply_skill_managed_sections(repo, "existing", context, old_manifest, force, updated, diagnostics, managed_artifacts)

    if cfc_index_rel in generated_written and (repo / cfc_index_rel).exists():
        managed_artifacts[cfc_index_rel] = {"kind": "file", "digest": content_digest((repo / cfc_index_rel).read_bytes())}
    else:
        managed_artifacts.pop(cfc_index_rel, None)
    for platform in sorted(required_platforms):
        rel = PLATFORM_FILE_MAP.get(platform)
        if rel and rel in generated_written and (repo / rel).exists():
            managed_artifacts[rel] = {"kind": "file", "digest": content_digest((repo / rel).read_bytes())}
    for rel in PLATFORM_FILE_MAP.values():
        if not (repo / rel).exists():
            managed_artifacts.pop(rel, None)

    lifecycle = "enrichment-required"
    manifest_path = repo / "project-atlas/atlas.json"
    manifest_text = manifest_content(repo, scan, lifecycle, required_platforms, managed_artifacts, last_verified_state=old_manifest.get("last_verified_state"))
    atomic_write_text(manifest_path, manifest_text)
    updated.append(manifest_path)

    semantic_verification = verify_existing_atlas(repo, stack=scan.get("stack", {}), scan=scan, selected_platforms=required_platforms, level="semantic", generation_mode="existing")
    lifecycle = semantic_verification["lifecycle_state"]
    manifest_text = manifest_content(repo, scan, lifecycle, required_platforms, managed_artifacts, last_verified_state=lifecycle)
    atomic_write_text(manifest_path, manifest_text)

    # ── Verification + repair loop (up to 3 passes) ──────────────────────────
    # Each pass forces-writes anything still missing. After 3 passes any
    # remaining gaps are a hard failure that the caller must report clearly.
    verification = verify_existing_atlas(repo, stack=scan.get("stack", {}), scan=scan, selected_platforms=required_platforms, level="structure", generation_mode="existing")
    for _repair_pass in range(3):
        if verification["status"] == "passed":
            break
        for d in verification.get("missing_required_directories", []):
            (repo / d).mkdir(parents=True, exist_ok=True)
        for f in verification.get("missing_required_files", []):
            sub = f.replace("project-atlas/", "")
            write_file(repo / f, existing_file_content(sub, context), force=True, backup=backup, created=created, skipped=skipped, updated=updated, backed_up=backed_up)
        for f in verification.get("missing_platform_files", []):
            platform = Path(f).stem
            write_file(repo / f, platform_file_content(platform, context), force=True, backup=backup, created=created, skipped=skipped, updated=updated, backed_up=backed_up)
        for fname in verification.get("missing_root_files", []):
            write_root_agent_file(repo / fname, repo_name, created=created, updated=updated, skipped=skipped)
        verification = verify_existing_atlas(repo, stack=scan.get("stack", {}), scan=scan, selected_platforms=required_platforms, level="structure", generation_mode="existing")

    if diagnostics:
        verification["diagnostics"].extend(diagnostics)
        verification["status"] = "failed"

    # ── Detailed log entry ───────────────────────────────────────────────────
    v = verification
    missing_summary = ""
    all_missing = (
        v.get("missing_required_files", []) +
        v.get("missing_required_directories", []) +
        v.get("missing_platform_files", []) +
        v.get("missing_root_files", [])
    )
    if all_missing:
        missing_summary = "\n- MISSING: " + ", ".join(all_missing)

    log_text = f"""
## {now_iso()} - Atlas generation

- Created: {len(created)}
- Updated: {len(updated)}
- Skipped existing: {len(skipped)}
- Backed up: {len(backed_up)}
- Verification status: {v['status']}{missing_summary}
"""
    append_log(repo / "project-atlas/maintenance-log.md", log_text)

    return {
        "status": v["status"],
        "created": [str(p.relative_to(repo)) for p in created if p.exists()],
        "updated": [str(p.relative_to(repo)) for p in updated if p.exists()],
        "skipped": [str(p.relative_to(repo)) for p in skipped if p.exists()],
        "backed_up": [str(p.relative_to(repo)) for p in backed_up if p.exists()],
        "verification": v,
        "lifecycle_state": lifecycle,
        "generation_mode": "existing",
        "diagnostics": v.get("diagnostics", []),
    }


def create_existing(repo: Path, scan: Dict[str, Any], force: bool = False, backup: bool = False, selected_platforms: Iterable[str] = (), update: bool = False, domains: Iterable[str] = (), cfc_index_threshold: int = 25, site_url: str = "") -> Dict[str, Any]:
    with atlas_lock(repo):
        return _create_existing(repo, scan, force, backup, selected_platforms, update, domains, cfc_index_threshold, site_url)

GREENFIELD_FILES = [
    "project-atlas/README.md", "project-atlas/agent-playbook.md", "project-atlas/.project-atlasignore",
    "project-atlas/plan/README.md", "project-atlas/plan/product-brief.md", "project-atlas/plan/stack-proposal.md", "project-atlas/plan/architecture-plan.md", "project-atlas/plan/data-model-plan.md", "project-atlas/plan/auth-plan.md", "project-atlas/plan/feature-plan.md", "project-atlas/plan/implementation-roadmap.md", "project-atlas/plan/open-questions.md",
    "project-atlas/context/project-overview.md", "project-atlas/context/stack.md", "project-atlas/context/architecture.md", "project-atlas/context/code-map.md", "project-atlas/context/feature-index.md", "project-atlas/context/database.md", "project-atlas/context/schema.md", "project-atlas/context/auth-and-access.md", "project-atlas/context/conventions.md", "project-atlas/context/dependency-map.md", "project-atlas/context/testing.md", "project-atlas/context/deployment.md", "project-atlas/context/known-risks.md", "project-atlas/context/glossary.md", "project-atlas/context/open-questions.md", "project-atlas/context/maintenance-log.md",
    "project-atlas/decisions/README.md", "project-atlas/handoffs/README.md", "project-atlas/snapshots/README.md",
    "project-atlas/plans/in-flight/README.md", "project-atlas/plans/completed/README.md",
]

# Living documents: accumulate arbitrary hand-authored prose for the life of the project and must
# never be whole-file regenerated once they exist, not even with --force. See write_file_once().
GREENFIELD_LIVING_DOCUMENT_FILES = ["project-atlas/tasks.md", "project-atlas/launch-checklist.md"]


def _create_greenfield(repo: Path, force: bool = False, backup: bool = False, site_url: str = "") -> Dict[str, Any]:
    created: List[Path] = []
    skipped: List[Path] = []
    updated: List[Path] = []
    backed_up: List[Path] = []
    diagnostics: List[Dict[str, Any]] = []
    old_manifest_raw, _manifest_error = load_manifest(repo)
    old_manifest = migrate_manifest(old_manifest_raw, repo) if old_manifest_raw else {}
    managed_artifacts = dict(old_manifest.get("managed_artifacts", {}) or {})
    for d in ["project-atlas/platforms", "project-atlas/decisions", "project-atlas/handoffs", "project-atlas/snapshots", "project-atlas/plans/in-flight", "project-atlas/plans/completed"]:
        (repo / d).mkdir(parents=True, exist_ok=True)
    context = {
        "generated": now_iso(), "repo_name": repo.name, "repo_path": str(repo),
        "site_url": resolve_site_url(repo, site_url) or "_Not yet provided — ask the user and record it here._",
    }
    for rel in GREENFIELD_FILES:
        sub = rel.replace("project-atlas/", "")
        template = load_template("greenfield", sub)
        if template is not None:
            content = render_template(template, context)
        elif rel.endswith(".project-atlasignore"):
            content = ".git/\nnode_modules/\nvendor/\n.env\n.env.*\n*.pem\n*.key\n"
        else:
            title = Path(rel).stem.replace("-", " ").title()
            content = f"# {title}\n\nGreenfield Project Atlas placeholder. Replace with confirmed project details. Do not invent implementation facts.\n"
        write_file(repo / rel, content, force=force, backup=backup, created=created, skipped=skipped, updated=updated, backed_up=backed_up)
    for rel in GREENFIELD_LIVING_DOCUMENT_FILES:
        sub = rel.replace("project-atlas/", "")
        template = load_template("greenfield", sub)
        content = render_template(template, context) if template is not None else generic_placeholder(sub)
        write_file_once(repo / rel, content, created=created, skipped=skipped)
    for rel in ["project-atlas/plan/product-brief.md", "project-atlas/plan/architecture-plan.md"]:
        ensure_contract_marker(repo, rel, updated)
    # Root agent instruction files
    repo_name = repo.name
    root_created: List[Path] = []
    root_updated: List[Path] = []
    root_skipped: List[Path] = []
    for fname in ROOT_GENERATED_FILES:
        write_root_agent_file(repo / fname, repo_name, created=root_created, updated=root_updated, skipped=root_skipped, generation_mode="greenfield")

    # ── Skill-authored guidance, kept current even on repos bootstrapped earlier ────────────
    apply_skill_managed_sections(repo, "greenfield", context, old_manifest, force, updated, diagnostics, managed_artifacts)

    manifest_path = repo / "project-atlas/atlas.json"
    scan = {"repo": str(repo), "files": [], "file_fingerprints": {}, "buckets": {}, "stack": {}, "cfc_inventory": [], "file_count": 0, "truncated": False, "truncated_at": None}
    manifest = manifest_content(repo, scan, "enrichment-required", [], managed_artifacts, generation_mode="greenfield", last_verified_state="enrichment-required")
    atomic_write_text(manifest_path, manifest)
    if manifest_path not in created:
        created.append(manifest_path)
    semantic = verify_existing_atlas(repo, scan=scan, level="semantic", generation_mode="greenfield")
    lifecycle = semantic["lifecycle_state"]
    manifest = manifest_content(repo, scan, lifecycle, [], managed_artifacts, generation_mode="greenfield", last_verified_state=lifecycle)
    atomic_write_text(manifest_path, manifest)
    verification = verify_existing_atlas(repo, scan=scan, level="structure", generation_mode="greenfield")
    if diagnostics:
        verification["diagnostics"].extend(diagnostics)
        verification["status"] = "failed"

    return {
        "status": verification["status"],
        "lifecycle_state": lifecycle,
        "generation_mode": "greenfield",
        "diagnostics": verification["diagnostics"],
        "verification": verification,
        "created": [str(p.relative_to(repo)) for p in created + root_created],
        "updated": [str(p.relative_to(repo)) for p in updated + root_updated],
        "skipped": [str(p.relative_to(repo)) for p in skipped + root_skipped],
    }


def create_greenfield(repo: Path, force: bool = False, backup: bool = False, site_url: str = "") -> Dict[str, Any]:
    with atlas_lock(repo):
        return _create_greenfield(repo, force, backup, site_url)


def convert_greenfield(repo: Path, scan: Dict[str, Any], force: bool = False, backup: bool = False, selected_platforms: Iterable[str] = (), site_url: str = "") -> Dict[str, Any]:
    with atlas_lock(repo):
        context = build_context(scan, site_url=resolve_site_url(repo, site_url))
        for rel in ["README.md", "agent-playbook.md"]:
            atomic_write_text(repo / "project-atlas" / rel, existing_file_content(rel, context))
        result = _create_existing(repo, scan, force=force, backup=backup, selected_platforms=selected_platforms, update=True, site_url=site_url)
        result["converted_from"] = "greenfield"
        result["generation_mode"] = "existing"
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Project Atlas template files.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--template-mode", choices=["existing", "greenfield"], default="existing")
    parser.add_argument("--scan-json")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--platform", action="append", default=[])
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if args.template_mode == "greenfield":
        result = create_greenfield(repo, force=args.force, backup=args.backup)
    else:
        if args.scan_json:
            scan = json.loads(Path(args.scan_json).read_text(encoding="utf-8"))
        else:
            scan = scan_repository(repo)
        result = create_existing(repo, scan, force=args.force, backup=args.backup, selected_platforms=args.platform)

    print(dump_json(result))
    return 0 if result.get("status") == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
