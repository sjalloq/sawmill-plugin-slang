"""Contract tests for slang plugin structure.

These tests validate that the plugin conforms to the sawmill plugin
contract without testing parsing correctness. They should pass
immediately after generation.
"""

from __future__ import annotations

from collections.abc import Iterator

from sawmill.plugin import SawmillPlugin


class TestPluginContract:
    """Structural contract checks."""

    def test_inherits_from_sawmill_plugin(self, plugin):
        """Plugin must inherit from SawmillPlugin."""
        assert isinstance(plugin, SawmillPlugin)

    def test_name_is_not_default(self, plugin):
        """Plugin name must be set (not 'base')."""
        assert plugin.name != "base", "Plugin must set a unique name"
        assert plugin.name, "Plugin name must not be empty"

    def test_can_handle_returns_float(self, plugin, tmp_path):
        """can_handle must return a float between 0 and 1."""
        dummy = tmp_path / "test.log"
        dummy.write_text("test content\n")
        result = plugin.can_handle(dummy)
        assert isinstance(result, float), f"Expected float, got {type(result)}"
        assert 0.0 <= result <= 1.0, f"Confidence must be 0.0-1.0, got {result}"

    def test_load_and_parse_returns_iterator(self, plugin, tmp_path):
        """load_and_parse must return an iterator (generator)."""
        dummy = tmp_path / "test.log"
        dummy.write_text("test content\n")
        result = plugin.load_and_parse(dummy)
        assert isinstance(result, Iterator)

    def test_get_filters_returns_list(self, plugin):
        """get_filters must return a list."""
        result = plugin.get_filters()
        assert isinstance(result, list)

    def test_severity_levels_valid_structure(self, plugin):
        """get_severity_levels must return well-formed dicts."""
        levels = plugin.get_severity_levels()
        assert isinstance(levels, list)
        assert len(levels) > 0
        for level in levels:
            assert isinstance(level, dict)
            assert isinstance(level["id"], str)
            assert isinstance(level["name"], str)
            assert isinstance(level["level"], int)
            assert isinstance(level["style"], str)

    def test_grouping_fields_valid_types(self, plugin):
        """get_grouping_fields must use valid field_type values."""
        valid_types = {"builtin", "metadata", "file_ref"}
        for field in plugin.get_grouping_fields():
            assert field["field_type"] in valid_types, (
                f"Invalid field_type '{field['field_type']}' for field '{field['id']}'. "
                f"Must be one of: {valid_types}"
            )

    def test_parsed_severities_match_declared(self, plugin, sample_log):
        """Message severities should be from declared severity IDs."""
        declared_ids = {lv["id"] for lv in plugin.get_severity_levels()}
        messages = list(plugin.load_and_parse(sample_log))
        for msg in messages:
            if msg.severity is not None:
                assert msg.severity in declared_ids, (
                    f"Message severity '{msg.severity}' not in declared "
                    f"severity IDs: {declared_ids}"
                )
