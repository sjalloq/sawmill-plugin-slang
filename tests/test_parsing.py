"""Tests for slang log parsing (load_and_parse)."""

from __future__ import annotations

from sawmill.models.message import Message

from sawmill_plugin_slang.patterns import slugify_error_message  # first-party


class TestLoadAndParse:
    """Tests for the load_and_parse hook."""

    def test_returns_list(self, plugin, sample_log):
        """load_and_parse should return a list."""
        result = plugin.load_and_parse(sample_log)
        assert isinstance(result, list)

    def test_items_are_messages(self, plugin, sample_log):
        """Each item should be a Message instance."""
        messages = plugin.load_and_parse(sample_log)
        for msg in messages:
            assert isinstance(msg, Message), f"Expected Message, got {type(msg)}"

    def test_messages_have_required_fields(self, plugin, sample_log):
        """Each message should have start_line, raw_text, and content populated."""
        messages = plugin.load_and_parse(sample_log)
        for msg in messages:
            assert msg.start_line >= 1, "start_line should be >= 1"
            assert msg.raw_text, "raw_text should not be empty"
            assert msg.content, "content should not be empty"

    def test_empty_file_returns_empty_list(self, plugin, tmp_path):
        """An empty file should return an empty list."""
        empty = tmp_path / "empty.log"
        empty.write_text("")
        assert plugin.load_and_parse(empty) == []

    def test_missing_file_returns_empty_list(self, plugin, tmp_path):
        """A non-existent file should return an empty list."""
        missing = tmp_path / "missing.log"
        assert plugin.load_and_parse(missing) == []


class TestErrorMessageId:
    """Tests that error messages get synthesized message IDs."""

    def test_unknown_module_gets_id(self, plugin, tmp_path):
        """Errors like 'unknown module' should get a synthesized message_id."""
        log = tmp_path / "test.log"
        log.write_text(
            "src/foo.sv:91:3: error: unknown module 'BUFG'\n"
            "  BUFG u_bufg_fb (\n"
            "  ^~~~\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].message_id == "unknown-module"

    def test_use_before_declaration_gets_id(self, plugin, tmp_path):
        """'identifier X used before its declaration' should get a synthesized ID."""
        log = tmp_path / "test.log"
        log.write_text(
            "src/foo.sv:48:19: error: identifier 'DepthW' used before its declaration\n"
            "    input  logic [DepthW-1:0] fifo_depth_i,\n"
            "                  ^~~~~~\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].message_id == "identifier-used-before-its-declaration"

    def test_build_error_gets_id(self, plugin, tmp_path):
        """BUILD ERROR lines should also get a synthesized message_id."""
        log = tmp_path / "test.log"
        log.write_text(
            "ERROR: Failed to build mono:projects:squirrel : Slang lint check failed\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].severity == "error"
        assert msgs[0].message_id is not None
        assert msgs[0].content == "Failed to build mono:projects:squirrel : Slang lint check failed"

    def test_novel_error_gets_id(self, plugin, tmp_path):
        """Any error should get a slugified ID, not just known patterns."""
        log = tmp_path / "test.log"
        log.write_text(
            "src/foo.sv:10:5: error: completely new error type never seen before\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].message_id == "completely-new-error-type-never-seen-before"


class TestWarningMessageId:
    """Tests that warning messages get message IDs from -W flags."""

    def test_warning_flag_extracted(self, plugin, tmp_path):
        """Warnings with [-Wflag] should have flag as message_id."""
        log = tmp_path / "test.log"
        log.write_text(
            "src/foo.sv:72:23: warning: comparison of differently signed types "
            "('int' and 'int unsigned') [-Wsign-compare]\n"
            "    for (int m = 0; m < NumMasters; m++) begin\n"
            "                    ~ ^ ~~~~~~~~~~\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].message_id == "sign-compare"


class TestCategoryPopulated:
    """Tests that category is derived from message_id."""

    def test_category_from_warning_flag(self, plugin, tmp_path):
        """Category should be first segment of the warning flag."""
        log = tmp_path / "test.log"
        log.write_text(
            "src/foo.sv:72:23: warning: comparison [-Wsign-compare]\n"
            "    for (int m = 0; m < NumMasters; m++) begin\n"
            "                    ~ ^ ~~~~~~~~~~\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].category == "sign"

    def test_category_from_error_id(self, plugin, tmp_path):
        """Category should be first segment of synthesized error ID."""
        log = tmp_path / "test.log"
        log.write_text(
            "src/foo.sv:91:3: error: unknown module 'BUFG'\n"
            "  BUFG u_bufg_fb (\n"
            "  ^~~~\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].category == "unknown"

    def test_no_category_when_no_id(self, plugin, tmp_path):
        """A note without a flag or error text that yields no alpha words has no category."""
        log = tmp_path / "test.log"
        log.write_text(
            "src/foo.sv:10:5: note: 12345\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].message_id is None
        assert msgs[0].category is None


class TestNoteGrouping:
    """Tests that note: diagnostics are grouped with their parent message."""

    def test_note_grouped_with_parent_warning(self, plugin, tmp_path):
        """A note: following a warning should be absorbed into the warning."""
        log = tmp_path / "test.log"
        log.write_text(
            "src/foo.sv:574:36: warning: initializer for static variable "
            "'unused' refers to 'key_valid_i' [-Wstatic-init-value]\n"
            "    logic unused = key_valid_i &\n"
            "                   ^~~~~~~~~~~\n"
            "src/foo.sv:103:72: note: declared here\n"
            "  input  logic  key_valid_i,\n"
            "                ^~~~~~~~~~~\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].severity == "warning"
        assert msgs[0].message_id == "static-init-value"
        # The note lines should be included in raw_text
        assert "note: declared here" in msgs[0].raw_text

    def test_note_grouped_with_parent_error(self, plugin, tmp_path):
        """A note: following an error should be absorbed into the error."""
        log = tmp_path / "test.log"
        log.write_text(
            "src/foo.sv:48:19: error: identifier 'DepthW' used before its declaration\n"
            "    input  logic [DepthW-1:0] fifo_depth_i,\n"
            "                  ^~~~~~\n"
            "src/foo.sv:95:29: note: declared here\n"
            "    localparam int unsigned DepthW = prim_util_pkg::vbits(DEPTH + 1);\n"
            "                            ^\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].severity == "error"
        assert "note: declared here" in msgs[0].raw_text

    def test_standalone_note_without_parent(self, plugin, tmp_path):
        """A note: at the start of a file (no preceding warning/error) stays standalone."""
        log = tmp_path / "test.log"
        log.write_text(
            "src/foo.sv:10:5: note: some standalone note\n"
            "  context line\n"
            "  ^~~~\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].severity == "note"

    def test_multiple_notes_grouped(self, plugin, tmp_path):
        """Multiple consecutive notes should all be absorbed into the parent."""
        log = tmp_path / "test.log"
        log.write_text(
            "src/foo.sv:10:5: warning: some warning [-Wtest-flag]\n"
            "  context\n"
            "  ^~~~\n"
            "src/foo.sv:20:5: note: first note\n"
            "  note context 1\n"
            "  ^\n"
            "src/foo.sv:30:5: note: second note\n"
            "  note context 2\n"
            "  ^\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].severity == "warning"
        assert "first note" in msgs[0].raw_text
        assert "second note" in msgs[0].raw_text

    def test_note_between_two_warnings_groups_correctly(self, plugin, tmp_path):
        """Note between two warnings should attach to the first, not the second."""
        log = tmp_path / "test.log"
        log.write_text(
            "src/foo.sv:10:5: warning: first warning [-Wflag-a]\n"
            "  context\n"
            "  ^~~~\n"
            "src/foo.sv:20:5: note: relates to first warning\n"
            "  note context\n"
            "  ^\n"
            "\n"
            "src/foo.sv:30:5: warning: second warning [-Wflag-b]\n"
            "  context\n"
            "  ^~~~\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 2
        assert msgs[0].severity == "warning"
        assert "relates to first warning" in msgs[0].raw_text
        assert msgs[1].severity == "warning"
        assert msgs[1].message_id == "flag-b"


class TestMultilineGrouping:
    """Tests for multi-line message grouping."""

    def test_source_context_and_caret_grouped(self, plugin, tmp_path):
        """Source context and caret indicator should be part of the message."""
        log = tmp_path / "test.log"
        log.write_text(
            "src/foo.sv:72:23: warning: comparison [-Wsign-compare]\n"
            "    for (int m = 0; m < NumMasters; m++) begin\n"
            "                    ~ ^ ~~~~~~~~~~\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].start_line == 1
        assert msgs[0].end_line == 3
        assert "for (int m = 0" in msgs[0].raw_text
        assert "~ ^ ~~~~~~~~~~" in msgs[0].raw_text


class TestInstanceMetadata:
    """Tests for instance hierarchy extraction."""

    def test_instance_metadata_extracted(self, plugin, tmp_path):
        """'in instance:' lines should populate metadata."""
        log = tmp_path / "test.log"
        log.write_text(
            "src/foo.sv:72:23: warning: comparison [-Wsign-compare]\n"
            "    for (int m = 0; m < NumMasters; m++) begin\n"
            "                    ~ ^ ~~~~~~~~~~\n"
            "  in instance: top.u_core.u_soc\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].metadata.get("instance") == "top.u_core.u_soc"


class TestBuildError:
    """Tests for build system error detection."""

    def test_build_error_detected(self, plugin, tmp_path):
        """'ERROR:' lines should be parsed as error messages."""
        log = tmp_path / "test.log"
        log.write_text(
            "Build failed: 12 errors, 395 warnings\n"
            "ERROR: Failed to build project : Slang lint check failed\n"
        )
        msgs = plugin.load_and_parse(log)
        assert len(msgs) == 1
        assert msgs[0].severity == "error"
        assert "Failed to build" in msgs[0].content


class TestSlugifyErrorMessage:
    """Tests for the slugify_error_message utility."""

    def test_strips_quoted_identifiers(self):
        assert slugify_error_message("unknown module 'BUFG'") == "unknown-module"

    def test_preserves_non_quoted_words(self):
        assert slugify_error_message("could not resolve net type") == "could-not-resolve-net-type"

    def test_strips_non_alpha_tokens(self):
        """Tokens with colons, digits, etc. are dropped."""
        assert slugify_error_message("Failed to build foo:bar : check failed") == (
            "failed-to-build-check-failed"
        )

    def test_empty_after_stripping(self):
        """If only quoted/non-alpha content, returns empty string."""
        assert slugify_error_message("'foo' 123") == ""


class TestExtractFileReference:
    """Tests for extract_file_reference hook."""

    def test_extracts_slang_format(self, plugin):
        """Should extract file reference from slang diagnostic format."""
        ref = plugin.extract_file_reference("src/foo.sv:42:10: warning: something")
        assert ref is not None
        assert ref.path == "src/foo.sv"
        assert ref.line == 42

    def test_returns_none_for_no_match(self, plugin):
        """Should return None when no file reference found."""
        ref = plugin.extract_file_reference("no file reference here")
        assert ref is None
