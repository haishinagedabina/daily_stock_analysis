# Board Membership Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist stock-to-board relationships locally so OpenClaw hot-theme screening can read board data in bulk from the database instead of resolving boards one stock at a time during each run.

**Architecture:** Add a normalized board persistence layer with `board_master` and `instrument_board_membership`, populate it with a dedicated backfill script, and change `FactorService` to use a local-first board lookup with remote fallback only for missing symbols. Keep `instrument_master` focused on stock master data and treat board membership as a separate many-to-many dataset.

**Tech Stack:** Python, SQLAlchemy, SQLite inline migrations, FastAPI service layer, pytest

---

## File Map

### Storage and schema
- Modify: `src/storage.py`
- Reference: `src/services/universe_service.py`
- Reference: `src/services/factor_service.py`

### Board persistence and sync
- Create: `src/repositories/board_repository.py`
- Create: `src/services/board_sync_service.py`
- Create: `scripts/backfill_instrument_boards.py`
- Reference: `data_provider/base.py`
- Reference: `data_provider/efinance_fetcher.py`

### Screening integration
- Modify: `src/services/factor_service.py`

### Tests
- Create: `tests/test_board_storage.py`
- Create: `tests/test_board_repository.py`
- Create: `tests/test_board_sync_service.py`
- Modify: `tests/test_factor_service.py`
- Optional: `tests/test_backfill_instrument_boards.py`

### Docs
- Modify: `README.md`
- Modify: `docs/CHANGELOG.md`

## Constraints and Guardrails

- Use TDD for every behavior change: failing test first, then minimal implementation.
- Do not overload `stock_daily` or `instrument_master` with denormalized board membership payloads.
- Keep the new schema additive-only and compatible with existing SQLite databases via inline migration.
- Keep remote board fetching off the hot path as much as possible.
- Only fetch remote board data for missing symbols, and write successful fallback results back to the local store.
- Do not attempt historical board-version tracking in this phase.
- Do not commit unless the human explicitly asks for it.

## Task 1: Add Board Persistence Schema

**Outcome:** The database can permanently store boards and stock-board relationships in normalized tables.

**Files:**
- Modify: `src/storage.py`
- Create: `tests/test_board_storage.py`

- [ ] **Step 1: Write the failing storage test for the new tables**

Cover:
- `board_master` table exists
- `instrument_board_membership` table exists
- uniqueness rules prevent duplicate relationships

Suggested test shape:

```python
def test_inline_migration_adds_board_tables(tmp_path):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'boards.db'}")
    tables = inspect(db.engine).get_table_names()
    assert "board_master" in tables
    assert "instrument_board_membership" in tables
```

- [ ] **Step 2: Run the focused storage test and verify it fails**

Run:

```bash
python -m pytest tests/test_board_storage.py -q
```

Expected before the fix:
- missing ORM models or missing inline migration support

- [ ] **Step 3: Add ORM models**

In `src/storage.py`, add:
- `BoardMaster`
- `InstrumentBoardMembership`

Required fields:
- `BoardMaster`: `board_code`, `board_name`, `board_type`, `market`, `source`, `is_active`, timestamps
- `InstrumentBoardMembership`: `instrument_code`, `board_id`, `market`, `source`, `is_primary`, timestamps

- [ ] **Step 4: Add indexes and uniqueness constraints**

Required constraints:
- unique board identity by `(market, source, board_name, board_type)`
- unique membership by `(instrument_code, board_id, source)`

- [ ] **Step 5: Add inline SQLite migration**

Extend `_apply_inline_migrations()` in `src/storage.py` with additive-only migration helpers that create the two new tables when missing.

- [ ] **Step 6: Re-run storage tests and confirm green**

Run:

```bash
python -m pytest tests/test_board_storage.py -q
python -m py_compile src/storage.py
```

- [ ] **Step 7: Checkpoint**

Record:
- schema is additive-only
- existing DBs can self-upgrade on startup

## Task 2: Add Board CRUD and Batch Lookup

**Outcome:** The application can upsert board metadata, upsert memberships, and bulk-read board names for a list of stock codes.

**Files:**
- Modify: `src/storage.py`
- Create: `src/repositories/board_repository.py`
- Create: `tests/test_board_repository.py`

- [ ] **Step 1: Write the failing repository tests**

Cover:
- upsert boards
- upsert memberships
- batch lookup `code -> [board names]`
- duplicate writes do not create duplicate rows

Suggested test shape:

```python
def test_batch_get_board_names_by_codes_returns_mapping(repo):
    repo.upsert_board_memberships(...)
    mapping = repo.batch_get_board_names_by_codes(["600519", "300750"])
    assert mapping["600519"] == ["白酒", "消费"]
```

- [ ] **Step 2: Run repository tests and verify failure**

Run:

```bash
python -m pytest tests/test_board_repository.py -q
```

- [ ] **Step 3: Add storage-level helpers**

Add methods in `src/storage.py`:
- `upsert_boards(...)`
- `replace_instrument_board_memberships(...)`
- `batch_get_instrument_board_names(codes, market="cn")`
- optional `list_instrument_board_memberships(...)`

- [ ] **Step 4: Add repository wrapper**

Create `src/repositories/board_repository.py` to keep board-specific reads and writes out of `FactorService`.

- [ ] **Step 5: Re-run repository tests**

Run:

```bash
python -m pytest tests/test_board_repository.py -q
python -m py_compile src/storage.py src/repositories/board_repository.py
```

- [ ] **Step 6: Checkpoint**

Record:
- board persistence and lookup are available without touching runtime screening logic yet

## Task 3: Add Board Sync Service

**Outcome:** There is a reusable service that can fetch, normalize, and persist board memberships for selected symbols or the active universe.

**Files:**
- Create: `src/services/board_sync_service.py`
- Create: `tests/test_board_sync_service.py`
- Reference: `data_provider/base.py`
- Reference: `src/services/universe_service.py`

- [ ] **Step 1: Write the failing service tests**

Cover:
- sync by explicit `codes`
- sync from active `instrument_master` universe
- normalize board payloads from `DataFetcherManager.get_belong_boards`
- persist results through `BoardRepository`

- [ ] **Step 2: Run the focused sync-service tests and verify failure**

Run:

```bash
python -m pytest tests/test_board_sync_service.py -q
```

- [ ] **Step 3: Implement `BoardSyncService`**

Responsibilities:
- resolve target codes from explicit codes or active instruments
- call `DataFetcherManager.get_belong_boards(code)`
- normalize board names and types
- upsert board rows
- replace memberships for each symbol
- return summary counts: `processed`, `synced`, `missing`, `failed`

- [ ] **Step 4: Add normalization helper**

Standardize:
- board name aliases
- board type aliases
- duplicate rows within a single fetch result

- [ ] **Step 5: Re-run service tests**

Run:

```bash
python -m pytest tests/test_board_sync_service.py -q
python -m py_compile src/services/board_sync_service.py
```

- [ ] **Step 6: Checkpoint**

Record:
- there is now one reusable entry point for board backfill and runtime fallback writes

## Task 4: Add Offline Board Backfill Script

**Outcome:** Operators can prefill local board memberships before screening jobs run.

**Files:**
- Create: `scripts/backfill_instrument_boards.py`
- Optional: `tests/test_backfill_instrument_boards.py`
- Reference: `scripts/fast_backfill.py`

- [ ] **Step 1: Write the failing CLI test or dry-run smoke test**

Cover:
- `--dry-run`
- `--codes`
- `--limit`
- `--stale-only` placeholder behavior if implemented in phase 1

- [ ] **Step 2: Run the script test or dry-run validation and confirm failure**

Run one of:

```bash
python -m pytest tests/test_backfill_instrument_boards.py -q
```

or

```bash
python scripts/backfill_instrument_boards.py --dry-run --limit 10
```

- [ ] **Step 3: Implement the script**

Recommended arguments:
- `--codes`
- `--limit`
- `--offset`
- `--dry-run`
- `--source`
- `--sleep-seconds`
- `--retry`

The script should:
- instantiate `BoardSyncService`
- resolve target codes
- print summary stats
- avoid writes in dry-run mode

- [ ] **Step 4: Add operational logging**

Log:
- total target count
- processed count
- synced count
- failed count
- elapsed time

- [ ] **Step 5: Re-run the script validation**

Run:

```bash
python scripts/backfill_instrument_boards.py --dry-run --limit 10
python -m py_compile scripts/backfill_instrument_boards.py
```

- [ ] **Step 6: Checkpoint**

Record:
- board data can now be preloaded offline instead of only during screening

## Task 5: Make FactorService Use Local-First Board Lookup

**Outcome:** Screening reads board data in bulk from the local DB and only falls back to remote fetches for missing symbols.

**Files:**
- Modify: `src/services/factor_service.py`
- Modify: `tests/test_factor_service.py`
- Reference: `src/repositories/board_repository.py`
- Reference: `src/services/board_sync_service.py`

- [ ] **Step 1: Write the failing factor-service tests**

Cover:
- local board lookup is used first
- remote fetch is skipped when local data exists
- only missing codes hit remote fallback
- fallback writes are persisted for future runs

Suggested test shape:

```python
def test_build_factor_snapshot_prefers_local_board_membership(...):
    ...
    assert fetcher_manager.get_belong_boards.call_count == 0
```

- [ ] **Step 2: Run factor-service tests and verify failure**

Run:

```bash
python -m pytest tests/test_factor_service.py -q
```

- [ ] **Step 3: Refactor board resolution in `FactorService`**

Replace the current per-code remote path with:
- bulk local load from `BoardRepository`
- compute `missing_codes`
- remote fetch only for missing codes
- persist successful fallback results via `BoardSyncService` or repository helpers

- [ ] **Step 4: Keep the output contract unchanged**

`HotThemeFactorEnricher.enrich_snapshot(..., boards=[...])` should still receive a `List[str]` of board names for each symbol.

- [ ] **Step 5: Re-run factor-service tests**

Run:

```bash
python -m pytest tests/test_factor_service.py -q
python -m py_compile src/services/factor_service.py
```

- [ ] **Step 6: Checkpoint**

Record:
- local board cache is now on the main screening path
- remote board fetching is downgraded to a sparse fallback path

## Task 6: Add Minimal Observability and Docs

**Outcome:** The new capability is documented and operational behavior is observable.

**Files:**
- Modify: `README.md`
- Modify: `docs/CHANGELOG.md`
- Optional: `docs/openclaw-api-integration.md`

- [ ] **Step 1: Add documentation updates**

Document:
- board memberships are now persisted locally
- a backfill script exists
- screening uses local-first board lookup

- [ ] **Step 2: Add changelog entry**

Include:
- new board persistence tables
- new backfill script
- screening performance improvement from local board cache

- [ ] **Step 3: Verify docs reference real files and commands**

Check:
- script path
- command flags
- affected services

- [ ] **Step 4: Final verification**

Run:

```bash
python -m pytest tests/test_board_storage.py tests/test_board_repository.py tests/test_board_sync_service.py tests/test_factor_service.py -q
python -m py_compile src/storage.py src/repositories/board_repository.py src/services/board_sync_service.py src/services/factor_service.py scripts/backfill_instrument_boards.py
```

- [ ] **Step 5: Optional full-project checks**

If the environment allows:

```bash
./scripts/ci_gate.sh
```

- [ ] **Step 6: Handoff checkpoint**

Record:
- schema added
- backfill script added
- screening uses local-first lookup
- remote per-stock board fetches are no longer the default path

## Notes for Execution

- Keep phase 1 limited to normalized storage plus local-first lookup. Do not add board history snapshots yet.
- Use `instrument_master` as the source of truth for target symbols, but do not store memberships back into `instrument_master` as JSON.
- If remote providers return inconsistent board types, prefer a conservative normalized type such as `industry`, `concept`, `region`, or `unknown`.
- If a symbol has no boards from the provider, treat that as `missing`, not as a hard failure.
- If the inline migration path becomes too large inside `src/storage.py`, extract small helper methods but keep startup behavior unchanged.

## Review Note

This plan intentionally skips the subagent review loop from the skill because the current session instructions only allow `spawn_agent` when the user explicitly asks for sub-agents.
