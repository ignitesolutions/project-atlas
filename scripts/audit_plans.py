#!/usr/bin/env python3
"""Reconcile project-atlas/plans/{in-flight,completed} with tasks.md checkbox state.

Convention (documented in agent-playbook.md, "Plan Tracking Protocol"): a task line that tracks a
saved implementation plan links to it as `(plan: [<slug>](plans/in-flight/<file>.md))` (or
`plans/completed/...` once done). Any task line with exactly one Markdown link into plans/ is
tracked, wherever the link sits in the line; any mention of a plan filename in tasks.md or
tasks-archive.md counts as a reference for orphan detection. This script keeps plan file location, and the link text that
points at it, consistent with the task's checkbox state.

With --archive-completed (apply mode only), `## ` phases of tasks.md whose task boxes are all
checked move verbatim to tasks-archive.md, keeping tasks.md short for every session that reads it.

It never invents task descriptions or deletes files — findings it cannot resolve deterministically
(orphaned plans, broken links, duplicate filenames in both folders) are always reported, never
guessed.
"""
from __future__ import annotations

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import argparse
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List

try:
    from utils import atlas_lock, atomic_write_text, dump_json, _completed_task_phases
except ImportError:
    from .utils import atlas_lock, atomic_write_text, dump_json, _completed_task_phases

TASK_BOX_RE = re.compile(r"^\s*-\s*\[([ xX])\]")
PLAN_LINK_RE = re.compile(r"\[[^\]]*\]\((plans/(?:in-flight|completed)/[^)\s]+)\)")
PLAN_MENTION_RE = re.compile(r"plans/(?:in-flight|completed)/([^)\s`'\"]+\.md)")
ARCHIVE_HEADER = "# Tasks Archive\n\nCompleted phases moved verbatim from `tasks.md`. Read only when history is needed.\n"


def _diagnostic(code: str, paths: List[str], message: str, repair: str) -> Dict[str, Any]:
    return {"code": code, "paths": sorted(set(paths)), "message": message, "suggested_repair": repair}


def _list_plan_filenames(dir_path: Path) -> set[str]:
    if not dir_path.is_dir():
        return set()
    return {p.name for p in dir_path.glob("*.md") if p.name.lower() != "readme.md"}


def _parse_task_entries(lines: List[str]) -> List[Dict[str, Any]]:
    entries = []
    for i, line in enumerate(lines):
        box = TASK_BOX_RE.match(line)
        links = PLAN_LINK_RE.findall(line) if box else []
        if len(set(links)) != 1:
            continue
        entries.append({"line_index": i, "checked": box.group(1) in "xX", "path": links[0]})
    return entries


def _archive_completed_phases(tasks_path: Path, archive_path: Path) -> List[str]:
    lines = tasks_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    phases = _completed_task_phases(lines)
    if not phases:
        return []
    moved_blocks = ["\n".join(lines[start:end]).rstrip() for start, end in phases]
    drop = {i for start, end in phases for i in range(start, end)}
    kept = [line for i, line in enumerate(lines) if i not in drop]
    existing = archive_path.read_text(encoding="utf-8", errors="ignore").rstrip() if archive_path.is_file() else ARCHIVE_HEADER.rstrip()
    atomic_write_text(archive_path, existing + "\n\n" + "\n\n".join(moved_blocks) + "\n")
    atomic_write_text(tasks_path, "\n".join(kept).rstrip() + "\n")
    return [block.splitlines()[0][3:].strip() for block in moved_blocks]


def audit(repo: Path, mode: str, archive_completed: bool = False, reopen: bool = True) -> Dict[str, Any]:
    """reopen=False reports (instead of performing) moves from completed/ back to in-flight/;
    maintain_atlas.py's automatic pass uses it so a deliberately filed plan never bounces back."""
    tasks_path = repo / "project-atlas/tasks.md"
    archive_path = repo / "project-atlas/tasks-archive.md"
    in_flight_dir = repo / "project-atlas/plans/in-flight"
    completed_dir = repo / "project-atlas/plans/completed"

    diagnostics: List[Dict[str, Any]] = []
    moved: List[str] = []
    relinked: List[str] = []

    if not tasks_path.is_file():
        return {"status": "passed", "mode": mode, "moved": [], "relinked": [], "archived_phases": [], "diagnostics": []}

    original_text = tasks_path.read_text(encoding="utf-8", errors="ignore")
    had_trailing_newline = original_text.endswith("\n")
    lines = original_text.splitlines()
    entries = _parse_task_entries(lines)

    in_flight_files = _list_plan_filenames(in_flight_dir)
    completed_files = _list_plan_filenames(completed_dir)
    referenced_filenames: set[str] = set(PLAN_MENTION_RE.findall(original_text))
    if archive_path.is_file():
        referenced_filenames.update(PLAN_MENTION_RE.findall(archive_path.read_text(encoding="utf-8", errors="ignore")))

    for entry in entries:
        filename = Path(entry["path"]).name
        referenced_filenames.add(filename)
        in_flight_here = filename in in_flight_files
        completed_here = filename in completed_files

        if not in_flight_here and not completed_here:
            diagnostics.append(_diagnostic(
                "BROKEN_PLAN_LINK", [f"project-atlas/tasks.md:{entry['line_index'] + 1}", f"project-atlas/{entry['path']}"],
                "Task links to a plan file that does not exist.",
                "Restore the plan file, or remove/repoint the link if the plan was deleted.",
            ))
            continue

        if in_flight_here and completed_here:
            diagnostics.append(_diagnostic(
                "PLAN_DUPLICATE_FILENAME", [f"project-atlas/plans/in-flight/{filename}", f"project-atlas/plans/completed/{filename}"],
                "The same plan filename exists in both in-flight and completed.",
                "Rename or remove one copy so the filename is unique across plans/.",
            ))
            continue

        actual_location = "in-flight" if in_flight_here else "completed"
        expected_location = "completed" if entry["checked"] else "in-flight"
        expected_path = f"plans/{expected_location}/{filename}"
        needs_move = actual_location != expected_location
        needs_relink = entry["path"] != expected_path

        if not needs_move and not needs_relink:
            continue

        if needs_move:
            code = "PLAN_MOVED_TO_COMPLETED" if expected_location == "completed" else "PLAN_MOVED_TO_IN_FLIGHT"
            message = f"Task checkbox state implies this plan belongs in plans/{expected_location}/."
            repair = f"Move the file to plans/{expected_location}/ and update its link in tasks.md."
        else:
            code = "PLAN_LINK_STALE_PATH"
            message = "The task's plan link path does not match the plan file's actual location."
            repair = "Update the link path in tasks.md to match the plan file's actual location."

        paths = [f"project-atlas/tasks.md:{entry['line_index'] + 1}", f"project-atlas/plans/{actual_location}/{filename}"]

        if mode == "apply" and not (needs_move and expected_location == "in-flight" and not reopen):
            if needs_move:
                src = (in_flight_dir if actual_location == "in-flight" else completed_dir) / filename
                dst = (in_flight_dir if expected_location == "in-flight" else completed_dir) / filename
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                moved.append(f"project-atlas/plans/{actual_location}/{filename} -> project-atlas/{expected_path}")
                if actual_location == "in-flight":
                    in_flight_files.discard(filename)
                    completed_files.add(filename)
                else:
                    completed_files.discard(filename)
                    in_flight_files.add(filename)
            old_link = f"]({entry['path']})"
            if old_link in lines[entry["line_index"]]:
                lines[entry["line_index"]] = lines[entry["line_index"]].replace(old_link, f"]({expected_path})", 1)
                relinked.append(f"project-atlas/tasks.md:{entry['line_index'] + 1} -> {expected_path}")
        else:
            diagnostics.append(_diagnostic(code, paths, message, repair))

    for filename in sorted(in_flight_files - referenced_filenames):
        diagnostics.append(_diagnostic(
            "ORPHANED_PLAN", [f"project-atlas/plans/in-flight/{filename}"],
            "Plan file has no task line in tasks.md referencing it.",
            "Add a task line linking to this plan, or remove the plan file if it's stale.",
        ))
    for filename in sorted(completed_files - referenced_filenames):
        diagnostics.append(_diagnostic(
            "ORPHANED_PLAN", [f"project-atlas/plans/completed/{filename}"],
            "Plan file has no task line in tasks.md referencing it.",
            "Add a task line linking to this plan, or remove the plan file if it's stale.",
        ))

    if mode == "apply" and (moved or relinked):
        new_text = "\n".join(lines) + ("\n" if had_trailing_newline else "")
        if new_text != original_text:
            atomic_write_text(tasks_path, new_text)

    archived_phases: List[str] = []
    if mode == "apply" and archive_completed:
        archived_phases = _archive_completed_phases(tasks_path, archive_path)

    return {
        "status": "failed" if diagnostics else "passed",
        "mode": mode,
        "moved": moved,
        "relinked": relinked,
        "archived_phases": archived_phases,
        "diagnostics": diagnostics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile project-atlas plans/ location with tasks.md checkbox state.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--mode", choices=["check", "apply"], default="check")
    parser.add_argument("--archive-completed", action="store_true", help="Apply mode: move fully completed tasks.md phases to tasks-archive.md")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    with atlas_lock(repo):
        result = audit(repo, args.mode, archive_completed=args.archive_completed)

    print(dump_json(result))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
