# PostgreSQL — Phase 22A

## Version & Installation

```text
PostgreSQL: 16.4-alpine (Docker official image, pinned)
Container:  agent-postgres (separate from WeKnora's postgres)
Port:       127.0.0.1:5433 (loopback only)
Database:   agent_runtime
User:       agent
Password:   AGENT_PG_PASSWORD (env / WSL /tmp/agent_pg_cred; never committed)
Data:       Docker volume (agent-postgres-data)
```

## Connection

```python
from runtime.state.pg import PostgresStore
os.environ["AGENT_PG_PASSWORD"] = "<password>"
store = PostgresStore()
store.init_schema()  # idempotent
```

Or via DSN:
```python
store = PostgresStore(dsn="host=127.0.0.1 port=5433 "
                            "dbname=agent_runtime user=agent "
                            "password=<pw>")
```

## Health Check

```bash
docker exec agent-postgres pg_isready -U agent -d agent_runtime
# or: store.health() → True/False
```

## Backup

```bash
docker exec agent-postgres pg_dump -U agent agent_runtime > backup.sql
```

## Restore

```bash
docker exec -i agent-postgres psql -U agent agent_runtime < backup.sql
```

## Schema

See DATABASE_SCHEMA.md. Init is idempotent (CREATE TABLE IF NOT EXISTS).

## Python Driver

- psycopg2-binary 2.9.11 (installed on Windows Python, which runs
  the tests). The WSL Python also needs it for in-WSL access.
