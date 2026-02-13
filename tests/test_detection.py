"""Tests for slang log file detection (can_handle)."""

from __future__ import annotations


class TestCanHandle:
    """Tests for the can_handle hook."""

    def test_matching_file_returns_high_confidence(self, plugin, sample_log):
        """A slang log file should return confidence >= 0.5."""
        # TODO: This test will pass once can_handle() is implemented
        # and sample.log contains real slang output.
        confidence = plugin.can_handle(sample_log)
        assert confidence >= 0.5, f"Expected confidence >= 0.5 for slang log, got {confidence}"

    def test_non_matching_file_returns_low_confidence(self, plugin, tmp_path):
        """A non-slang file should return confidence < 0.5."""
        other_file = tmp_path / "random.txt"
        other_file.write_text("This is not a slang log file.\n")
        confidence = plugin.can_handle(other_file)
        assert confidence < 0.5, f"Expected confidence < 0.5 for non-slang file, got {confidence}"

    def test_missing_file_returns_zero(self, plugin, tmp_path):
        """A non-existent file should return 0.0."""
        missing = tmp_path / "does_not_exist.log"
        assert plugin.can_handle(missing) == 0.0
