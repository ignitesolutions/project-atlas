#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List

try:
    from utils import load_ignore_patterns, should_ignore, rel_posix, dump_json
except ImportError:
    from .utils import load_ignore_patterns, should_ignore, rel_posix, dump_json


def iter_files(repo: Path) -> Iterable[str]:
    ignores = load_ignore_patterns(repo)
    for path in repo.rglob("*"):
        rel = rel_posix(path, repo)
        if should_ignore(rel, path.is_dir(), ignores):
            if path.is_dir():
                continue
            continue
        if path.is_file():
            yield rel


TOKEN_SPLIT_RE = re.compile(r"[/\\\-_.]+")


def detect_stack_from_paths(paths: Iterable[str]) -> Dict[str, object]:
    files = list(paths)
    lower = [p.lower() for p in files]
    tokens = {t for p in lower for t in TOKEN_SPLIT_RE.split(p) if t}

    def any_name(*names: str) -> bool:
        names_l = {n.lower() for n in names}
        return any(Path(p).name.lower() in names_l for p in files)

    def any_suffix(*suffixes: str) -> bool:
        return any(p.endswith(s.lower()) for p in lower for s in suffixes)

    def any_contains(*parts: str) -> bool:
        return any(any(part.lower() in p for part in parts) for p in lower)

    def any_token(*names: str) -> bool:
        # Whole path-segment tokens only, so a file merely mentioning a database
        # in its name ("mysql-notes.md" still counts, but "notmysqlish" does not)
        # cannot trigger a platform file.
        return any(n.lower() in tokens for n in names)

    marker_names = {
        "Application.cfc", "Application.cfm", "box.json", "server.json",
        "composer.json", "artisan", "wp-config.php", "symfony.lock",
        "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
        "vite.config.js", "vite.config.ts", "next.config.js", "next.config.mjs", "next.config.ts",
        "nuxt.config.js", "nuxt.config.ts", "webpack.config.js", "angular.json",
        "tsconfig.json", "tailwind.config.js", "tailwind.config.ts", "tailwind.config.cjs",
        "pyproject.toml", "requirements.txt", "Pipfile", "poetry.lock", "manage.py", "app.py", "wsgi.py", "asgi.py",
        "Gemfile", "Rakefile", "config.ru",
        "pom.xml", "build.gradle", "build.gradle.kts",
        "application.properties", "application.yml", "application.yaml",
        "go.mod", "go.sum", "Cargo.toml", "Cargo.lock", "mix.exs",
        "Dockerfile", "docker-compose.yml", "compose.yml",
        "Chart.yaml", "kustomization.yaml", "serverless.yml", "serverless.yaml", "template.yaml",
    }

    stack = {
        # Languages / runtimes
        "cfml": any_suffix(".cfm", ".cfc") or any_name("Application.cfc", "Application.cfm", "box.json", "server.json"),
        "php": any_suffix(".php") or any_name("composer.json", "artisan", "wp-config.php"),
        "node-js": any_name("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "vite.config.js", "next.config.js", "nuxt.config.js", "webpack.config.js"),
        "typescript": any_name("tsconfig.json") or any_suffix(".ts", ".tsx"),
        "python": any_name("pyproject.toml", "requirements.txt", "Pipfile", "poetry.lock", "manage.py", "app.py", "wsgi.py", "asgi.py"),
        "ruby": any_name("Gemfile", "Rakefile"),
        "java": any_name("pom.xml", "build.gradle", "build.gradle.kts"),
        "dotnet": any_suffix(".csproj", ".sln") or any_name("Program.cs", "Startup.cs"),
        "go": any_name("go.mod", "go.sum"),
        "rust": any_name("Cargo.toml", "Cargo.lock"),
        "elixir": any_name("mix.exs"),

        # CI/CD pipelines
        "github-actions": any_contains(".github/workflows/", ".github/workflow.yml", "action.yml"),
        "gitlab-ci": any_name(".gitlab-ci.yml", "gitlab/ci.yml", ".ci/gitlab-ci.yml"),
        "jenkins": any_name("Jenkinsfile", "config.xml") or any_contains("Jenkinsfile", "jobs/"),
        "circleci": any_name(".circleci/config.yml", "circleci-config.yml"),
        "azure-pipelines": any_name("azure-pipelines.yml", "azdo.yaml"),

        # Testing frameworks
        "jest": any_name("jest.config.js", "jest.config.ts", "jest.config.mjs") or any_contains("__tests__", "__test__"),
        "playwright": any_name("playwright.config.js", "playwright.config.ts", "playwright.config.mjs"),
        "cypress": any_name("cypress.config.js", "cypress.config.ts") or any_contains("cypress/", "cypress/plugins/"),
        "vitest": any_name("vitest.config.js", "vitest.config.ts") or any_suffix(".vitest.*"),
        "mocha": any_name(".mocharc.yml", ".mocharc.yaml", "mocha.opts"),

        # CSS Preprocessing
        "sass": any_suffix(".scss") or any_contains("node_modules/sass/", "package.json", "sass"),
        "less": any_suffix(".less") or any_contains("node_modules/less/", "package.json", "less"),
        "postcss": any_name("postcss.config.js", "postcss.config.cjs") or any_contains("package.json", "postcss"),

        # Backend frameworks / CMS
        "laravel": any_name("artisan"),
        "symfony": any_name("symfony.lock") or any_contains("config/bundles.php"),
        "wordpress": any_name("wp-config.php") or any_contains("wp-content/", "wp-admin/"),
        "drupal": any_contains("sites/default/settings.php") or any_token("drupal"),
        "rails": any_name("config.ru") or any_contains("bin/rails", "config/routes.rb"),
        "spring": any_name("application.properties", "application.yml", "application.yaml"),
        "django": any_name("manage.py") or any_contains("wsgi.py", "asgi.py"),
        "flask": any_token("flask"),
        "fastapi": any_token("fastapi"),
        "phoenix": any_contains("_web/endpoint.ex", "_web/router.ex"),

        # Frontend frameworks
        "react": any_suffix(".jsx", ".tsx"),
        "vue": any_suffix(".vue") or any_name("vue.config.js"),
        "angular": any_name("angular.json"),
        "svelte": any_suffix(".svelte") or any_name("svelte.config.js"),
        "nextjs": any_name("next.config.js", "next.config.mjs", "next.config.ts"),
        "nuxt": any_name("nuxt.config.js", "nuxt.config.ts"),
        "tailwindcss": any_name("tailwind.config.js", "tailwind.config.ts", "tailwind.config.cjs"),
        "graphql": any_suffix(".graphql", ".gql") or any_name("schema.graphql"),

        # Databases
        "mysql": any_token("mysql", "mysqli", "mysqlconnector", "mariadb"),
        "mssql": any_token("mssql", "sqlserver", "sqlsrv", "jtds"),
        "postgresql": any_token("postgres", "postgresql", "psql", "psycopg2", "pg8000"),
        "mongodb": any_token("mongodb", "mongoose", "mongo"),
        "redis": any_token("redis"),
        "sqlite": any_suffix(".sqlite", ".sqlite3") or any_token("sqlite"),
        "oracle-db": any_token("oracle", "oradata", "ojdbc"),

        # Infrastructure / deployment
        "docker": any_name("Dockerfile", "docker-compose.yml", "compose.yml", ".dockerignore") or any_contains("docker/") or any_name(".containerfiles/*"),
        "kubernetes": any_name("Chart.yaml", "kustomization.yaml") or any_contains("k8s/", "kubernetes/") or any_token("kubernetes"),
        "terraform": any_suffix(".tf", ".tfvars") or any_name("terraform.tfstate"),
        "serverless": any_name("serverless.yml", "serverless.yaml", "template.yaml", "sam.yaml"),
        "rabbitmq": any_token("rabbitmq", "amqp"),
        "kafka": any_token("kafka"),
        "elasticsearch": any_token("elasticsearch", "elastic"),

        # CFML Frameworks (Lucee / Railo)
        "lucee": any_name("lucee.cfg", "lucee.ini") or any_contains("box.json", "server.json", "lucee"),
        "railo": any_token("coldfusion.railo") or any_name("railo.cfg", "railo.ini"),

        "markers": sorted([p for p in files if Path(p).name in marker_names]),
    }
    return stack


def detect_stack(repo: Path) -> Dict[str, object]:
    return detect_stack_from_paths(iter_files(repo))


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect Project Atlas repository stack.")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    print(dump_json(detect_stack(repo)))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())