# OpenClaw CN Board Input Guide

- generated_at: 2026-03-29
- total_boards: 1007

## Required rule

- Every OpenClaw theme name should exactly match at least one `board_name` from the whitelist whenever possible.
- Do not send composite names like `???/??` or `???/??` as one theme item.
- Split composite hot themes into multiple theme items, each aligned to a concrete board name.
- Keep keywords as supporting evidence only; do not rely on keywords to rescue a non-matching board name.

## Recommended input pattern

1. One hot board per theme item.
2. `theme.name` should prefer an exact board name from this whitelist.
3. If a news topic spans multiple boards, send multiple theme items instead of one merged label.

## Board counts by type

- unknown: 1007

## Files

- JSON: `docs/generated/openclaw-cn-board-whitelist-2026-03-29.json`
- CSV: `docs/generated/openclaw-cn-board-whitelist-2026-03-29.csv`
