# Architecture

<!-- project-atlas:contract {"request flow":{"status":"pending","evidence":[],"note":""},"boundaries":{"status":"pending","evidence":[],"note":""}} -->

Generated: {{generated}}

<!-- CONTRACT: This file must answer: how does a request flow end-to-end, what
     layers exist, where does business logic live, and what are the module
     boundaries. During enrichment, replace candidate lists with confirmed
     statements and keep only load-bearing paths. -->

## Detected architecture shape

- CFML/Lucee application: {{cfml_detected}}
- PHP application: {{php_detected}}
- Node/JavaScript application: {{node_detected}}
- Python application: {{python_detected}}
- Database indicators: {{db_indicators}}

## Entry points
{{entry_points_list}}

## Request flow

Not yet documented. Describe the path from HTTP request to response (entry point → controller/page → service → data access → view).

## Application boundaries

### Controllers / routes / handlers
{{controllers_routes_handlers_list}}

### Services / data access / components
{{services_data_components_list}}
