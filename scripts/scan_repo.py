#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import argparse
import json
import os
import re
import hashlib
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

try:
    from detect_stack import detect_stack_from_paths
    from utils import load_ignore_patterns, should_ignore, rel_posix, read_text_limited, is_secret_path, dump_json, atomic_write_text, content_digest, load_manifest
except ImportError:
    from .detect_stack import detect_stack_from_paths
    from .utils import load_ignore_patterns, should_ignore, rel_posix, read_text_limited, is_secret_path, dump_json, atomic_write_text, content_digest, load_manifest

CFFUNCTION_RE = re.compile(r"<\s*cffunction\b[^>]*\bname\s*=\s*['\"]([^'\"]+)['\"]", re.I)
DATASOURCE_RE = re.compile(r"(?:this\.datasource|\bdatasource\b)\s*[:=]\s*['\"]([A-Za-z0-9_.\-]+)['\"]", re.I)
CFCOMPONENT_TAG_RE = re.compile(r"<\s*cfcomponent\b", re.I)
SCRIPT_FUNCTION_RE = re.compile(
    r"(?im)^\s*(?:(?:public|private|remote|package)\s+)?(?:(?:static|final)\s+)?(?:(?:[A-Za-z_$][\w.$<>\[\],]*|any|void|numeric|string|boolean|query|struct|array)\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("
)

BUCKET_RULES = [
    ("entry_points", ["application.cfc", "application.cfm", "index.cfm", "index.php", "app.py", "manage.py", "server.js", "main.js"]),
    ("routes", ["route", "routes"]),
    ("controllers", ["controller", "controllers"]),
    ("handlers", ["handler", "handlers"]),
    ("services", ["service", "services"]),
    ("repositories", ["repository", "repositories", "dao"]),
    ("models", ["model", "models"]),
    ("entities", ["entity", "entities"]),
    ("components", ["component", "components", ".cfc"]),
    ("views", ["view", "views", "templates"]),
    ("frontend", ["frontend", "client", "assets", ".jsx", ".tsx", ".vue", ".svelte"]),
    ("config", ["config", ".env", "settings", "server.json", "box.json"]),
    ("database", ["database", "db", "schema", "migration", "migrations", "sql"]),
    ("migrations", ["migration", "migrations"]),
    ("tests", ["test", "tests", "spec", "specs"]),
    ("auth_candidates", ["auth", "login", "logout", "permission", "role", "session", "security"]),
    ("permission_candidates", ["permission", "role", "acl", "access"]),
    ("deployment", ["deploy", "docker", "compose", "nginx", "iis"]),
    ("ci_cd", [".github", "workflow", "gitlab-ci", "jenkins", "circleci", "azure-pipelines"]),
    ("docs", ["readme", "docs", "documentation", ".md"]),
]

EVIDENCE_NAMES = {
    "application.cfc", "application.cfm", "box.json", "server.json", "composer.json", "package.json",
    "pyproject.toml", "requirements.txt", "dockerfile", "docker-compose.yml", "compose.yml", "readme.md",
}

# Indicators of things that differ between dev/stage/live. Matches feed the
# launch-checklist.md evidence section: service name + file paths only, never values.
# Patterns favor domain/SDK-anchored text over bare dictionary words (e.g. "Square",
# "Drift", "Segment") to avoid false positives from unrelated prose or variable names.
THIRD_PARTY_PATTERNS = [
    # Payments
    ("Stripe", re.compile(r"\bstripe\b", re.I)),
    ("Authorize.net", re.compile(r"authorize\.?net|\bauthnet\b", re.I)),
    ("PayPal", re.compile(r"\bpaypal\b", re.I)),
    ("Braintree", re.compile(r"\bbraintree\b", re.I)),
    ("Square", re.compile(r"\bsquareup\b|square[_-]?connect|SqPaymentForm|squareup\.com", re.I)),
    ("Adyen", re.compile(r"\badyen\b", re.I)),
    ("Worldpay", re.compile(r"\bworldpay\b", re.I)),
    ("NMI (Network Merchants)", re.compile(r"securenmi\.com|\bnmi[_-]?(api|gateway)\b|networkmerchants", re.I)),
    ("2Checkout / Verifone", re.compile(r"\b2checkout\b|\bverifone\b", re.I)),
    ("Klarna", re.compile(r"\bklarna\b", re.I)),
    ("Plaid", re.compile(r"\bplaid\b", re.I)),
    ("PayPal Payflow", re.compile(r"\bpayflow\b", re.I)),

    # Communications (email / SMS)
    ("Twilio", re.compile(r"\btwilio\b", re.I)),
    ("SendGrid", re.compile(r"\bsendgrid\b", re.I)),
    ("Mailgun", re.compile(r"\bmailgun\b", re.I)),
    ("Postmark", re.compile(r"\bpostmark(app)?\b", re.I)),
    ("AWS SES", re.compile(r"\bamazon[_-]?ses\b|\bawsses\b|sendrawemail", re.I)),
    ("Mandrill", re.compile(r"\bmandrill\b", re.I)),
    ("Vonage / Nexmo", re.compile(r"\bvonage\b|\bnexmo\b", re.I)),
    ("MessageBird", re.compile(r"\bmessagebird\b", re.I)),

    # Cloud, storage, and CDN
    ("AWS / S3", re.compile(r"\bamazonaws\b|\baws[_-]?(access|secret|region)\b|\bs3bucket\b", re.I)),
    ("Azure", re.compile(r"\bazure\b|azuread|entra[_-]?id", re.I)),
    ("Google Cloud Platform", re.compile(r"google[_-]?cloud|\bgcs\b|storage\.googleapis|\bgcp\b", re.I)),
    ("DigitalOcean Spaces", re.compile(r"digitalocean|do[_-]?spaces", re.I)),
    ("Cloudinary", re.compile(r"\bcloudinary\b", re.I)),
    ("Cloudflare", re.compile(r"\bcloudflare\b", re.I)),
    ("Fastly", re.compile(r"\bfastly\b", re.I)),
    ("Akamai", re.compile(r"\bakamai\b", re.I)),
    ("CloudFront", re.compile(r"\bcloudfront\b", re.I)),

    # Auth / identity
    ("Auth0", re.compile(r"\bauth0\b", re.I)),
    ("Okta", re.compile(r"\bokta\b", re.I)),
    ("OneLogin", re.compile(r"\bonelogin\b", re.I)),
    ("Google OAuth", re.compile(r"accounts\.google\.com|google[_-]?oauth", re.I)),
    ("Facebook Login", re.compile(r"graph\.facebook\.com|facebook[_-]?(login|oauth)", re.I)),
    ("LinkedIn OAuth", re.compile(r"api\.linkedin\.com|linkedin[_-]?oauth", re.I)),

    # Analytics / tracking
    ("Google Analytics", re.compile(r"google-analytics|gtag\s*\(|\bUA-\d{4,}|\bG-[A-Z0-9]{6,}\b", re.I)),
    ("Google Tag Manager", re.compile(r"googletagmanager|\bGTM-[A-Z0-9]+\b", re.I)),
    ("Mixpanel", re.compile(r"\bmixpanel\b", re.I)),
    ("Segment", re.compile(r"segment\.(com|io)|cdn\.segment", re.I)),
    ("Amplitude", re.compile(r"\bamplitude\b", re.I)),
    ("Hotjar", re.compile(r"\bhotjar\b", re.I)),
    ("Facebook Pixel", re.compile(r"\bfbq\s*\(|facebook[_-]?pixel", re.I)),

    # Error tracking / observability
    ("Sentry", re.compile(r"\bsentry\b", re.I)),
    ("Bugsnag", re.compile(r"\bbugsnag\b", re.I)),
    ("Rollbar", re.compile(r"\brollbar\b", re.I)),
    ("New Relic", re.compile(r"new[_-]?relic|newrelic", re.I)),
    ("Datadog", re.compile(r"\bdatadog\b|\bdd-trace\b", re.I)),
    ("Honeybadger", re.compile(r"\bhoneybadger\b", re.I)),
    ("LogRocket", re.compile(r"\blogrocket\b", re.I)),
    ("PagerDuty", re.compile(r"\bpagerduty\b", re.I)),

    # Search
    ("Algolia", re.compile(r"\balgolia\b", re.I)),
    ("Elasticsearch", re.compile(r"\belasticsearch\b|elastic\.co", re.I)),
    ("Solr", re.compile(r"\bsolr\b", re.I)),

    # Maps
    ("Google Maps", re.compile(r"maps\.google|googleapis.*maps|google[_-]?maps", re.I)),
    ("Mapbox", re.compile(r"\bmapbox\b", re.I)),

    # CAPTCHA
    ("reCAPTCHA", re.compile(r"recaptcha", re.I)),
    ("hCaptcha", re.compile(r"\bhcaptcha\b", re.I)),

    # Feature flags
    ("LaunchDarkly", re.compile(r"launchdarkly", re.I)),
    ("Split.io", re.compile(r"split\.io|\bsplitio\b", re.I)),

    # Support / CRM / marketing
    ("Intercom", re.compile(r"\bintercom\b", re.I)),
    ("Zendesk", re.compile(r"\bzendesk\b", re.I)),
    ("Drift", re.compile(r"drift\.com|driftt\.com|window\.drift", re.I)),
    ("Freshdesk", re.compile(r"\bfreshdesk\b", re.I)),
    ("Salesforce", re.compile(r"\bsalesforce\b", re.I)),
    ("HubSpot", re.compile(r"\bhubspot\b", re.I)),
    ("Mailchimp", re.compile(r"\bmailchimp\b", re.I)),
    ("Marketo", re.compile(r"\bmarketo\b", re.I)),
    ("Klaviyo", re.compile(r"\bklaviyo\b", re.I)),
    ("ActiveCampaign", re.compile(r"activecampaign", re.I)),

    # E-commerce / CMS platforms
    ("Shopify", re.compile(r"\bshopify\b", re.I)),
    ("WooCommerce", re.compile(r"woocommerce", re.I)),
    ("Magento", re.compile(r"\bmagento\b", re.I)),
    ("BigCommerce", re.compile(r"bigcommerce", re.I)),

    # Push notifications / realtime
    ("Firebase / FCM", re.compile(r"\bfirebase\b|\bfcm[_-]?(token|key)\b", re.I)),
    ("OneSignal", re.compile(r"onesignal", re.I)),
    ("Pusher", re.compile(r"pusherapp|pusher\.com|\bnew Pusher\(", re.I)),

    # Video / meetings
    ("Vimeo", re.compile(r"\bvimeo\b", re.I)),
    ("YouTube API", re.compile(r"youtube.*api|googleapis.*youtube|\bytplayer\b", re.I)),
    ("Zoom", re.compile(r"zoom\.us|zoom[_-]?api", re.I)),

    # Documents / e-signature
    ("DocuSign", re.compile(r"docusign", re.I)),
    ("Adobe Sign", re.compile(r"adobesign|echosign", re.I)),

    # Team chat webhooks
    ("Slack", re.compile(r"hooks\.slack\.com|slack[_-]?webhook|\bslack[_-]?api\b", re.I)),
    ("Microsoft Teams", re.compile(r"outlook\.office\.com/webhook|teams[_-]?webhook", re.I)),

    # CMS platforms
    ("Mura CMS", re.compile(r"\bmura[_-]?(cms)?\b|mura\.com", re.I)),
    ("Masa CMS", re.compile(r"\bmasa[_-]?(cms)?\b|masa\.cms", re.I)),

    # CFML Frameworks (Lucee / Railo)
    ("Lucee", re.compile(r"\blucee\b|lucee\.cfg", re.I)),
    ("Railo", re.compile(r"coldfusion\.railo\b|railo\.cfg", re.I)),

    # Improved precision patterns
    ("Stripe Checkout/Elements", re.compile(r"\bstripe[_-]?(checkout|elements)\b|stripe\.com", re.I)),
    ("PayPal Payflow Pro", re.compile(r"\bpayflowpro\b|payflow\.net", re.I)),
    ("Twilio SendGrid API", re.compile(r"sendgrid[_-]?api[-_]?key|sendgrid\.net", re.I)),
    ("Vercel CLI/Config", re.compile(r"\bvercel[_-]?(cli)?\b|vercel\.json", re.I)),
    ("Netlify Config", re.compile(r"\bnetslify[^a-z]|netlify[_-]?config\.(toml|json)\b", re.I)),

    # More precise patterns for existing services (avoid false positives from internal code)
    ("AWS Lambda/Serverless", re.compile(r"lambda_function\.py|aws-lambda-adapter\b|\baws[_-]?(lambda)?function\b", re.I)),
    ("Firebase App Check", re.compile(r"\bfirebase[_-]?app-check\b|firebaseappcheck", re.I)),

    # Webhooks/callbacks - more specific to avoid false positives from generic code comments
    ("Webhooks / callbacks (specific)", re.compile(r"\bwebhook\b.*(?:github|slack|stripe|zoom|twilio)\b|\bcallback[_-]?url\s*=\s*['\"]", re.I)),

    ("Environment variables", re.compile(r"getSystemSetting|server\.system\.environment|process\.env|os\.environ|getenv\s*\(", re.I)),
    ("API keys / secrets (names only)", re.compile(r"\bapi[_-]?key\b|secret[_-]?key|client[_-]?secret", re.I)),
]


def record_third_party(text: str, rel: str, hits: Dict[str, set]) -> None:
    for label, pattern in THIRD_PARTY_PATTERNS:
        if pattern.search(text):
            hits.setdefault(label, set()).add(rel)


TOKEN_SPLIT_RE = re.compile(r"[/\\\-_.]+")


def path_tokens(rel: str) -> set:
    """Whole tokens from a path, split on separators, so needles like 'test' or
    'db' match real path segments instead of substrings ('latest', 'feedback')."""
    return {t for t in TOKEN_SPLIT_RE.split(rel.lower()) if t}


def bucket_path(rel: str) -> List[str]:
    low = rel.lower()
    tokens = path_tokens(rel)
    buckets = []
    for bucket, needles in BUCKET_RULES:
        matched = False
        for n in needles:
            # Needles with separators (".cfc", ".github", "gitlab-ci", "server.json")
            # are specific enough for substring matching; bare words must match a
            # whole path token to avoid false positives.
            if ("." in n or "-" in n) and n in low:
                matched = True
            elif n in tokens:
                matched = True
        if matched:
            buckets.append(bucket)
    return buckets or ["other"]


def extract_cfc_methods(text: str) -> List[str]:
    names = set(CFFUNCTION_RE.findall(text))
    names.update(SCRIPT_FUNCTION_RE.findall(text))
    return sorted(n for n in names if n)


def likely_evidence_file(rel: str) -> bool:
    low = rel.lower()
    name = Path(low).name
    if name in EVIDENCE_NAMES:
        return True
    return any(part in low for part in ["route", "auth", "login", "permission", "session", "database", "db", "schema", "migration", "docker", "deploy", "ci", "workflow", "config", "settings"])


STACK_TEXT_OVERRIDE_TOKENS = [
    ("mssql", ["mssql", "sqlsrv", "sql server", "sqlserver", "pdo_sqlsrv", "jtds"]), ("mysql", ["mysql", "mysqli", "pdo_mysql", "mysqlconnector"]),
    ("postgresql", ["psycopg2", "pg8000", "postgres", "postgresql"]), ("mongodb", ["pymongo", "mongoose", "mongodb"]),
    ("redis", ["redis"]), ("sqlite", ["sqlite3", "sqlite"]), ("oracle-db", ["cx_oracle", "oracledb", "ojdbc"]),
    ("flask", ["flask"]), ("fastapi", ["fastapi"]), ("django", ["django"]), ("rails", ["rails"]),
    ("spring", ["spring-boot", "springframework"]), ("react", ['"react"', "'react'"]), ("vue", ['"vue"', "'vue'"]),
    ("angular", ["@angular/core"]), ("svelte", ["svelte"]), ("nextjs", ['"next"', "'next'"]), ("nuxt", ["nuxt"]),
    ("graphql", ["graphql"]), ("tailwindcss", ["tailwindcss"]), ("rabbitmq", ["rabbitmq", "amqplib", "pika"]),
    ("kafka", ["kafka"]), ("elasticsearch", ["elasticsearch"]),
]


def _atlas_ignore_patterns(repo: Path) -> List[str]:
    patterns: List[str] = []
    for rel in [".project-atlasignore", "project-atlas/.project-atlasignore"]:
        path = repo / rel
        if path.is_file():
            patterns.extend(line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip() and not line.lstrip().startswith("#"))
    return patterns


def discover_repository_files(repo: Path, max_files: int) -> Tuple[List[str], List[str], List[str], bool, str | None, str]:
    git = subprocess.run(["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, check=False)
    if git.returncode == 0 and git.stdout.strip() == "true":
        result = subprocess.run(["git", "-C", str(repo), "ls-files", "-c", "-o", "--exclude-standard", "-z"], capture_output=True, check=False)
        if result.returncode == 0:
            patterns = _atlas_ignore_patterns(repo)
            candidates = sorted({raw.decode("utf-8", errors="surrogateescape") for raw in result.stdout.split(b"\0") if raw})
            files, ignored = [], []
            truncated_at = None
            for rel in candidates:
                if should_ignore(rel, False, patterns) or is_secret_path(rel):
                    ignored.append(rel)
                    continue
                if len(files) >= max_files:
                    truncated_at = rel
                    break
                files.append(rel)
            dirs = sorted({parent.as_posix() for rel in files for parent in Path(rel).parents if parent.as_posix() != "."})
            return files, dirs, ignored, truncated_at is not None, truncated_at, "git"

    ignores = load_ignore_patterns(repo)
    files: List[str] = []
    dirs: List[str] = []
    ignored: List[str] = []
    truncated_at = None
    for root, dirnames, filenames in os.walk(repo, topdown=True):
        root_path = Path(root)
        kept_dirs = []
        for name in sorted(dirnames):
            rel = rel_posix(root_path / name, repo)
            if should_ignore(rel, True, ignores):
                ignored.append(rel + "/")
            else:
                kept_dirs.append(name)
                dirs.append(rel)
        dirnames[:] = kept_dirs
        for name in sorted(filenames):
            rel = rel_posix(root_path / name, repo)
            if should_ignore(rel, False, ignores) or is_secret_path(rel):
                ignored.append(rel)
                continue
            if len(files) >= max_files:
                truncated_at = rel
                dirnames[:] = []
                break
            files.append(rel)
        if truncated_at:
            break
    return files, dirs, ignored, truncated_at is not None, truncated_at, "filesystem"


def _load_scan_cache(repo: Path) -> Dict[str, Any]:
    path = repo / "project-atlas/.cache/scan-v3.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if data.get("version") == 3 else {"version": 3, "files": {}}
    except (OSError, json.JSONDecodeError):
        return {"version": 3, "files": {}}


def _cache_entry(rel: str, path: Path, digest: str) -> Dict[str, object]:
    result: Dict[str, object] = {"digest": digest, "third_party": [], "datasources": [], "stack_overrides": [], "evidence": None}
    if rel.lower().endswith(".cfc"):
        text, status = read_text_limited(path, max_bytes=500_000)
        hits: Dict[str, set] = {}
        if text:
            record_third_party(text, rel, hits)
        methods = extract_cfc_methods(text) if text else []
        result.update({
            "cfc": {"path": rel, "methods": methods, "status": status if methods else (status if status != "extracted" else "no methods found"), "role": infer_role(rel)},
            "datasources": sorted(set(DATASOURCE_RE.findall(text))) if text else [],
            "third_party": sorted(hits),
            "syntax": "tag" if text and CFCOMPONENT_TAG_RE.search(text[:4000]) else "script",
        })
    elif rel.lower().endswith(".cfm"):
        text, _status = read_text_limited(path, max_bytes=100_000)
        hits: Dict[str, set] = {}
        if text:
            record_third_party(text, rel, hits)
        result["third_party"] = sorted(hits)
    elif likely_evidence_file(rel):
        text, status = read_text_limited(path, max_bytes=80_000)
        hits: Dict[str, set] = {}
        if text:
            record_third_party(text, rel, hits)
        lowered = text.lower() if text else ""
        result.update({"evidence": status, "stack_overrides": [key for key, tokens in STACK_TEXT_OVERRIDE_TOKENS if any(token in lowered for token in tokens)], "third_party": sorted(hits)})
    return result


def scan_repository(repo: Path, max_files: int = 20000, write_cache: bool = False, restrict_paths: Iterable[str] = ()) -> Dict[str, object]:
    repo = Path(repo).resolve()
    manifest_at_scan, _manifest_error = load_manifest(repo)
    files, dirs, ignored, truncated, truncated_at, discovery = discover_repository_files(repo, max_files)
    buckets: Dict[str, List[str]] = {}
    for rel in files:
        for bucket in bucket_path(rel):
            buckets.setdefault(bucket, []).append(rel)
    app_files = [rel for rel in files if not rel.startswith("project-atlas/") and rel not in {"AGENTS.md", "CLAUDE.md"}]
    stack = detect_stack_from_paths(app_files)
    cache = _load_scan_cache(repo)
    old_entries = cache.get("files", {}) or {}
    new_entries: Dict[str, Any] = {}
    fingerprints: Dict[str, str] = {}
    evidence: Dict[str, str] = {}
    cfc_inventory: List[Dict[str, object]] = []
    stack_overrides: set = set()
    datasources: set = set()
    third_party_hits: Dict[str, set] = {}
    tag_syntax_count = 0
    script_syntax_count = 0
    cache_hits = 0
    cache_misses = 0
    restricted = set(restrict_paths)

    for rel in app_files:
        path = repo / rel
        previous = old_entries.get(rel, {})
        if restricted and rel not in restricted and previous.get("digest"):
            digest = previous["digest"]
            entry = previous
            cache_hits += 1
            fingerprints[rel] = digest
            new_entries[rel] = entry
            cfc = entry.get("cfc")
            if cfc:
                cfc_inventory.append(cfc)
                datasources.update(entry.get("datasources", []))
                if entry.get("syntax") == "tag": tag_syntax_count += 1
                else: script_syntax_count += 1
            if entry.get("evidence") is not None: evidence[rel] = entry["evidence"]
            stack_overrides.update(entry.get("stack_overrides", []))
            for label in entry.get("third_party", []): third_party_hits.setdefault(label, set()).add(rel)
            continue
        try:
            digest = content_digest(path.read_bytes())
        except OSError:
            continue
        fingerprints[rel] = digest
        if previous.get("digest") == digest:
            entry = previous
            cache_hits += 1
        else:
            entry = _cache_entry(rel, path, digest)
            cache_misses += 1
        new_entries[rel] = entry
        cfc = entry.get("cfc")
        if cfc:
            cfc_inventory.append(cfc)
            datasources.update(entry.get("datasources", []))
            if entry.get("syntax") == "tag": tag_syntax_count += 1
            else: script_syntax_count += 1
        if entry.get("evidence") is not None:
            evidence[rel] = entry["evidence"]
        stack_overrides.update(entry.get("stack_overrides", []))
        for label in entry.get("third_party", []):
            third_party_hits.setdefault(label, set()).add(rel)

    if write_cache:
        cache_path = repo / "project-atlas/.cache/scan-v3.json"
        atomic_write_text(cache_path, json.dumps({"version": 3, "files": new_entries}, indent=2, sort_keys=True) + "\n")

    # Path-based detection (detect_stack.py) misses frameworks/services that are only
    # named inside a manifest's content (e.g. "fastapi" as a line in requirements.txt).
    # These overrides reuse the evidence text already read above for that content.
    for key in stack_overrides:
        stack[key] = True

    if tag_syntax_count or script_syntax_count:
        cfc_syntax_summary = f"{script_syntax_count} script-syntax and {tag_syntax_count} tag-syntax `.cfc` components detected."
    else:
        cfc_syntax_summary = "Not analyzed."

    return {
        "repo": str(repo),
        "file_count": len(files),
        "dir_count": len(dirs),
        "files": files,
        "file_fingerprints": fingerprints,
        "truncated": truncated,
        "truncated_at": truncated_at,
        "dirs": dirs,
        "buckets": {k: sorted(v)[:200] for k, v in sorted(buckets.items())},
        "ignored_sample": sorted(ignored)[:200],
        "stack": stack,
        "evidence": evidence,
        "cfc_inventory": cfc_inventory,
        "cfm_pages": sorted(p for p in app_files if p.lower().endswith(".cfm")),
        "datasources": sorted(datasources),
        "cfc_syntax_summary": cfc_syntax_summary,
        "third_party_indicators": [
            {"service": label, "files": sorted(paths)[:8]}
            for label, paths in sorted(third_party_hits.items())
        ],
        "scan_cache": {"hits": cache_hits, "misses": cache_misses, "entries": len(new_entries)},
        "discovery": discovery,
        "restricted_paths": sorted(restricted),
        "manifest_fingerprint_at_scan": manifest_at_scan.get("repository_fingerprint") if manifest_at_scan else None,
    }


def infer_role(rel: str) -> str:
    low = rel.lower()
    if "controller" in low:
        return "controller"
    if "service" in low:
        return "service"
    if "model" in low:
        return "model"
    if "dao" in low or "repository" in low:
        return "data access"
    if "handler" in low:
        return "handler"
    if "auth" in low or "login" in low or "security" in low:
        return "auth/security"
    if Path(low).name == "application.cfc":
        return "application entry point"
    return "component"


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a repository for Project Atlas.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--max-files", type=int, default=20000)
    parser.add_argument("--output")
    parser.add_argument("--allow-partial-scan", action="store_true")
    args = parser.parse_args()
    data = scan_repository(Path(args.repo), max_files=args.max_files)
    if data.get("truncated") and not args.allow_partial_scan:
        data["status"] = "failed"
        data["error"] = "Repository scan truncated; increase --max-files or pass --allow-partial-scan."
    text = dump_json(data)
    if args.output:
        atomic_write_text(Path(args.output), text)
    else:
        print(text)
    return 1 if data.get("status") == "failed" else 0

if __name__ == "__main__":
    raise SystemExit(main())
