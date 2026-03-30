# Board Sync Schedule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated scheduled board-sync job that runs after the A-share close on trading days and prewarms local stock-to-board memberships.

**Architecture:** Reuse the existing schedule-mode process in `main.py`, extend `src/scheduler.py` to register multiple daily jobs, and add a new `BoardSyncScheduleService` that wraps `BoardSyncService` with trading-day guards and structured logging. Keep the feature opt-in behind dedicated config flags so current deployments remain unchanged until enabled.

**Tech Stack:** Python, schedule, SQLAlchemy, pytest

---

## File Map

### Scheduler and startup wiring
- Modify: `src/scheduler.py`
- Modify: `main.py`

### Board sync scheduled service
- Create: `src/services/board_sync_schedule_service.py`
- Reference: `src/services/board_sync_service.py`
- Reference: `src/services/screening_schedule_service.py`

### Config
- Modify: `src/config.py`
- Modify: `src/core/config_registry.py`
- Modify: `.env.example`

### Tests
- Create: `tests/test_board_sync_schedule_service.py`
- Modify: `tests/test_config.py` or nearest config coverage file if present
- Create or modify: `tests/test_scheduler.py`
- Optional narrow wiring test: `tests/test_main_schedule_wiring.py`

### Docs
- Modify: `README.md`
- Modify: `docs/CHANGELOG.md`

## Constraints and Guardrails

- Use TDD for each behavior change.
- Keep `BOARD_SYNC_SCHEDULE_ENABLED` disabled by default.
- Do not replace or delay the current scheduled analysis or scheduled screening job.
- Board-sync failures must not crash the scheduler loop.
- Preserve compatibility for existing callers of `Scheduler.set_daily_task(...)`.

## Task 1: Add Config Entries

**Outcome:** The board sync schedule is configurable and disabled by default.

**Files:**
- Modify: `src/config.py`
- Modify: `src/core/config_registry.py`
- Modify: `.env.example`

- [ ] **Step 1: Write the failing config test**

Cover:
- `BOARD_SYNC_SCHEDULE_ENABLED` default is `False`
- `BOARD_SYNC_SCHEDULE_TIME` default is `15:05`
- `BOARD_SYNC_RUN_IMMEDIATELY` default is `False`

- [ ] **Step 2: Run the focused config test and verify failure**

Run:

```bash
python -m pytest tests/test_config.py -q
```

- [ ] **Step 3: Add the new config fields in `src/config.py`**

Add:
- `board_sync_schedule_enabled: bool = False`
- `board_sync_schedule_time: str = "15:05"`
- `board_sync_run_immediately: bool = False`

- [ ] **Step 4: Add env parsing**

Read:
- `BOARD_SYNC_SCHEDULE_ENABLED`
- `BOARD_SYNC_SCHEDULE_TIME`
- `BOARD_SYNC_RUN_IMMEDIATELY`

- [ ] **Step 5: Register the fields in `src/core/config_registry.py`**

Add titles and descriptions so Web/runtime config surfaces stay consistent.

- [ ] **Step 6: Update `.env.example`**

Document the three new env vars with safe defaults.

- [ ] **Step 7: Re-run the focused config test**

Run:

```bash
python -m pytest tests/test_config.py -q
python -m py_compile src/config.py src/core/config_registry.py
```

## Task 2: Add BoardSyncScheduleService

**Outcome:** There is one dedicated service that handles scheduled board sync with trading-day guards.

**Files:**
- Create: `src/services/board_sync_schedule_service.py`
- Create: `tests/test_board_sync_schedule_service.py`

- [ ] **Step 1: Write the failing service tests**

Cover:
- skip on non-trading day
- successful sync on trading day
- service returns structured summary instead of raising

Suggested test shape:

```python
def test_run_once_skips_non_trading_day():
    service = BoardSyncScheduleService(...)
    result = service.run_once(force_run=False, market="cn")
    assert result["status"] == "skipped"
```

- [ ] **Step 2: Run the focused service tests and verify failure**

Run:

```bash
python -m pytest tests/test_board_sync_schedule_service.py -q
```

- [ ] **Step 3: Implement `BoardSyncScheduleService`**

Responsibilities:
- call trading-day guard
- resolve active symbols from `instrument_master`
- invoke `BoardSyncService.sync_codes(...)`
- return `status`, `processed`, `synced`, `missing`, `failed`

- [ ] **Step 4: Keep failures non-fatal**

Wrap sync calls so an exception returns a structured failure payload and logs the error.

- [ ] **Step 5: Re-run service tests**

Run:

```bash
python -m pytest tests/test_board_sync_schedule_service.py -q
python -m py_compile src/services/board_sync_schedule_service.py
```

## Task 3: Extend Scheduler for Multiple Jobs

**Outcome:** One scheduler process can host both the existing scheduled run and the new board-sync job.

**Files:**
- Modify: `src/scheduler.py`
- Create or modify: `tests/test_scheduler.py`

- [ ] **Step 1: Write the failing scheduler test**

Cover:
- multiple daily jobs can be registered with different times
- the legacy single-task API still works

- [ ] **Step 2: Run the focused scheduler test and verify failure**

Run:

```bash
python -m pytest tests/test_scheduler.py -q
```

- [ ] **Step 3: Refactor `Scheduler`**

Target design:
- keep `set_daily_task(...)` as a compatibility wrapper
- add a new multi-job registration method such as `add_daily_task(name, task, schedule_time, run_immediately=False)`

- [ ] **Step 4: Preserve logging and graceful shutdown**

Ensure the new job model still uses `_safe_run_task(...)` style protection and existing signal handling.

- [ ] **Step 5: Re-run scheduler tests**

Run:

```bash
python -m pytest tests/test_scheduler.py -q
python -m py_compile src/scheduler.py
```

## Task 4: Wire Board Sync into Schedule Mode

**Outcome:** `main.py --schedule` can register the board-sync job when enabled without disturbing current jobs.

**Files:**
- Modify: `main.py`
- Optional test: `tests/test_main_schedule_wiring.py`

- [ ] **Step 1: Write the failing wiring test or narrow integration test**

Cover:
- board sync job is added only when `BOARD_SYNC_SCHEDULE_ENABLED=true`
- existing scheduled analysis or screening job still registers

- [ ] **Step 2: Run the focused wiring test and verify failure**

Run:

```bash
python -m pytest tests/test_main_schedule_wiring.py -q
```

- [ ] **Step 3: Update schedule-mode startup in `main.py`**

Behavior:
- keep current scheduled task logic
- instantiate the scheduler directly
- register the existing job
- conditionally register the board sync job
- run the scheduler loop once all jobs are registered

- [ ] **Step 4: Respect immediate-run settings independently**

Use:
- `SCHEDULE_RUN_IMMEDIATELY` for the existing main job
- `BOARD_SYNC_RUN_IMMEDIATELY` for the board-sync job

- [ ] **Step 5: Re-run wiring tests**

Run:

```bash
python -m pytest tests/test_main_schedule_wiring.py -q
python -m py_compile main.py
```

## Task 5: Update Docs

**Outcome:** Operators know how to enable and use the new scheduled board sync.

**Files:**
- Modify: `README.md`
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: Update `README.md`**

Document:
- purpose of the scheduled board sync
- new env vars
- recommended default time: `15:05`

- [ ] **Step 2: Update `docs/CHANGELOG.md`**

Add an unreleased note for scheduled board-cache prewarm support.

- [ ] **Step 3: Check docs references**

Verify:
- file names
- env var names
- command examples

## Task 6: Final Verification

**Outcome:** The scheduled board sync is covered by tests and safe to hand off.

**Files:**
- No new files

- [ ] **Step 1: Run focused test suite**

Run:

```bash
python -m pytest tests/test_board_sync_schedule_service.py tests/test_scheduler.py tests/test_main_schedule_wiring.py tests/test_config.py -q
```

- [ ] **Step 2: Run related regression tests**

Run:

```bash
python -m pytest tests/test_board_sync_service.py tests/test_backfill_instrument_boards.py tests/test_factor_service.py -q
```

- [ ] **Step 3: Run compile checks**

Run:

```bash
python -m py_compile main.py src/config.py src/core/config_registry.py src/scheduler.py src/services/board_sync_schedule_service.py
```

- [ ] **Step 4: Optional manual smoke**

Run in a safe local environment:

```bash
python main.py --schedule --no-run-immediately
```

Check:
- the existing main scheduled job is still registered
- the board sync job is registered only when enabled
- next run timestamps look correct

- [ ] **Step 5: Handoff**

Record:
- changed files
- verification evidence
- known gaps such as `stale-only` still being future work
