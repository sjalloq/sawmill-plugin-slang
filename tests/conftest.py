"""Shared fixtures for slang plugin tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from sawmill_plugin_slang.plugin import SlangPlugin


@pytest.fixture
def plugin():
    """Return an instance of the slang plugin."""
    return SlangPlugin()


@pytest.fixture
def sample_log(tmp_path: Path) -> Path:
    """Create a sample log file for testing.

    Replace this content with real slang tool output.
    """
    log_file = tmp_path / "sample.log"
    log_file.write_text((Path(__file__).parent.parent / "examples" / "sample.log").read_text())
    return log_file
