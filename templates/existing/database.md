# Database

## Detected database indicators

- MySQL: {{mysql_detected}}
- MSSQL: {{mssql_detected}}
- PostgreSQL: {{postgresql_detected}}
- MongoDB: {{mongodb_detected}}
- Redis: {{redis_detected}}
- Oracle: {{oracle_db_detected}}

## Datasources

{{datasources_list}}

## Candidate database files
{{database_candidates_list}}

<!-- CONTRACT: Record datasource names, where queries live, schema and migration
     locations, and query conventions (e.g. queryExecute with named parameters). -->

## Secret handling

Never record secret values (passwords, keys, tokens, connection strings) — names, locations, and access patterns only.
