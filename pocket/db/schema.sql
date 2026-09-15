-- Conversation sessions group related turns.
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT NOT NULL PRIMARY KEY,
    title TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
-- A turn represents one complete user-to-agent interaction.
CREATE TABLE IF NOT EXISTS turns (
    id TEXT NOT NULL PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN (
            'pending',
            'running',
            'awaiting_approval',
            'completed',
            'failed'
        )
    ),
    iterations INTEGER NOT NULL DEFAULT 0 CHECK (iterations >= 0),
    latency_ms INTEGER CHECK (
        latency_ms is NULL
        or latency_ms >= 0
    ),
    gate_retrieved INTEGER NOT NULL DEFAULT 0 CHECK (gate_retrieved IN (0, 1)),
    gate_failed_open INTEGER NOT NULL DEFAULT 0 CHECK (gate_failed_open IN (0, 1)),
    tokens INTEGER NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    provider TEXT,
    model TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    completed_at TEXT,
    UNIQUE (session_id, id),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
-- The durable product record of messages exchanged during a turn.
CREATE TABLE IF NOT EXISTS chat_log (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant', 'tool')),
    content TEXT NOT NULL,
    consolidated INTEGER NOT NULL DEFAULT 0 CHECK (consolidated IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'cli',
    meta TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(meta)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (session_id, turn_id) REFERENCES turns(session_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_turns_session_created ON turns(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_log_session_id ON chat_log(session_id, id);
CREATE INDEX IF NOT EXISTS idx_chat_log_turn_id ON chat_log(turn_id, id);
-- Semantic memory: durable facts learned about people, projects, and preferences.
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY,
    subject TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'user',
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (
        confidence >= 0.0
        AND confidence <= 1.0
    ),
    turn_id TEXT,
    superseded_by INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (
        superseded_by IS NULL
        OR superseded_by <> id
    ),
    FOREIGN KEY (turn_id) REFERENCES turns(id) ON DELETE
    SET NULL,
        FOREIGN KEY (superseded_by) REFERENCES facts(id) ON DELETE
    SET NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_subject_active ON facts(subject, id)
WHERE superseded_by IS NULL;
CREATE INDEX IF NOT EXISTS idx_facts_turn_id ON facts(turn_id);
-- Episodic memory: durable summaries of events and prior interactions.
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY,
    happened_at TEXT NOT NULL,
    summary TEXT NOT NULL,
    session_id TEXT,
    turn_span TEXT NOT NULL DEFAULT '[]' CHECK (
        json_valid(turn_span)
        AND json_type(turn_span) = 'array'
    ),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE
    SET NULL
);
CREATE INDEX IF NOT EXISTS idx_episodes_happened_at ON episodes(happened_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_session_id ON episodes(session_id);
-- Procedural memory telemetry: records when an installed skill was used.
CREATE TABLE IF NOT EXISTS skill_uses (
    id INTEGER PRIMARY KEY,
    skill_name TEXT NOT NULL,
    session_id TEXT,
    turn_id TEXT,
    tokens_loaded INTEGER NOT NULL DEFAULT 0 CHECK (tokens_loaded >= 0),
    used_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE
    SET NULL,
        FOREIGN KEY (turn_id) REFERENCES turns(id) ON DELETE
    SET NULL
);
CREATE INDEX IF NOT EXISTS idx_skill_uses_name_time ON skill_uses(skill_name, used_at);
CREATE INDEX IF NOT EXISTS idx_skill_uses_turn_id ON skill_uses(turn_id);
-- A document is one source imported into the RAG system.
-- source - identifies the original url or file
-- collection - group docuements
-- content_hash - used to detect if the document has changed since last import
-- mtime_ns - supports fast file change detection
-- meta - arbitrary JSON metadata about the document
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    collection TEXT NOT NULL DEFAULT 'default',
    source TEXT NOT NULL,
    title TEXT,
    content_hash TEXT NOT NULL,
    mtime_ns INTEGER,
    meta TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(meta)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (collection, source)
);
CREATE INDEX IF NOT EXISTS idx_documents_collection ON documents(collection, id);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
-- Search operates on smaller document chunks instead of whole documents.
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL,
    ord INTEGER NOT NULL CHECK (ord >= 0),
    text TEXT NOT NULL,
    heading TEXT,
    embedded INTEGER NOT NULL DEFAULT 0 CHECK (embedded IN (0, 1)),
    meta TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(meta)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (doc_id, ord),
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chunks_unembedded ON chunks(doc_id, id)
WHERE embedded = 0;
-- Optional vector representation of a document chunk.
CREATE TABLE IF NOT EXISTS vectors (
    chunk_id INTEGER NOT NULL,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL CHECK (dim > 0),
    norm REAL NOT NULL CHECK (norm > 0),
    vec BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (chunk_id, model),
    FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_vectors_model_dim ON vectors(model, dim, chunk_id);
-- Optional embeddings for semantic-memory facts.
-- Embeddings remain separate from facts because Pocket must still work when no embedding provider is available.
CREATE TABLE IF NOT EXISTS fact_vectors (
    fact_id INTEGER NOT NULL,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL CHECK (dim > 0),
    norm REAL NOT NULL CHECK (norm > 0),
    vec BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (fact_id, model),
    FOREIGN KEY (fact_id) REFERENCES facts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_fact_vectors_model_dim ON fact_vectors(model, dim, fact_id);
-- Reuses embeddings when identical content is encountered again.
CREATE TABLE IF NOT EXISTS embed_cache (
    content_hash TEXT NOT NULL,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL CHECK (dim > 0),
    norm REAL NOT NULL CHECK (norm > 0),
    vec BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (content_hash, model)
);
-- id         Database event number and UI replay cursor
-- span_id    Logical operation identifier
-- parent_id  Parent operation, used to construct a trace tree
-- kind       Type: model, tool, gate, retrieval, error, etc.
-- name       Specific operation: retrieval_gate, call_openai, now_tool
-- phase      start, end, or another lifecycle phase
-- status     ok, error, interrupted, etc.
-- dur_ms     Operation duration in milliseconds
-- attrs      Flexible structured event details
-- error      Human-readable error information
-- Durable trace events. The integer id is also the UI/SSE replay cursor.
CREATE TABLE IF NOT EXISTS spans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    span_id TEXT NOT NULL,
    parent_id TEXT,
    session_id TEXT,
    turn_id TEXT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    phase TEXT NOT NULL DEFAULT 'end',
    status TEXT NOT NULL DEFAULT 'ok',
    dur_ms INTEGER CHECK (
        dur_ms IS NULL
        OR dur_ms >= 0
    ),
    attrs TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(attrs)),
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id, turn_id) REFERENCES turns(session_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_spans_turn_cursor ON spans(turn_id, id);
CREATE INDEX IF NOT EXISTS idx_spans_session_cursor ON spans(session_id, id);
CREATE INDEX IF NOT EXISTS idx_spans_kind_cursor ON spans(kind, id);
CREATE INDEX IF NOT EXISTS idx_spans_span_cursor ON spans(span_id, id);
CREATE INDEX IF NOT EXISTS idx_spans_parent_cursor ON spans(parent_id, id);
-- Append-only model token usage. Monetary cost is derived elsewhere.
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    turn_id TEXT,
    role TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    cached_tokens INTEGER NOT NULL DEFAULT 0 CHECK (cached_tokens >= 0),
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_usage_turn_cursor ON usage(turn_id, id);
CREATE INDEX IF NOT EXISTS idx_usage_model_cursor ON usage(provider, model, id);
-- Problems and degradations discovered during execution or diagnosis.
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    turn_id TEXT,
    span_id TEXT,
    code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error')),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'ignored')),
    message TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(evidence)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_findings_turn_cursor ON findings(turn_id, id);
CREATE INDEX IF NOT EXISTS idx_findings_code_status ON findings(code, status, id);
-- Durable record of tool actions requiring user approval.
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(arguments)),
    risk TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN (
            'pending',
            'approved',
            'denied',
            'expired'
        )
    ),
    requested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    decided_at TEXT,
    decision_reason TEXT,
    FOREIGN KEY (session_id, turn_id) REFERENCES turns(session_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_approvals_turn_status ON approvals(turn_id, status, id);
-- One complete execution of an evaluation suite.
CREATE TABLE IF NOT EXISTS eval_runs (
    id TEXT NOT NULL PRIMARY KEY,
    suite TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running' CHECK (
        status IN (
            'running',
            'passed',
            'failed',
            'error'
        )
    ),
    summary TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(summary)),
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    completed_at TEXT
);
-- Individual test cases belonging to an evaluation run.
CREATE TABLE IF NOT EXISTS eval_cases (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    case_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'passed',
            'failed',
            'error',
            'skipped'
        )
    ),
    score REAL CHECK (
        score IS NULL
        OR (
            score >= 0.0
            AND score <= 1.0
        )
    ),
    duration_ms INTEGER CHECK (
        duration_ms IS NULL
        OR duration_ms >= 0
    ),
    details TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(details)),
    UNIQUE (run_id, case_name),
    FOREIGN KEY (run_id) REFERENCES eval_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_eval_cases_run_status ON eval_cases(run_id, status, id);
-- Cached results from probing a provider/model combination.
CREATE TABLE IF NOT EXISTS provider_capabilities (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    tool_calling INTEGER CHECK (
        tool_calling IS NULL
        OR tool_calling IN (0, 1)
    ),
    json_mode INTEGER CHECK (
        json_mode IS NULL
        OR json_mode IN (0, 1)
    ),
    embeddings INTEGER CHECK (
        embeddings IS NULL
        OR embeddings IN (0, 1)
    ),
    details TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(details)),
    error TEXT,
    checked_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (provider, model)
);
-- Runtime-managed non-secret settings and feature state.
CREATE TABLE IF NOT EXISTS settings_kv (
    setting_key TEXT NOT NULL PRIMARY KEY,
    value_json TEXT NOT NULL CHECK (json_valid(value_json)),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
-- Records database migrations that have been applied.
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL PRIMARY KEY CHECK (version > 0),
    name TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);