#!/usr/bin/env python3
"""Reconcile project-atlas/plans/{in-flight,completed} with tasks.md checkbox state.

Convention (documented in agent-playbook.md, "Plan Tracking Protocol"): a task line that tracks a
saved implementation plan links to it as `(plan: [<slug>](plans/in-flight/<file>.md))` (or
`plans/completed/...` once done). This script keeps plan file location, and the link text that
points at it, consistent with the task's checkbox state.

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
    from utils import atlas_lock, atomic_write_text, dump_json
except ImportError:
    from .utils import atlas_lock, atomic_write_text, dump_json

TASK_LINE_RE = re.compile(r"^\s*-\s*\[([ x])\].*\(plan:\s*\[[^\]]*\]\(([^)]+)\)\)\s*$")
PLAN_LINK_RE_TEMPLATE = r"(\(plan:\s*\[[^\]]*\]\()({path})(\))"


def _diagnostic(code: str, paths: List[str], message: str, repair: str) -> Dict[str, Any]:
    return {"code": code, "paths": sorted(set(paths)), "message": message, "suggested_repair": repair}


def _list_plan_filenames(dir_path: Path) -> set[str]:
    if not dir_path.is_dir():
        return set()
    return {p.name for p in dir_path.glob("*.md") if p.name.lower() != "readme.md"}


def _parse_task_entries(lines: List[str]) -> List[Dict[str, Any]]:
    entries = []
    for i, line in enumerate(lines):
        match = TASK_LINE_RE.match(line)
        if not match:
            continue
        path = match.group(2)
        if not (path.startswith("plans/in-flight/") or path.startswith("plans/completed/")):
            continue
        entries.append({"line_index": i, "checked": match.group(1) == "x", "path": path})
    return entries


def audit(repo: Path, mode: str) -> Dict[str, Any]:
    tasks_path = repo / "project-atlas/tasks.md"
    in_flight_dir = repo / "project-atlas/plans/in-flight"
    completed_dir = repo / "project-atlas/plans/completed"

    diagnostics: List[Dict[str, Any]] = []
    moved: List[str] = []
    relinked: List[str] = []

    if not tasks_path.is_file():
        return {"status": "passed", "mode": mode, "moved": [], "relinked": [], "diagnostics": []}

    original_text = tasks_path.read_text(encoding="utf-8", errors="ignore")
    had_trailing_newline = original_text.endswith("\n")
    lines = original_text.splitlines()
    entries = _parse_task_entries(lines)

    in_flight_files = _list_plan_filenames(in_flight_dir)
    completed_files = _list_plan_filenames(completed_dir)
    referenced_filenames: set[str] = set()

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

        if mode == "apply":
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
            link_pattern = re.compile(PLAN_LINK_RE_TEMPLATE.format(path=re.escape(entry["path"])))
            new_line, count = link_pattern.subn(r"\g<1>" + expected_path + r"\g<3>", lines[entry["line_index"]], count=1)
            if count:
                lines[entry["line_index"]] = new_line
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

    return {
        "status": "failed" if diagnostics else "passed",
        "mode": mode,
        "moved": moved,
        "relinked": relinked,
        "diagnostics": diagnostics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile project-atlas plans/ location with tasks.md checkbox state.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--mode", choices=["check", "apply"], default="check")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    with atlas_lock(repo):
        result = audit(repo, args.mode)

    print(dump_json(result))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
