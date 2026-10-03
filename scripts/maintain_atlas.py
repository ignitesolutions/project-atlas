#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import argparse
import json
import re
import subprocess
from pathlib import Path

try:
    from scan_repo import scan_repository, discover_repository_files
    from write_templates import create_existing, create_greenfield, convert_greenfield
    from audit_plans import audit as audit_plans
    from utils import append_log, dump_json, now_iso, verify_existing_atlas, load_manifest, migrate_manifest, atomic_write_text, repository_fingerprint, atlas_lock, SKILL_VERSION, atlas_warnings, content_digest, git_commit, ROOT_GENERATED_FILES, STATUS_UNFILLED_MARKER
except ImportError:
    from .scan_repo import scan_repository, discover_repository_files
    from .write_templates import create_existing, create_greenfield, convert_greenfield
    from .audit_plans import audit as audit_plans
    from .utils import append_log, dump_json, now_iso, verify_existing_atlas, load_manifest, migrate_manifest, atomic_write_text, repository_fingerprint, atlas_lock, SKILL_VERSION, atlas_warnings, content_digest, git_commit, ROOT_GENERATED_FILES, STATUS_UNFILLED_MARKER

LOG_KEEP_LINES = 100
AUTO_CHANGED_LIMIT = 300


def _git_lines(repo: Path, *args: str) -> list[str] | None:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    return [line for line in result.stdout.splitlines() if line] if result.returncode == 0 else None


def _is_app_file(rel: str) -> bool:
    return not rel.startswith("project-atlas/") and rel not in ROOT_GENERATED_FILES


def atlas_status(repo: Path, max_files: int, sample: int = 15) -> dict:
    """Session-start snapshot: how far the Atlas has drifted from the code, without a full rescan.
    Lists files (no hashing), then hashes only the files Git or mtimes say may have changed."""
    manifest, error = load_manifest(repo)
    if error:
        return {"status": "failed", "mode": "status", "diagnostics": [{"code": "MANIFEST_INVALID_JSON" if error != "missing" else "STRUCTURE_MISSING", "paths": ["project-atlas/atlas.json"], "message": error, "suggested_repair": "Bootstrap the Atlas, or repair atlas.json."}]}
    generation_mode = manifest.get("generation_mode", "existing")
    recorded = manifest.get("file_fingerprints", {}) or {}
    files, _dirs, _ignored, truncated, _at, discovery = discover_repository_files(repo, max_files)
    current = {rel for rel in files if _is_app_file(rel)}
    added = sorted(current - set(recorded))
    deleted = sorted(set(recorded) - current)

    atlas_commit = manifest.get("git_commit")
    head = git_commit(repo)
    candidates: set[str] | None = None
    commits_since = None
    if discovery == "git" and atlas_commit:
        since_commit = _git_lines(repo, "diff", "--name-only", atlas_commit, "--")
        if since_commit is not None:
            candidates = set(since_commit)
            count = _git_lines(repo, "rev-list", "--count", f"{atlas_commit}..HEAD")
            commits_since = int(count[0]) if count else 0
    if candidates is None:
        manifest_path = repo / "project-atlas/atlas.json"
        cutoff = manifest_path.stat().st_mtime
        candidates = {rel for rel in current if (repo / rel).stat().st_mtime > cutoff}
    modified = []
    for rel in sorted(candidates & current & set(recorded)):
        try:
            if content_digest((repo / rel).read_bytes()) != recorded[rel]:
                modified.append(rel)
        except OSError:
            pass
    changed = sorted(set(added) | set(deleted) | set(modified))

    tasks = {"open": 0, "blocked": 0, "done": 0}
    tasks_path = repo / "project-atlas/tasks.md"
    if tasks_path.is_file():
        for line in tasks_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if stripped.startswith(("- [x]", "- [X]")):
                tasks["done"] += 1
            elif stripped.startswith("- [ ]"):
                tasks["blocked" if "BLOCKED" in stripped else "open"] += 1
    in_flight = repo / "project-atlas/plans/in-flight"
    plans_in_flight = len([p for p in in_flight.glob("*.md") if p.name.lower() != "readme.md"]) if in_flight.is_dir() else 0
    status_path = repo / "project-atlas/status.md"
    last_updated = None
    if status_path.is_file():
        match = re.search(r"^Last updated:\s*(.+)$", status_path.read_text(encoding="utf-8", errors="ignore"), re.M)
        last_updated = match.group(1).strip() if match else None

    warnings = atlas_warnings(repo, generation_mode) + audit_plans(repo, "check")["diagnostics"]
    lifecycle = manifest.get("lifecycle_state")
    short = (atlas_commit or "")[:7]
    next_actions = []
    if generation_mode == "greenfield" and current and not recorded:
        next_actions.append("Implementation files exist but the Atlas is still greenfield: run `maintain_atlas.py --repo . --mode convert`.")
    elif changed:
        since = f" --changed-since {short}" if short and discovery == "git" else ""
        next_actions.append(f"Run `maintain_atlas.py --repo . --mode update{since}`, then update the Atlas files the playbook maps those changes to.")
    if manifest.get("skill_version") != SKILL_VERSION:
        next_actions.append("Run `maintain_atlas.py --repo . --mode reconcile` to bring the Atlas to the installed skill version.")
    next_actions.extend(item["suggested_repair"] for item in warnings)
    return {
        "status": "attention" if changed or warnings or manifest.get("skill_version") != SKILL_VERSION or truncated else "passed",
        "mode": "status",
        "generation_mode": generation_mode,
        "lifecycle_state": f"{lifecycle} @ {short}" if short else lifecycle,
        "atlas_commit": atlas_commit,
        "head_commit": head,
        "commits_since_atlas": commits_since,
        "changed_app_files": len(changed),
        "changed_app_files_sample": changed[:sample],
        "skill_version": {"atlas": manifest.get("skill_version"), "installed": SKILL_VERSION},
        "status_md_last_updated": last_updated,
        "tasks": tasks,
        "plans_in_flight": plans_in_flight,
        "warnings": warnings,
        "next_actions": next_actions,
        "diagnostics": [],
    }


def compact_log(repo: Path) -> dict:
    """Move the oldest maintenance-log entries verbatim to an archive file, keeping the newest
    entries (about LOG_KEEP_LINES lines) plus an Earlier history entry pointing at the archive."""
    manifest, _error = load_manifest(repo)
    log_rel = "project-atlas/context/maintenance-log.md" if manifest.get("generation_mode") == "greenfield" else "project-atlas/maintenance-log.md"
    archive_rel = log_rel.replace("maintenance-log.md", "maintenance-log-archive.md")
    log_path, archive_path = repo / log_rel, repo / archive_rel
    if not log_path.is_file():
        return {"status": "failed", "mode": "compact-log", "updated": [], "diagnostics": [{"code": "STRUCTURE_MISSING", "paths": [log_rel], "message": "Maintenance log not found.", "suggested_repair": "Run an Atlas update."}]}
    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("## ")]
    header = lines[:starts[0]] if starts else lines
    entries = [lines[s:(starts[n + 1] if n + 1 < len(starts) else len(lines))] for n, s in enumerate(starts)]
    earlier = [e for e in entries if e[0].strip().lower() == "## earlier history"]
    # Agents have historically both prepended and appended entries, so order by the heading's date
    # (file position breaks ties and orders undated entries) and write everything back oldest-first.
    def entry_key(item):
        position, entry = item
        match = re.match(r"##\s+(\d{4}-\d{2}-\d{2})", entry[0])
        return (match.group(1) if match else "", position)
    dated = [entry for _key, entry in sorted(((entry_key(item), item[1]) for item in enumerate(e for e in entries if e[0].strip().lower() != "## earlier history")), key=lambda pair: pair[0])]
    keep: list = []
    for entry in reversed(dated):
        if keep and sum(len(e) for e in keep) + len(entry) > LOG_KEEP_LINES:
            break
        keep.insert(0, entry)
    archived = dated[:len(dated) - len(keep)]
    if not archived:
        return {"status": "passed", "mode": "compact-log", "updated": [], "archived_entries": 0, "diagnostics": []}
    archive_name = Path(archive_rel).name
    pointer = f"Older entries are archived verbatim in `{archive_name}`. Summarize them here in one paragraph."
    earlier_block = earlier[0] if earlier else ["## Earlier history", ""]
    if archive_name not in "\n".join(earlier_block):
        earlier_block = [*earlier_block, pointer, ""]
    existing_archive = archive_path.read_text(encoding="utf-8", errors="ignore").rstrip() if archive_path.is_file() else "# Maintenance Log Archive\n\nEntries moved verbatim from the maintenance log, oldest first."
    archive_body = "\n\n".join("\n".join(entry).rstrip() for entry in archived)
    new_log = "\n".join(header).rstrip() + "\n\n" + "\n".join(earlier_block).rstrip() + "\n\n" + "\n".join("\n".join(entry).rstrip() + "\n" for entry in keep)
    with atlas_lock(repo):
        atomic_write_text(archive_path, existing_archive + "\n\n" + archive_body + "\n")
        atomic_write_text(log_path, new_log.rstrip() + "\n")
    return {"status": "passed", "mode": "compact-log", "updated": [log_rel, archive_rel], "archived_entries": len(archived), "kept_entries": len(keep), "diagnostics": []}


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain or verify Project Atlas.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--mode", choices=["check", "status", "auto", "update", "reconcile", "convert", "migrate", "compact-log"], default="check")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--platform", action="append", default=[])
    parser.add_argument("--level", choices=["structure", "evidence", "semantic"], default="semantic")
    parser.add_argument("--changed-since", help="Limit update domains to paths changed since this Git ref")
    parser.add_argument("--paths", action="append", default=[], help="Changed path to classify; repeat as needed")
    parser.add_argument("--domain", action="append", choices=["all", "code", "architecture", "database", "auth", "deployment", "operations"], default=[])
    parser.add_argument("--max-files", type=int, default=20000)
    parser.add_argument("--allow-partial-scan", action="store_true")
    parser.add_argument("--generation-mode", choices=["auto", "existing", "greenfield"], default="auto")
    parser.add_argument("--log", action="store_true", help="In check mode, also append the result to maintenance-log.md")
    parser.add_argument("--site-url", default="", help="Public-facing site URL to record in agent-playbook.md (update/reconcile/convert modes). If omitted, whatever is already recorded is preserved.")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if args.mode in ("status", "compact-log"):
        result = atlas_status(repo, args.max_files) if args.mode == "status" else compact_log(repo)
        print(dump_json(result))
        return 1 if result.get("status") == "failed" else 0

    # Auto mode is what a bare skill invocation runs: record what changed since the last Atlas
    # update (the agent needs that list to update hand-authored documents), run a normal update
    # (which also reconciles skill version and plans), then report the post-update status.
    auto_before = None
    if args.mode == "auto":
        auto_before = atlas_status(repo, args.max_files, sample=AUTO_CHANGED_LIMIT)
        if auto_before["status"] == "failed":
            auto_before["mode"] = "auto"
            auto_before["next_actions"] = ["No usable Atlas here: run the bootstrap interview (references/bootstrap-interview.md), then bootstrap_atlas.py."]
            print(dump_json(auto_before))
            return 1
        args.mode = "update"

    changed_paths = list(args.paths)
    if args.changed_since:
        result = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", args.changed_since, "--"], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(json.dumps({"status": "failed", "diagnostics": [{"code": "INVALID_GIT_REF", "paths": [args.changed_since], "message": result.stderr.strip(), "suggested_repair": "Use a valid Git revision."}]}, indent=2))
            return 1
        changed_paths.extend(p for p in result.stdout.splitlines() if p)

    scan = scan_repository(repo, max_files=args.max_files, write_cache=args.mode in {"update", "convert"}, restrict_paths=changed_paths)
    if scan.get("truncated") and not args.allow_partial_scan:
        result = {"status": "failed", "mode": args.mode, "generation_mode": args.generation_mode, "lifecycle_state": "stale", "created": [], "updated": [], "diagnostics": [{"code": "PARTIAL_SCAN", "paths": [scan.get("truncated_at")], "message": "Repository scan was truncated.", "suggested_repair": "Increase --max-files or pass --allow-partial-scan."}], "verification": None}
        print(dump_json(result))
        return 1

    domains = set(args.domain)
    for path in changed_paths:
        low = path.lower()
        for domain, tokens in [
            ("auth", ["auth", "login", "session", "permission", "role"]),
            ("database", ["sql", "schema", "migration", "database", "repository", "dao"]),
            ("deployment", ["deploy", "docker", "workflow", "jenkins", "config"]),
        ]:
            if any(token in low for token in tokens):
                domains.add(domain)
        # Every changed path can move the code map, even when it also belongs to a narrower domain.
        domains.add("code")

    if args.mode == "migrate":
        raw, error = load_manifest(repo)
        if error:
            result = {"status": "failed", "mode": "migrate", "generation_mode": args.generation_mode, "lifecycle_state": "stale", "created": [], "updated": [], "diagnostics": [{"code": "MANIFEST_INVALID_JSON", "paths": ["project-atlas/atlas.json"], "message": error, "suggested_repair": "Repair the manifest before migration."}], "verification": None}
        else:
            migrated = migrate_manifest(raw, repo)
            current_fingerprints = {p: v for p, v in (scan.get("file_fingerprints", {}) or {}).items() if not p.startswith("project-atlas/") and p not in {"AGENTS.md", "CLAUDE.md"}}
            migrated["file_fingerprints"] = current_fingerprints
            migrated["repository_fingerprint"] = repository_fingerprint(f"{p}:{value}" for p, value in current_fingerprints.items())
            atomic_write_text(repo / "project-atlas/atlas.json", json.dumps(migrated, indent=2, sort_keys=True) + "\n")
            verification = verify_existing_atlas(repo, stack=scan.get("stack", {}), scan=scan, selected_platforms=args.platform, level="structure", generation_mode=args.generation_mode)
            result = {"status": verification["status"], "mode": "migrate", "generation_mode": verification["generation_mode"], "lifecycle_state": verification["lifecycle_state"], "created": [], "updated": ["project-atlas/atlas.json"], "diagnostics": verification["diagnostics"], "verification": verification}
    elif args.mode == "convert":
        result = convert_greenfield(repo, scan, force=args.force, backup=args.backup, selected_platforms=args.platform, site_url=args.site_url)
        result["mode"] = "convert"
    elif args.mode in ("update", "reconcile"):
        manifest_path = repo / "project-atlas/atlas.json"
        old_manifest = {}
        try:
            old_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        except json.JSONDecodeError:
            pass
        current_fingerprints = {p: v for p, v in (scan.get("file_fingerprints", {}) or {}).items() if not p.startswith("project-atlas/") and p not in {"AGENTS.md", "CLAUDE.md"}}
        effective_mode = args.generation_mode if args.generation_mode != "auto" else old_manifest.get("generation_mode", "existing")
        skill_version_matches = old_manifest.get("skill_version") == SKILL_VERSION
        # `--mode reconcile` always takes the full regeneration path below, even when nothing in
        # the repo's source changed, since a skill upgrade doesn't touch repo fingerprints. It
        # never passes force=True on its own, so digest-tracked managed sections still refuse to
        # clobber hand-edited content — reconciliation only ever backfills what's missing or
        # unmodified since it last generated it.
        take_fast_path = (
            args.mode == "update" and skill_version_matches
            and old_manifest.get("file_fingerprints") == current_fingerprints
            and not changed_paths and not domains and not args.force and effective_mode == "existing"
        )
        if take_fast_path:
            live = verify_existing_atlas(repo, stack=scan.get("stack", {}), scan=scan, selected_platforms=args.platform, level="semantic", generation_mode="existing")
            structure_incomplete = any(item["code"] == "STRUCTURE_MISSING" for item in live["diagnostics"])
            if structure_incomplete:
                # Source files are unchanged, but required Atlas structure is missing (e.g. the
                # installed skill version added new required files since this repo was bootstrapped).
                # Repair through the normal write path: it only ever fills in missing files/dirs and
                # never overwrites hand-authored content.
                result = create_existing(repo, scan, force=args.force, backup=args.backup, selected_platforms=args.platform, update=True, domains=domains, site_url=args.site_url)
            else:
                structural_codes = {"MANIFEST_INVALID_JSON", "MANIFEST_SCHEMA_UNSUPPORTED", "MANIFEST_FIELD_MISSING", "MANIFEST_FIELD_INVALID", "GENERATED_CONTENT_MODIFIED", "MANAGED_SENTINEL_INVALID"}
                hard_diagnostics = [item for item in live["diagnostics"] if item["code"] in structural_codes]
                updated_files = []
                head = git_commit(repo)
                # Source is unchanged, so the Atlas is current as of HEAD: record that, so `--mode
                # status` measures drift from here rather than from the last content change.
                if not hard_diagnostics and (old_manifest.get("lifecycle_state") != live["lifecycle_state"] or old_manifest.get("git_commit") != head):
                    old_manifest["lifecycle_state"] = live["lifecycle_state"]
                    old_manifest["last_verified_state"] = live["lifecycle_state"]
                    old_manifest["git_commit"] = head
                    old_manifest["generated_at"] = now_iso()
                    atomic_write_text(manifest_path, json.dumps(old_manifest, indent=2, sort_keys=True) + "\n")
                    updated_files.append("project-atlas/atlas.json")
                result = {"status": "failed" if hard_diagnostics else "passed", "mode": args.mode, "generation_mode": "existing", "lifecycle_state": live["lifecycle_state"], "created": [], "updated": updated_files, "skipped": [], "diagnostics": hard_diagnostics, "verification": live, "no_changes": not updated_files}
        elif effective_mode == "greenfield":
            result = create_greenfield(repo, force=args.force, backup=args.backup, site_url=args.site_url)
        else:
            result = create_existing(repo, scan, force=args.force, backup=args.backup, selected_platforms=args.platform, update=True, domains=domains, site_url=args.site_url)
        result["mode"] = args.mode
        # Plan files follow tasks.md checkbox state on every update; ambiguous findings are reported
        # as warnings rather than failing the update.
        with atlas_lock(repo):
            plan_audit = audit_plans(repo, "apply", reopen=False)
        result["plans_moved"] = plan_audit["moved"]
        result["plans_relinked"] = plan_audit["relinked"]
        if plan_audit["moved"] or plan_audit["relinked"]:
            result["no_changes"] = False
        result["warnings"] = ((result.get("verification") or {}).get("warnings") or []) + plan_audit["diagnostics"]
    else:
        # Check mode is read-only: it must not touch the repository, so it can run
        # in CI or pre-commit without dirtying the tree. Pass --log to also record
        # the result in maintenance-log.md.
        verification = verify_existing_atlas(repo, stack=scan.get("stack", {}), scan=scan, selected_platforms=args.platform, level=args.level, generation_mode=args.generation_mode)
        v = verification
        if args.log:
            all_missing = (
                v.get("missing_required_files", []) +
                v.get("missing_required_directories", []) +
                v.get("missing_platform_files", []) +
                v.get("missing_root_files", [])
            )
            missing_line = ("\n- MISSING: " + ", ".join(all_missing)) if all_missing else ""
            with atlas_lock(repo):
                append_log(
                    repo / "project-atlas/maintenance-log.md",
                    f"\n## {now_iso()} - Atlas check\n\n- Verification status: {v['status']}{missing_line}\n"
                )
        result = {"status": v["status"], "mode": "check", "generation_mode": v["generation_mode"], "lifecycle_state": v["lifecycle_state"], "created": [], "updated": [], "diagnostics": v["diagnostics"], "warnings": v.get("warnings", []) + audit_plans(repo, "check")["diagnostics"], "verification": v}

    if auto_before is not None:
        after = atlas_status(repo, args.max_files)
        # The no-change fast path reports only structural failures in `diagnostics`; the full
        # verification still names alias, scaffold, and enrichment gaps the agent must act on.
        findings, seen = [], set()
        for item in (result.get("diagnostics") or []) + ((result.get("verification") or {}).get("diagnostics") or []):
            key = (item["code"], tuple(item["paths"]))
            if key not in seen:
                seen.add(key)
                findings.append(item)
        next_actions = [f"{item['code']} ({', '.join(item['paths'])}): {item['suggested_repair']}" for item in findings] + after.get("next_actions", [])
        result = {
            "status": "failed" if result.get("status") != "passed" else ("attention" if next_actions or after["status"] != "passed" else "passed"),
            "mode": "auto",
            "generation_mode": after.get("generation_mode"),
            "lifecycle_state": after.get("lifecycle_state"),
            "previous_atlas_commit": auto_before.get("atlas_commit"),
            "changed_since_last_update": auto_before["changed_app_files_sample"],
            "changed_count": auto_before["changed_app_files"],
            "created": result.get("created", []),
            "updated": result.get("updated", []),
            "plans_moved": result.get("plans_moved", []),
            "tasks": after.get("tasks"),
            "plans_in_flight": after.get("plans_in_flight"),
            "status_md_last_updated": after.get("status_md_last_updated"),
            "skill_version": after.get("skill_version"),
            "warnings": after.get("warnings", []),
            "next_actions": next_actions,
            "diagnostics": findings,
        }
        print(dump_json(result))
        return 1 if result["status"] == "failed" else 0

    print(dump_json(result))
    if result.get("status") != "passed":
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
