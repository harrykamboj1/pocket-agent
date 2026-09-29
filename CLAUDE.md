# Pocket Agent Working Conventions

## Product rules

1. Keep the default path local-first: no Docker, forced downloads, accounts, or network.
2. Fail open only for optional capabilities, and always expose the degradation through a
   health result, finding, span, or user-visible message.
3. A future browser event must first exist as a durable row in `spans`; never create a direct
   graph-node-to-browser shortcut.
4. Keep third-party libraries behind Pocket-owned functions, dataclasses, and protocols.
5. State what is implemented separately from what is planned.

## Development workflow

- Build one thin behavior with its test before expanding the surface area.
- Run `make gate` before every product-code commit.
- Keep the gate offline, deterministic, and independent of API keys or local services.
- Add a deterministic regression case for every fixed bug.
- Prefer explicit paths when staging; never use `git add .` in this repository.
- Never commit `.env`, `.pocket/`, `.venv/`, `dist/`, caches, secrets, or runtime databases.
- `BUILD_PLAN.md`, `LEARNING_ROADMAP.md`, and `LEARNING_PROGRESS.md` are local learning files;
  update them at session boundaries but do not stage or push them.

## Python conventions

- Support Python 3.11 and newer.
- Use type annotations at subsystem boundaries.
- Separate pure derivation from filesystem, network, database, and terminal side effects.
- Close database and network resources on success and failure.
- Return structured results from domain logic; render them only at interface boundaries.
- Do not include secrets in messages, representations, logs, reports, or fixtures that mimic
  real credentials.

## Commands

```bash
make format   # apply Ruff formatting and safe lint fixes
make lint     # formatting and static checks
make test     # unit/integration tests
make eval     # deterministic acceptance evals
make gate     # complete offline release gate
```

Keep user-facing terminal and UI copy concise. Do not use emojis as status indicators;
status must remain understandable in plain text and assistive technology.
