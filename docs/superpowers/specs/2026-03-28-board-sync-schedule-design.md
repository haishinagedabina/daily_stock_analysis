# Board Sync Schedule Design

**Date:** 2026-03-28

**Goal:** Add a dedicated scheduled job that syncs local stock-to-board memberships after the A-share close on each trading day, so OpenClaw hot-theme screening can rely on a warm local board cache.

## Context

The repository already has a schedule-mode entrypoint and daily scheduler:

- [main.py](E:/daily_stock_analysis/main.py) enters schedule mode through `--schedule`
- [src/scheduler.py](E:/daily_stock_analysis/src/scheduler.py) registers a single daily job with the `schedule` library
- [src/services/screening_schedule_service.py](E:/daily_stock_analysis/src/services/screening_schedule_service.py) handles scheduled screening runs

We have now added:

- [src/services/board_sync_service.py](E:/daily_stock_analysis/src/services/board_sync_service.py)
- [scripts/backfill_instrument_boards.py](E:/daily_stock_analysis/scripts/backfill_instrument_boards.py)
- local persistence tables in [src/storage.py](E:/daily_stock_analysis/src/storage.py)

What is still missing is a scheduler-integrated board sync job that runs automatically after the market close.

## Requirements

1. Run only on A-share trading days by default.
2. Run after the market close, not before 15:00 Beijing time.
3. Reuse the existing schedule-mode lifecycle instead of introducing a parallel cron implementation.
4. Keep the job independent from the existing full analysis and screening jobs.
5. Fail open: a board-sync failure must not block the rest of the schedule process.
6. Be configurable from `.env` / runtime config just like other scheduled behaviors.

## Options Considered

### Option A: Reuse existing schedule loop and add a second daily job

Add a board-sync scheduled service and extend the current scheduler to support multiple daily jobs.

Pros:
- Reuses the repository's current schedule mode
- Keeps deployment and startup behavior consistent
- Easy to pair with trading-day checks and existing logging

Cons:
- Requires light refactoring in `src/scheduler.py`, which currently assumes one task

### Option B: Piggyback board sync onto the existing 18:00 scheduled analysis

Run board sync inside the current scheduled analysis task before the main job starts.

Pros:
- Smallest code change

Cons:
- Too late for the intended "after 15:00 prewarm" use case
- Couples two unrelated jobs too tightly

### Option C: Use a separate external cron / GitHub Actions workflow

Pros:
- Operationally simple in some deployments

Cons:
- Creates a second scheduling path outside the application's main lifecycle
- Harder to reason about local runs vs server runs

## Recommendation

Use **Option A**.

Add a dedicated board-sync scheduled job with its own configuration, and extend the current scheduler to support registering multiple daily jobs in the same process.

## Proposed Design

### 1. New config entries

Add:

- `BOARD_SYNC_SCHEDULE_ENABLED`
- `BOARD_SYNC_SCHEDULE_TIME`
- `BOARD_SYNC_RUN_IMMEDIATELY`

Recommended defaults:

- `BOARD_SYNC_SCHEDULE_ENABLED=false`
- `BOARD_SYNC_SCHEDULE_TIME=15:05`
- `BOARD_SYNC_RUN_IMMEDIATELY=false`

The time is intentionally set after the 15:00 A-share close to avoid syncing during the live session.

### 2. New service

Create:

- `src/services/board_sync_schedule_service.py`

Responsibilities:

- Check whether today is an A-share trading day
- Resolve the active local universe from `instrument_master`
- Invoke `BoardSyncService.sync_codes(...)`
- Log and return a structured summary
- Never raise a fatal error that stops the scheduler loop

### 3. Scheduler refactor

Update:

- `src/scheduler.py`

Current limitation:

- `Scheduler` stores a single `_task_callback`
- `set_daily_task()` registers one job only

Change to:

- support multiple named jobs
- allow different daily times per job
- keep the existing single-task API as a compatibility wrapper if possible

This avoids breaking current schedule users while enabling one process to run:

- full analysis or screening at `SCHEDULE_TIME`
- board sync at `BOARD_SYNC_SCHEDULE_TIME`

### 4. main.py schedule wiring

Update:

- `main.py`

In schedule mode:

- preserve the current scheduled analysis or scheduled screening behavior
- optionally register a second job when `BOARD_SYNC_SCHEDULE_ENABLED=true`
- instantiate `BoardSyncScheduleService`
- do not make board sync a hard prerequisite for the other scheduled jobs

### 5. Trading-day rule

Use the same style as [src/services/screening_schedule_service.py](E:/daily_stock_analysis/src/services/screening_schedule_service.py):

- default market: `cn`
- skip on non-trading days unless explicitly forced

This keeps behavior consistent with the rest of the application's scheduled market-sensitive jobs.

## Failure Handling

- If board sync fails, log the exception and return a structured failure payload
- Do not terminate the scheduler process
- Do not block the evening scheduled analysis job
- If no active local universe exists, log a warning and return a skip or failed summary rather than crashing

## Testing Strategy

1. Unit tests for `BoardSyncScheduleService`
   - trading day skip
   - successful sync
   - failure isolation

2. Unit tests for `Scheduler`
   - multiple jobs can be registered
   - compatibility with the old single-job entrypoint remains intact

3. Schedule wiring tests for `main.py` or a narrow wrapper
   - board sync job is registered only when enabled
   - board sync does not replace existing scheduled analysis or screening job

4. Config tests
   - defaults and parsing for the three new env vars

## Non-Goals

- No historical versioning of board memberships
- No true `stale-only` incremental refresh in this phase
- No separate external workflow or system cron integration

## Rollout Plan

1. Land config and service
2. Refactor scheduler to support multiple jobs
3. Wire board sync into schedule mode behind `BOARD_SYNC_SCHEDULE_ENABLED`
4. Add docs and tests
5. Keep disabled by default until explicitly enabled in deployment
