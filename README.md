# Pocket Agent

Pocket Agent is a local-first learning project for building an observable AI agent one
verified vertical slice at a time. The current Phase 0 foundation provides typed
configuration, deterministic runtime paths, a versioned SQLite/FTS5 database, and a
truthful `pocket doctor` command.

Pocket Agent does **not** call a model or run an agent loop yet. Provider adapters, tracing,
tools, memory services, RAG ingestion, the API, and the browser cockpit begin in Phase 1.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Optional: a running Ollama service when `POCKET_PROVIDER=ollama`

No Docker service or forced model download is required.

## Quickstart

```bash
git clone <repository-url> pocket-agent
cd pocket-agent
uv sync --group dev
POCKET_PROVIDER=ollama POCKET_MODEL=qwen3:1.7b uv run pocket doctor
```

The Ollama command succeeds only when the selected service is running. To exercise the
current non-Ollama configuration path without making a provider API call:

```bash
POCKET_PROVIDER=openai \
POCKET_MODEL=gpt-5 \
POCKET_API_KEY=your-key \
uv run pocket doctor
```

The cloud-provider check currently validates configuration presence only. It does not prove
network access, authentication, quota, model availability, or inference; those live probes
arrive with provider adapters in Phase 1.

Expected Phase 0 output includes `PASS` results for required local capabilities and `WARN`
results for the not-yet-implemented embedder and sandbox. Warnings are visible degradation
and exit `0`; required failures exit `1`.

Runtime state is created below `POCKET_HOME` (default `.pocket/`) and is ignored by Git.

## Quality gate

The release gate is deterministic, offline, and requires no provider key:

```bash
make gate
```

Useful focused commands:

```bash
make format
make lint
make test
make eval
```

## Implemented topic map

| Topic | Owner | Current behavior |
|---|---|---|
| Configuration | `pocket/config.py` | Typed `POCKET_*` settings and secret-safe loading |
| Runtime paths | `pocket/paths.py` | Pure path derivation plus explicit initialization |
| SQLite policy | `pocket/db/connect.py` | WAL, busy timeout, foreign keys, named rows |
| Schema/migrations | `pocket/db/schema.sql`, `pocket/db/migrate.py` | 20 base tables, schema versions, atomic migrations |
| Full-text search | `pocket/db/migrate.py` | External-content FTS5 indexes and synchronization triggers |
| Health reporting | `pocket/ops/health.py` | Structured checks, aggregation, remediation and exit status |
| CLI | `pocket/cli.py` | Doctor-only Phase 0 command tree |
| Tests | `tests/` | Unit and integration coverage |
| Starter evals | `evals/deterministic/` | Three offline Phase 0 acceptance scenarios |

## Design rules

1. Local-first: the default installation requires no Docker or background service.
2. Fail open, but never silently: optional failures degrade visibly.
3. Durable events before UI events: future browser state will come from SQLite spans.

See `CLAUDE.md` for contributor conventions. The detailed build and learning plans are
maintained locally and intentionally excluded from commits.
