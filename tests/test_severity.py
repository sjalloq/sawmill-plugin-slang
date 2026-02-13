"""Tests for slang severity levels (get_severity_levels)."""

from __future__ import annotations


class TestGetSeverityLevels:
    """Tests for the get_severity_levels hook."""

    def test_returns_non_empty_list(self, plugin):
        """get_severity_levels must return at least one level."""
        levels = plugin.get_severity_levels()
        assert len(levels) > 0, "Must define at least one severity level"

    def test_required_fields_present(self, plugin):
        """Each level must have id, name, level, and style."""
        for level in plugin.get_severity_levels():
            assert "id" in level, f"Missing 'id' in {level}"
            assert "name" in level, f"Missing 'name' in {level}"
            assert "level" in level, f"Missing 'level' in {level}"
            assert "style" in level, f"Missing 'style' in {level}"

    def test_ids_are_unique(self, plugin):
        """Severity IDs must be unique."""
        levels = plugin.get_severity_levels()
        ids = [lv["id"] for lv in levels]
        assert len(ids) == len(set(ids)), f"Duplicate severity IDs: {ids}"

    def test_levels_are_consecutive_from_zero(self, plugin):
        """Numeric levels must be consecutive integers starting at 0."""
        levels = plugin.get_severity_levels()
        numeric = sorted(lv["level"] for lv in levels)
        expected = list(range(len(levels)))
        assert numeric == expected, (
            f"Levels must be consecutive from 0: got {numeric}, expected {expected}"
        )

    def test_ids_are_lowercase(self, plugin):
        """Severity IDs should be lowercase."""
        for level in plugin.get_severity_levels():
            assert level["id"] == level["id"].lower(), (
                f"Severity ID should be lowercase: '{level['id']}'"
            )
