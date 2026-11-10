# cortex-vision

On-device vision capture MCP for Cortex (macOS, Apple Vision). Python.

Global rules are imported, not restated:

## Repo-specific constraints

- Eyes only: 'look' captures and extracts, then hands off to Cortex's recall/remember. It never reads or writes memories itself.
- Requires Camera and Screen Recording permissions; check_vision_setup compiles the helper and requests them.

## Etiquette

Conventional commits, staged file-by-file. One PR per concern. Do not merge your own PR without the owner's go-ahead.

## Non-negotiables

- CI contract (`docs/agent-guidance.md`, "CI contract for agents and routines"): it binds
  every agent and routine and wins over a less restrictive routine prompt. One pull request in flight, no
  comparison with the main branch, no forced push, no comment after an approve.
