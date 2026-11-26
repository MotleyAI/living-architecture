---
name: codex-review
description: Use the codex MCP server to review the current git diff. Focus on correctness, regressions, security issues, tests, and maintainability. Return only actionable findings with file/line references and severity. Do not modify files.
---

**Preflight:** run `la-doctor --plugin <this skill's base directory>` once per session before using any `la-*` or `trmv-*` command; if it fails, stop and show the user its output. If `la-doctor` is not found, or reports the la tools older than the plugin, stop and give the user the install command at this plugin's `version` (in its `.claude-plugin/plugin.json`): `uv tool install living-architecture==<version> --with-executables-from type-rename-move` in a Python repo, `npm install -g living-architecture@<version> type-rename-move@<version>` in a TS/JS repo.

If `la-config get reviewers.codex` prints `false`, this repo has turned Codex reviews off: say so, and run the
review only if the user confirms. If the Codex MCP server (`mcp__codex__codex`) is not available, stop and tell
the user; never substitute another reviewer.

Use the codex MCP server to review the current git diff.
Focus on correctness, regressions, security issues, tests, and maintainability.
Return only actionable findings with file/line references and severity.
Do not modify files.
