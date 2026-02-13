# sawmill-plugin-slang

Sawmill plugin for slang

## Quick Start

```bash
# Install in development mode
make install

# Run tests
make test

# Lint
make lint
```

## Development

Start by filling in the TODO items in `src/sawmill_plugin_slang/plugin.py`.
Work on hooks in this order:

1. **`get_severity_levels`** — Define your tool's severity levels (already has a working default)
2. **`can_handle`** — Detect your tool's log files by name or content
3. **`load_and_parse`** — Parse log files into Message objects
4. **`get_filters`** — Add pre-defined filters for common patterns
5. **`extract_file_reference`** — Extract source file references from messages
6. **`get_grouping_fields`** — Add custom grouping dimensions (optional)

Add real log output to `examples/sample.log` to use in tests.

## How Sawmill Finds Your Plugin

Sawmill discovers plugins via Python entry points. The entry point is
declared in `pyproject.toml` under `[project.entry-points."sawmill.plugins"]`.
Running `pip install -e .` registers it. Confirm with `sawmill --list-plugins`.

## Testing

```bash
make test
```

Tests are in `tests/`. The contract tests (`test_plugin_contract.py`)
validate plugin structure and pass immediately. The other tests will
start passing as you implement the plugin hooks.
