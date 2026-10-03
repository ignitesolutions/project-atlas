# Platform Detection Guidance

Markers used to decide which `project-atlas/platforms/*.md` files to create. Authoritative implementation: `scripts/detect_stack.py`.

| Platform | Markers |
| --- | --- |
| cfml | `.cfm`, `.cfc` files; `Application.cfc`, `Application.cfm`, `box.json`, `server.json` |
| php | `.php` files; `composer.json`, `artisan`, `wp-config.php` |
| node-js | `package.json`, lockfiles (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`); Vite/Next/Nuxt/Webpack config |
| python | `pyproject.toml`, `requirements.txt`, `Pipfile`, `poetry.lock`, `manage.py`, `app.py`, `wsgi.py`, `asgi.py` |
| docker | `Dockerfile`, compose files, `.dockerignore`, `docker/` directories |
| mysql | path tokens `mysql`/`mysqli`/`mysqlconnector`; evidence-file text mentioning mysql/mysqli/pdo_mysql |
| mssql | path tokens `mssql`/`sqlserver`/`sqlsrv`/`jtds`; evidence-file text mentioning mssql/sqlsrv/sql server/pdo_sqlsrv/jtds |
| postgresql | path tokens `postgres`/`postgresql`/`psql`/`psycopg2`/`pg8000` |
| mongodb | path tokens `mongodb`/`mongoose`/`mongo` |
| redis | path token `redis` |
| oracle-db | path tokens `oracle`/`oradata`/`ojdbc` |
| ci_cd | any of: `.github/workflows/` (GitHub Actions), `.gitlab-ci.yml` (GitLab CI), `Jenkinsfile` (Jenkins), `.circleci/config.yml` (CircleCI), `azure-pipelines.yml` (Azure Pipelines) |
| testing | any of: `jest.config.*`/`__tests__`/`__test__` (Jest), `playwright.config.*` (Playwright), `cypress.config.*`/`cypress/` (Cypress), `vitest.config.*` (Vitest), `.mocharc.*`/`mocha.opts` (Mocha) |

Notes:

- Path-based database detection uses whole path tokens (segments split on `/`, `-`, `_`, `.`), so a file that merely contains the letters does not trigger a platform. Text found inside evidence files (config, database code) is the stronger signal.
- CFML repositories additionally get: full `.cfc` method inventory (both `<cffunction>` tag syntax and script `function` declarations), a `.cfm` page list, datasource names (names only), and tag-vs-script component syntax counts.
- `ci_cd` and `testing` are each a union of several individual `detect_stack.py` flags (see `scripts/utils.py`'s `CI_CD_STACK_KEYS` / `TESTING_STACK_KEYS`) — the platform file is created when any one of the underlying tools is detected, without identifying which specific tool triggered it beyond what's visible in `stack.md`'s detection table.
- Other platforms not listed here never get a platform file just to explain a false positive — note those in `stack.md` or `open-questions.md`.
- Platform files are conditional evidence views, not part of the compact required core. The canonical platform list and freshness metadata live in `atlas.json`.
- Git repositories discover tracked and eligible untracked files through `git ls-files`; Git applies `.gitignore`, while `.project-atlasignore` supplies Atlas-specific exclusions. Non-Git repositories use a standard-library glob fallback with less complete Git-ignore semantics.
