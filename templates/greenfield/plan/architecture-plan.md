# Architecture Plan

<!-- project-atlas:contract {"request flow":{"status":"pending","evidence":[],"note":""},"boundaries":{"status":"pending","evidence":[],"note":""}} -->

## Request flow

Describe the intended path from request to response (entry point → controller/page → service → data access → view).

## Layers and boundaries

- Where does business logic live?
- What are the service boundaries (one service per business workflow)?

## Proposed directory layout

```text
/
```

## Shared infrastructure

- Layout templates, error handling, logging, configuration loading.

## Integration points

- External APIs, scheduled jobs, email, file storage.
