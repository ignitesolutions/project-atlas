import json
import shutil
import subprocess
import sys
import tempfile
import time
import os
import threading
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

from scan_repo import extract_cfc_methods, scan_repository
from utils import redact_secrets, should_ignore, verify_existing_atlas, atlas_lock, atomic_write_text, migrate_manifest
from write_templates import create_existing, create_greenfield, convert_greenfield, write_root_agent_file


class ProjectAtlasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        (self.repo / "README.md").write_text("# Fixture\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def bootstrap(self):
        scan = scan_repository(self.repo)
        result = create_existing(self.repo, scan)
        self.assertEqual("passed", result["status"])
        return scan, result

    def test_existing_bootstrap_creates_decisions_scaffold(self):
        _, result = self.bootstrap()
        readme = self.repo / "project-atlas/decisions/README.md"
        template = self.repo / "project-atlas/decisions/TEMPLATE.md"
        self.assertTrue(readme.is_file())
        self.assertTrue(template.is_file())
        self.assertIn("## Decision", template.read_text(encoding="utf-8"))
        self.assertIn("project-atlas/decisions/README.md", result["created"])
        self.assertIn("project-atlas/decisions/TEMPLATE.md", result["created"])

        # A hand-authored decision record must survive a subsequent maintenance update.
        custom = readme.parent / "0001-use-queryexecute-for-sql.md"
        custom.write_text("# Use queryExecute for all SQL\n", encoding="utf-8")
        create_existing(self.repo, scan_repository(self.repo), update=True)
        self.assertEqual("# Use queryExecute for all SQL\n", custom.read_text(encoding="utf-8"))

    def test_update_backfills_missing_structure_with_no_source_changes(self):
        # A skill upgrade can add newly-required files (e.g. decisions/README.md). A repo
        # bootstrapped under an older skill version simulates that by simply missing them.
        self.bootstrap()
        decisions_dir = self.repo / "project-atlas/decisions"
        shutil.rmtree(decisions_dir)
        self.assertFalse(decisions_dir.exists())

        result = subprocess.run(
            [sys.executable, str(SKILL / "scripts/maintain_atlas.py"), "--repo", str(self.repo), "--mode", "update"],
            capture_output=True, text=True, check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual("passed", payload["status"])
        self.assertIn("project-atlas/decisions/README.md", payload["created"])
        self.assertIn("project-atlas/decisions/TEMPLATE.md", payload["created"])
        self.assertTrue((decisions_dir / "README.md").is_file())
        self.assertTrue((decisions_dir / "TEMPLATE.md").is_file())

        # Running it again with everything present and no source changes stays a true no-op.
        second = subprocess.run(
            [sys.executable, str(SKILL / "scripts/maintain_atlas.py"), "--repo", str(self.repo), "--mode", "update"],
            capture_output=True, text=True, check=True,
        )
        second_payload = json.loads(second.stdout)
        self.assertTrue(second_payload.get("no_changes"))
        self.assertEqual([], second_payload["updated"])

    def test_skill_version_reconciliation(self):
        self.bootstrap()
        manifest_path = self.repo / "project-atlas/atlas.json"
        playbook = self.repo / "project-atlas/agent-playbook.md"
        self.assertIn("## Plan Tracking Protocol", playbook.read_text(encoding="utf-8"))

        # Simulate a repo bootstrapped by an older skill version: its manifest predates
        # skill_version tracking and it never had the skill-guidance managed section.
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["skill_version"] = "0.0.0-test-old"
        manifest["managed_artifacts"].pop("project-atlas/agent-playbook.md", None)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        text = playbook.read_text(encoding="utf-8")
        start = text.index("<!-- project-atlas:generated:skill-guidance:start -->")
        end = text.index("<!-- project-atlas:generated:skill-guidance:end -->") + len("<!-- project-atlas:generated:skill-guidance:end -->")
        playbook.write_text(text[:start] + text[end:], encoding="utf-8")
        self.assertNotIn("## Plan Tracking Protocol", playbook.read_text(encoding="utf-8"))

        def run(*extra):
            proc = subprocess.run(
                [sys.executable, str(SKILL / "scripts/maintain_atlas.py"), "--repo", str(self.repo), *extra],
                capture_output=True, text=True, check=False,
            )
            return json.loads(proc.stdout)

        check_payload = run("--mode", "check", "--level", "structure")
        self.assertIn("SKILL_VERSION_STALE", {item["code"] for item in check_payload["diagnostics"]})

        reconcile_payload = run("--mode", "reconcile")
        self.assertEqual("passed", reconcile_payload["status"])
        self.assertIn("## Plan Tracking Protocol", playbook.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertNotEqual("0.0.0-test-old", manifest["skill_version"])

        # A hand-edited managed section blocks further sync until --force.
        edited = playbook.read_text(encoding="utf-8").replace(
            "## Plan Tracking Protocol", "## Plan Tracking Protocol (edited by hand)"
        )
        playbook.write_text(edited, encoding="utf-8")
        blocked_payload = run("--mode", "reconcile")
        self.assertIn("GENERATED_CONTENT_MODIFIED", {item["code"] for item in blocked_payload["diagnostics"]})
        self.assertIn("edited by hand", playbook.read_text(encoding="utf-8"))

        forced_payload = run("--mode", "reconcile", "--force")
        self.assertEqual("passed", forced_payload["status"])
        self.assertNotIn("edited by hand", playbook.read_text(encoding="utf-8"))

        # Idempotent once nothing is left to reconcile.
        again_payload = run("--mode", "reconcile")
        self.assertEqual("passed", again_payload["status"])

    def test_living_documents_survive_marker_phrase_and_force_in_greenfield(self):
        # tasks.md/launch-checklist.md accumulate freeform hand-authored prose for the life of a
        # project. If that prose ever happens to contain one of the generic scaffold-placeholder
        # marker phrases (e.g. a completed task literally mentioning "replace with confirmed
        # project details"), the old write_file() path would treat the whole file as still a
        # placeholder and silently overwrite it — this must never happen, not even with --force.
        create_greenfield(self.repo)
        tasks = self.repo / "project-atlas/tasks.md"
        checklist = self.repo / "project-atlas/launch-checklist.md"
        real_tasks = "# Tasks\n\n## Phase 1: Zone Builder\n\n- [x] Replace with confirmed project details for zone rendering.\n"
        real_checklist = "# Launch Checklist\n\n- [ ] Generated placeholder value for STRIPE_KEY must be set in prod.\n"
        tasks.write_text(real_tasks, encoding="utf-8")
        checklist.write_text(real_checklist, encoding="utf-8")

        create_greenfield(self.repo, force=True)
        # tasks.md legitimately gains the digest-tracked plan-link-convention managed section
        # (an append, not an overwrite) — the real hand-authored content must still be intact.
        self.assertIn(real_tasks.strip(), tasks.read_text(encoding="utf-8"))
        self.assertEqual(real_checklist, checklist.read_text(encoding="utf-8"))

    def test_launch_checklist_survives_marker_phrase_and_force_in_existing_mode(self):
        (self.repo / "config.py").write_text("value = os.environ.get('STRIPE_KEY')\n", encoding="utf-8")
        scan = scan_repository(self.repo)
        self.assertTrue(scan.get("third_party_indicators"))
        create_existing(self.repo, scan)
        checklist = self.repo / "project-atlas/launch-checklist.md"
        self.assertTrue(checklist.is_file())
        real_checklist = "# Launch Checklist\n\n- [ ] Generated placeholder value for STRIPE_KEY must be set in prod.\n"
        checklist.write_text(real_checklist, encoding="utf-8")

        create_existing(self.repo, scan_repository(self.repo), force=True)
        self.assertEqual(real_checklist, checklist.read_text(encoding="utf-8"))

    def test_ignore_prunes_vendor_and_supports_negation(self):
        (self.repo / ".gitignore").write_text("vendor/\n*.log\n!important.log\n", encoding="utf-8")
        (self.repo / "vendor/deep").mkdir(parents=True)
        (self.repo / "vendor/deep/secret.cfc").write_text("component {}", encoding="utf-8")
        (self.repo / "debug.log").write_text("x", encoding="utf-8")
        (self.repo / "important.log").write_text("x", encoding="utf-8")
        scan = scan_repository(self.repo)
        self.assertNotIn("vendor/deep/secret.cfc", scan["files"])
        self.assertNotIn("debug.log", scan["files"])
        self.assertIn("important.log", scan["files"])

    def test_secrets_are_skipped_and_values_redacted(self):
        (self.repo / ".env").write_text("API_KEY=real-secret", encoding="utf-8")
        scan = scan_repository(self.repo)
        self.assertNotIn(".env", scan["files"])
        self.assertNotIn("real-secret", redact_secrets("api_key=real-secret"))

    def test_truncation_is_reported(self):
        for index in range(5):
            (self.repo / f"file-{index}.txt").write_text("x", encoding="utf-8")
        scan = scan_repository(self.repo, max_files=2)
        self.assertTrue(scan["truncated"])
        self.assertIsNotNone(scan["truncated_at"])

    def test_cfml_tag_and_script_methods(self):
        text = '<cffunction name="tagMethod"></cffunction>\npublic string function scriptMethod() {}'
        self.assertEqual(["scriptMethod", "tagMethod"], extract_cfc_methods(text))

    def test_stack_detection_ignores_atlas_false_positives(self):
        (self.repo / "project-atlas").mkdir()
        (self.repo / "project-atlas/notes.md").write_text("React Redis PostgreSQL", encoding="utf-8")
        scan = scan_repository(self.repo)
        self.assertFalse(scan["stack"]["react"])
        self.assertFalse(scan["stack"]["redis"])
        self.assertFalse(scan["stack"]["postgresql"])

    def test_update_preserves_hand_authored_content_and_is_idempotent(self):
        self.bootstrap()
        code_map = self.repo / "project-atlas/code-map.md"
        code_map.write_text("Human note.\n\n" + code_map.read_text(encoding="utf-8"), encoding="utf-8")
        scan = scan_repository(self.repo)
        create_existing(self.repo, scan, update=True)
        first = code_map.read_text(encoding="utf-8")
        self.assertTrue(first.startswith("Human note."))
        create_existing(self.repo, scan_repository(self.repo), update=True)
        self.assertTrue(code_map.read_text(encoding="utf-8").startswith("Human note."))

    def test_stale_source_and_enrichment_diagnostics(self):
        self.bootstrap()
        manifest_path = self.repo / "project-atlas/atlas.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["sources"]["architecture.md"] = ["missing/service.cfc"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = verify_existing_atlas(self.repo, scan=scan_repository(self.repo), level="semantic")
        codes = {item["code"] for item in result["diagnostics"]}
        self.assertIn("STALE_SOURCE", codes)
        self.assertIn("ENRICHMENT_REQUIRED", codes)

    def test_source_edit_marks_evidence_stale(self):
        source = self.repo / "service.cfc"
        source.write_text("component {}", encoding="utf-8")
        self.bootstrap()
        source.write_text("component { function changed() {} }", encoding="utf-8")
        result = verify_existing_atlas(self.repo, scan=scan_repository(self.repo), level="evidence")
        self.assertIn("GENERATED_DRIFT", {item["code"] for item in result["diagnostics"]})

    def test_content_digest_detects_same_size_preserved_timestamp(self):
        source = self.repo / "service.cfc"
        source.write_text("component { function one() {} }", encoding="utf-8")
        self.bootstrap()
        original = source.stat()
        source.write_text("component { function two() {} }", encoding="utf-8")
        os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))
        result = verify_existing_atlas(self.repo, scan=scan_repository(self.repo), level="evidence")
        self.assertIn("GENERATED_DRIFT", {item["code"] for item in result["diagnostics"]})

    def test_cfc_index_refreshes_and_is_removed_across_threshold(self):
        for index in range(25):
            (self.repo / f"C{index}.cfc").write_text(f"component {{ function m{index}() {{}} }}", encoding="utf-8")
        self.bootstrap()
        index_path = self.repo / "project-atlas/cfc-index.md"
        (self.repo / "C25.cfc").write_text("component { function newest() {} }", encoding="utf-8")
        result = create_existing(self.repo, scan_repository(self.repo), update=True)
        self.assertEqual("passed", result["status"])
        self.assertIn("C25.cfc", index_path.read_text(encoding="utf-8"))
        (self.repo / "C25.cfc").unlink()
        (self.repo / "C24.cfc").unlink()
        result = create_existing(self.repo, scan_repository(self.repo), update=True)
        self.assertEqual("passed", result["status"])
        self.assertFalse(index_path.exists())
        self.assertIn("C23.cfc", (self.repo / "project-atlas/code-map.md").read_text(encoding="utf-8"))

    def test_hand_edited_generated_index_is_protected(self):
        for index in range(25):
            (self.repo / f"C{index}.cfc").write_text("component {}", encoding="utf-8")
        self.bootstrap()
        index_path = self.repo / "project-atlas/cfc-index.md"
        index_path.write_text(index_path.read_text(encoding="utf-8") + "\nHuman edit.\n", encoding="utf-8")
        result = create_existing(self.repo, scan_repository(self.repo), update=True)
        self.assertEqual("failed", result["status"])
        self.assertIn("GENERATED_CONTENT_MODIFIED", {item["code"] for item in result["diagnostics"]})
        self.assertIn("Human edit.", index_path.read_text(encoding="utf-8"))

    def test_invalid_and_unsupported_manifests_fail_structure(self):
        self.bootstrap()
        manifest_path = self.repo / "project-atlas/atlas.json"
        manifest_path.write_text("{broken", encoding="utf-8")
        result = verify_existing_atlas(self.repo, scan=scan_repository(self.repo), level="structure")
        self.assertIn("MANIFEST_INVALID_JSON", {item["code"] for item in result["diagnostics"]})
        manifest_path.write_text(json.dumps({"schema_version": 999}), encoding="utf-8")
        result = verify_existing_atlas(self.repo, scan=scan_repository(self.repo), level="structure")
        codes = {item["code"] for item in result["diagnostics"]}
        self.assertIn("MANIFEST_SCHEMA_UNSUPPORTED", codes)
        self.assertIn("MANIFEST_FIELD_MISSING", codes)

    def test_v2_manifest_migrates_generated_ownership(self):
        self.bootstrap()
        manifest_path = self.repo / "project-atlas/atlas.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["schema_version"] = 2
        manifest["managed_sections"] = {"project-atlas/code-map.md": ["evidence"]}
        manifest.pop("managed_artifacts", None)
        manifest.pop("last_verified_state", None)
        migrated = migrate_manifest(manifest, self.repo)
        self.assertEqual(3, migrated["schema_version"])
        owner = migrated["managed_artifacts"]["project-atlas/code-map.md"]
        self.assertEqual("section", owner["kind"])
        self.assertEqual(64, len(owner["digest"]))

    def test_semantic_contract_requires_prose_and_evidence(self):
        self.bootstrap()
        for name, criteria in [("project-overview.md", ["purpose", "users", "workflows"]), ("architecture.md", ["request flow", "boundaries"])]:
            contract = {key: {"status": "complete", "evidence": [], "note": ""} for key in criteria}
            (self.repo / "project-atlas" / name).write_text("# Empty\n<!-- project-atlas:contract " + json.dumps(contract) + " -->\n", encoding="utf-8")
        result = verify_existing_atlas(self.repo, scan=scan_repository(self.repo), level="semantic")
        self.assertIn("CONTRACT_EVIDENCE_INVALID", {item["code"] for item in result["diagnostics"]})

    def test_semantic_contract_accepts_supported_complete_and_explained_unknown(self):
        self.bootstrap()
        overview = {"purpose": {"status": "complete", "evidence": ["README.md"], "note": "The README directly documents the product purpose."}, "users": {"status": "unknown", "evidence": [], "note": "User roles are not documented and affect authorization design."}, "workflows": {"status": "complete", "evidence": ["README.md"], "note": "The README documents the primary supported workflows."}}
        architecture = {"request flow": {"status": "unknown", "evidence": [], "note": "Request routing is not documented and affects implementation placement."}, "boundaries": {"status": "complete", "evidence": ["README.md"], "note": "The README identifies the relevant application boundary."}}
        prose = "\nThis repository has sufficiently detailed hand-authored context explaining the application, its behavior, boundaries, and implementation evidence for future agents.\n"
        (self.repo / "project-atlas/project-overview.md").write_text("# Overview\n<!-- project-atlas:contract " + json.dumps(overview) + " -->" + prose, encoding="utf-8")
        (self.repo / "project-atlas/architecture.md").write_text("# Architecture\n<!-- project-atlas:contract " + json.dumps(architecture) + " -->" + prose, encoding="utf-8")
        result = verify_existing_atlas(self.repo, scan=scan_repository(self.repo), level="semantic")
        self.assertEqual("passed", result["status"])
        self.assertEqual("verified", result["lifecycle_state"])

    def test_root_sentinels_preserve_external_content(self):
        target = self.repo / "AGENTS.md"
        target.write_text("External rule.\n", encoding="utf-8")
        created, updated, skipped = [], [], []
        write_root_agent_file(target, "fixture", created, updated, skipped)
        first = target.read_text(encoding="utf-8")
        write_root_agent_file(target, "fixture", created, updated, skipped)
        self.assertEqual(first, target.read_text(encoding="utf-8"))
        self.assertTrue(first.startswith("External rule."))

    def test_greenfield_bootstrap_has_root_sentinels(self):
        result = create_greenfield(self.repo)
        self.assertEqual("passed", result["status"])
        for name in ["AGENTS.md", "CLAUDE.md"]:
            text = (self.repo / name).read_text(encoding="utf-8")
            self.assertIn("<!-- project-atlas:start -->", text)
            self.assertIn("<!-- project-atlas:end -->", text)

    def test_greenfield_verifies_and_converts(self):
        create_greenfield(self.repo)
        result = verify_existing_atlas(self.repo, scan=scan_repository(self.repo), level="structure")
        self.assertEqual("passed", result["status"])
        self.assertEqual("greenfield", result["generation_mode"])
        converted = convert_greenfield(self.repo, scan_repository(self.repo), force=True)
        self.assertEqual("existing", converted["generation_mode"])
        result = verify_existing_atlas(self.repo, scan=scan_repository(self.repo), level="structure")
        self.assertEqual("existing", result["generation_mode"])

    def test_git_discovery_honors_gitignore_and_includes_untracked(self):
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
        (self.repo / "ignored.txt").write_text("x", encoding="utf-8")
        (self.repo / "untracked.cfc").write_text("component {}", encoding="utf-8")
        scan = scan_repository(self.repo)
        self.assertEqual("git", scan["discovery"])
        self.assertNotIn("ignored.txt", scan["files"])
        self.assertIn("untracked.cfc", scan["files"])

    def test_scan_cache_reuses_unchanged_parsed_evidence(self):
        (self.repo / "service.cfc").write_text("component { function run() {} }", encoding="utf-8")
        first = scan_repository(self.repo, write_cache=True)
        second = scan_repository(self.repo, write_cache=True)
        self.assertGreater(first["scan_cache"]["misses"], 0)
        self.assertEqual(0, second["scan_cache"]["misses"])
        self.assertGreater(second["scan_cache"]["hits"], 0)

    def test_malformed_root_sentinels_are_reported(self):
        self.bootstrap()
        (self.repo / "AGENTS.md").write_text("<!-- project-atlas:end -->\n<!-- project-atlas:start -->", encoding="utf-8")
        result = verify_existing_atlas(self.repo, scan=scan_repository(self.repo), level="structure")
        self.assertIn("MANAGED_SENTINEL_INVALID", {item["code"] for item in result["diagnostics"]})

    def test_duplicate_managed_section_sentinels_are_reported(self):
        self.bootstrap()
        path = self.repo / "project-atlas/code-map.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text + "\n<!-- project-atlas:generated:evidence:start -->\nduplicate\n<!-- project-atlas:generated:evidence:end -->\n", encoding="utf-8")
        result = verify_existing_atlas(self.repo, scan=scan_repository(self.repo), level="structure")
        self.assertIn("MANAGED_SENTINEL_INVALID", {item["code"] for item in result["diagnostics"]})

    def test_atomic_write_and_lock_timeout(self):
        target = self.repo / "project-atlas/value.txt"
        atomic_write_text(target, "complete")
        self.assertEqual("complete", target.read_text(encoding="utf-8"))
        errors = []
        with atlas_lock(self.repo):
            def contender():
                try:
                    with atlas_lock(self.repo, timeout_seconds=0.1):
                        pass
                except Exception as exc:
                    errors.append(exc)
            thread = threading.Thread(target=contender)
            thread.start()
            thread.join()
        self.assertTrue(any(isinstance(exc, TimeoutError) for exc in errors))

    def test_stale_scan_cannot_overwrite_concurrent_atlas_update(self):
        self.bootstrap()
        stale_scan = scan_repository(self.repo)
        manifest_path = self.repo / "project-atlas/atlas.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["repository_fingerprint"] = "a" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = create_existing(self.repo, stale_scan, update=True)
        self.assertEqual("failed", result["status"])
        self.assertIn("SCAN_STALE_CONCURRENT_UPDATE", {item["code"] for item in result["diagnostics"]})

    def test_cli_json_envelope_and_lifecycle_refresh(self):
        bootstrap = subprocess.run([sys.executable, str(SKILL / "scripts/bootstrap_atlas.py"), "--repo", str(self.repo)], capture_output=True, text=True, check=True)
        payload = json.loads(bootstrap.stdout)
        for key in ["status", "generation_mode", "lifecycle_state", "created", "updated", "diagnostics", "verification"]:
            self.assertIn(key, payload)
        check = subprocess.run([sys.executable, str(SKILL / "scripts/maintain_atlas.py"), "--repo", str(self.repo), "--mode", "check", "--level", "structure"], capture_output=True, text=True, check=True)
        payload = json.loads(check.stdout)
        for key in ["status", "generation_mode", "lifecycle_state", "created", "updated", "diagnostics", "verification"]:
            self.assertIn(key, payload)
        overview = {"purpose": {"status": "complete", "evidence": ["README.md"], "note": "The README directly documents the product purpose."}, "users": {"status": "unknown", "evidence": [], "note": "User roles are unknown and affect access-control planning."}, "workflows": {"status": "complete", "evidence": ["README.md"], "note": "The README documents the primary supported workflows."}}
        architecture = {"request flow": {"status": "unknown", "evidence": [], "note": "Request routing is unknown and affects implementation placement."}, "boundaries": {"status": "complete", "evidence": ["README.md"], "note": "The README identifies the relevant application boundary."}}
        prose = "\nThis hand-authored project context is deliberately long enough to explain supported behavior, evidence, system boundaries, and the decisions future agents must understand.\n"
        (self.repo / "project-atlas/project-overview.md").write_text("# Overview\n<!-- project-atlas:contract " + json.dumps(overview) + " -->" + prose, encoding="utf-8")
        (self.repo / "project-atlas/architecture.md").write_text("# Architecture\n<!-- project-atlas:contract " + json.dumps(architecture) + " -->" + prose, encoding="utf-8")
        update = subprocess.run([sys.executable, str(SKILL / "scripts/maintain_atlas.py"), "--repo", str(self.repo), "--mode", "update"], capture_output=True, text=True, check=True)
        payload = json.loads(update.stdout)
        self.assertEqual("verified", payload["lifecycle_state"])
        manifest = json.loads((self.repo / "project-atlas/atlas.json").read_text(encoding="utf-8"))
        self.assertEqual("verified", manifest["lifecycle_state"])
        second = subprocess.run([sys.executable, str(SKILL / "scripts/maintain_atlas.py"), "--repo", str(self.repo), "--mode", "update"], capture_output=True, text=True, check=True)
        payload = json.loads(second.stdout)
        self.assertTrue(payload["no_changes"])
        self.assertEqual([], payload["updated"])

    def test_large_scan_performance_smoke(self):
        for index in range(500):
            (self.repo / f"f{index}.txt").write_text("x", encoding="utf-8")
        started = time.monotonic()
        scan = scan_repository(self.repo)
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertGreaterEqual(scan["file_count"], 501)


if __name__ == "__main__":
    unittest.main()
