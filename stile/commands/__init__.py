"""Command implementations.

Each `cmd_<name>(...)` returns a plain `dict` with the JSON success payload.
The CLI layer (stile.cli) handles JSON serialisation, exit codes, and human
output. Commands MUST NOT call `print()` -- that would break testability.
"""
