# Known Risks

<!-- CONTRACT: List fragile, security-sensitive, or data-sensitive areas with
     the paths involved and why they are risky. -->

## Current risks

- Automated Atlas generation is based on static repository inspection.
- Review generated summaries before relying on them for production changes.
- Never record secret values (passwords, keys, tokens, connection strings) — names, locations, and access patterns only.
