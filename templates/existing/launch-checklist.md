# Launch Checklist

<!-- One paragraph describing launch readiness state. This file accumulates during development:
     every time work introduces something that differs between dev, stage, and live, add an item
     here immediately — do not wait for launch planning. -->

Everything that must be done, changed, or verified when this project moves to the LIVE environment. Add items as development happens; check them off during launch.

**Item format:** `- [ ] Item — environment(s) affected — where it is configured — who/what does it (agent, developer, DBA, vendor dashboard)`

## Evidence from bootstrap scan

<!-- CONTRACT: During enrichment, open each candidate below and convert every real
     dev/stage/live difference into a checklist item in the sections that follow —
     or an explicit question when unconfirmed. Remove entries that turn out to be
     irrelevant; this section should shrink as the checklist sections grow. -->

### Candidate config / environment files

{{launch_config_candidates_list}}

### Third-party service and environment indicators

{{third_party_indicators_list}}

## Environment configuration

<!-- Env vars, config files, application settings, feature flags, debug/error-display settings,
     datasource names, mail server settings — anything whose VALUE differs between dev, stage,
     and live. Name the variable/setting and where it lives. Never record secret values
     (passwords, keys, tokens, connection strings) — names, locations, and access patterns
     only. -->

- [ ] none recorded yet

## Keys, credentials, and certificates

<!-- API keys, signing keys, OAuth client IDs, SSL/TLS certificates that need live values or
     rotation at launch. Names and locations only — never the values themselves. -->

- [ ] none recorded yet

## Folders, files, and permissions

<!-- Upload/temp/log directories that must exist on the live server, filesystem permissions,
     scheduled task (cron/cfschedule) registrations, web server or vhost config differences. -->

- [ ] none recorded yet

## Database

<!-- Schema migrations or SQL scripts pending against live, seed/lookup data to load,
     datasource setup, jobs or agents to enable. Link the SQL files by path. -->

- [ ] none recorded yet

## Third-party services

<!-- Per service (Stripe, Authorize.net, mail provider, external APIs, webhooks, DNS/CDN):
     switch test/sandbox mode to live, live keys, webhook/callback URLs pointing at the live
     domain, account or plan setup, allowed-origin/IP allowlists. -->

- [ ] none recorded yet

## Verification after launch

<!-- What to check once live: critical workflows to exercise, logs to watch, payments/emails
     to confirm end-to-end. -->

- [ ] none recorded yet
