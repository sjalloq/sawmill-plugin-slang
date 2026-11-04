"""Sawmill plugin for slang (SystemVerilog compiler)."""

from __future__ import annotations

from collections.abc import Iterator
from importlib.metadata import version
from pathlib import Path
from typing import TextIO

from sawmill.models.filter_def import FilterDefinition
from sawmill.models.message import FileRef, Message
from sawmill.plugin import SawmillPlugin, hookimpl

from sawmill_plugin_slang.patterns import (
    BUILD_ERROR_PATTERN,
    DIAGNOSTIC_PATTERN,
    FILE_REF_PATTERN,
    INSTANCE_PATTERN,
    SLANG_SIGNATURE,
    WARNING_FLAG_PATTERN,
    slugify_error_message,
)

# Number of lines to scan for can_handle detection
_DETECTION_LINES = 100

# load_and_parse state-machine modes (see SlangPlugin._parse_stream)
_PLAIN, _PRIMARY, _NOTE = range(3)


class SlangPlugin(SawmillPlugin):
    """Parser for slang log files.

    Detects and parses slang (SystemVerilog compiler) logs, extracting
    structured messages including severity, warning flags, file references,
    and design hierarchy context.

    Slang diagnostic format:
        filepath:line:col: severity: message [-Wflag]
          source_context
                         ^~~~
          in instance: hierarchy.path
    """

    name = "slang"
    version = version("sawmill-plugin-slang")
    description = "Sawmill plugin for slang SystemVerilog compiler"

    @hookimpl
    def can_handle(self, path: Path) -> float:
        """Determine if this is a slang log file.

        Reads the first N lines and looks for slang-style diagnostics
        referencing SystemVerilog/Verilog source files.

        Returns:
            Confidence score 0.0-1.0 based on how many diagnostic
            lines match the slang pattern.
        """
        if not path.exists():
            return 0.0

        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                matches = 0
                for i, line in enumerate(f):
                    if i >= _DETECTION_LINES:
                        break
                    if SLANG_SIGNATURE.match(line.rstrip("\n")):
                        matches += 1
        except OSError:
            return 0.0

        if matches >= 3:
            return 0.8
        elif matches >= 1:
            return 0.6
        return 0.0

    @staticmethod
    def _synthesize_error_id(msg_text: str) -> str | None:
        """Derive a message ID from error text by slugifying.

        Strips quoted identifiers and converts to kebab-case.
        Returns None only if the message has no alpha words.
        """
        slug = slugify_error_message(msg_text)
        return slug or None

    @staticmethod
    def _extract_category(message_id: str | None) -> str | None:
        """Extract category from the first segment of a message ID.

        E.g. "sign-compare" -> "sign", "unknown-module" -> "unknown".
        """
        if not message_id:
            return None
        parts = message_id.split("-")
        return parts[0] if parts else None

    @hookimpl
    def load_and_parse(self, path: Path) -> Iterator[Message]:
        """Stream a slang log file as parsed messages.

        The file is checked and opened eagerly, when this is called, so a
        missing or unreadable file yields an empty iterator without raising.
        Parsing then proceeds lazily via `_parse_stream`.
        """
        if not path.exists():
            return iter(())
        try:
            f = open(path, encoding="utf-8", errors="replace")
        except OSError:
            return iter(())
        return self._parse_stream(f)

    def _parse_stream(self, f: TextIO) -> Iterator[Message]:
        """Single-pass state machine over an open file; closes it when done.

        Modes:
          - ``_PLAIN``: no continuation context. Indented and instance lines
            extend the current message; a `note:` is absorbed only into a
            warning/error parent; other text flushes and is dropped.
          - ``_PRIMARY``: after a primary diagnostic. Indented and instance
            lines extend it; any `note:` is absorbed; other text flushes.
          - ``_NOTE``: after an absorbed `note:`. Every non-blank line that is
            not a new diagnostic or build error is appended, indented or not.

        Memory stays O(one in-flight message).
        """
        current_lines: list[str] = []
        current_start: int = 0
        current_severity: str | None = None
        current_content: str | None = None
        current_file_ref: FileRef | None = None
        current_message_id: str | None = None
        current_instance: str | None = None
        mode = _PLAIN

        def _build() -> Message:
            raw_text = "\n".join(current_lines)
            metadata: dict[str, str] = {}
            if current_instance:
                metadata["instance"] = current_instance
            return Message(
                start_line=current_start,
                end_line=current_start + len(current_lines) - 1,
                raw_text=raw_text,
                content=current_content or raw_text,
                severity=current_severity,
                message_id=current_message_id,
                category=self._extract_category(current_message_id),
                file_ref=current_file_ref,
                metadata=metadata,
            )

        def _reset() -> None:
            nonlocal current_severity, current_content
            nonlocal current_file_ref, current_message_id, current_instance
            current_lines.clear()
            current_severity = None
            current_content = None
            current_file_ref = None
            current_message_id = None
            current_instance = None

        try:
            for line_num, raw in enumerate(f, 1):
                line = raw.rstrip("\n")

                # Empty line separates message blocks.
                if not line.strip():
                    if current_lines and current_severity is not None:
                        yield _build()
                    _reset()
                    mode = _PLAIN
                    continue

                diag_match = DIAGNOSTIC_PATTERN.match(line)
                if diag_match:
                    filepath, line_no, _col_no, severity, msg_text = diag_match.groups()

                    # `note:` diagnostics are absorbed into a parent message.
                    if severity == "note" and current_lines and (
                        mode != _PLAIN or current_severity in ("warning", "error")
                    ):
                        current_lines.append(line)
                        mode = _NOTE
                        continue

                    # New primary diagnostic: flush previous, start fresh.
                    if current_lines and current_severity is not None:
                        yield _build()
                    _reset()
                    mode = _PRIMARY

                    current_lines.append(line)
                    current_start = line_num
                    current_severity = severity
                    current_content = msg_text
                    current_file_ref = FileRef(path=filepath, line=int(line_no))

                    flag_match = WARNING_FLAG_PATTERN.search(msg_text)
                    if flag_match:
                        current_message_id = flag_match.group(1)
                    elif severity == "error":
                        current_message_id = self._synthesize_error_id(msg_text)
                    else:
                        current_message_id = None
                    continue

                build_match = BUILD_ERROR_PATTERN.match(line)

                # After an absorbed note, everything up to the next blank line,
                # diagnostic or build error belongs to the message.
                if mode == _NOTE and not build_match:
                    current_lines.append(line)
                    continue

                instance_match = INSTANCE_PATTERN.match(line)
                if instance_match and current_lines:
                    current_instance = instance_match.group(1)
                    current_lines.append(line)
                    continue

                if line[0].isspace() and current_lines:
                    current_lines.append(line)
                    continue

                if build_match:
                    if current_lines and current_severity is not None:
                        yield _build()
                    _reset()
                    mode = _PLAIN
                    current_lines.append(line)
                    current_start = line_num
                    current_severity = "error"
                    current_content = build_match.group(1)
                    current_message_id = self._synthesize_error_id(build_match.group(1))
                    continue

                # Non-diagnostic, non-continuation line: flush and drop.
                if current_lines and current_severity is not None:
                    yield _build()
                _reset()
                mode = _PLAIN

            if current_lines and current_severity is not None:
                yield _build()
        finally:
            f.close()

    @hookimpl
    def get_severity_levels(self) -> list[dict]:
        """Define severity levels for slang logs.

        Slang produces three severity levels: error, warning, and note.
        """
        return [
            {
                "id": "error",
                "name": "Error",
                "level": 2,
                "style": "red bold",
            },
            {
                "id": "warning",
                "name": "Warning",
                "level": 1,
                "style": "yellow",
            },
            {
                "id": "note",
                "name": "Note",
                "level": 0,
                "style": "cyan",
            },
        ]

    @hookimpl
    def get_filters(self) -> list[FilterDefinition]:
        """Get pre-defined filter definitions for slang logs.

        Provides filters for common warning categories.
        """
        return [
            FilterDefinition(
                id="width-warnings",
                name="Width Warnings",
                pattern=r"\[-Wwidth-",
                source="plugin:slang",
                description="Width truncation and expansion warnings",
            ),
            FilterDefinition(
                id="sign-warnings",
                name="Sign Warnings",
                pattern=r"\[-Wsign-",
                source="plugin:slang",
                description="Sign comparison and conversion warnings",
            ),
            FilterDefinition(
                id="case-warnings",
                name="Case Warnings",
                pattern=r"\[-Wcase-",
                source="plugin:slang",
                description="Case statement warnings (redundant default, missing default)",
            ),
            FilterDefinition(
                id="unused-warnings",
                name="Unused Warnings",
                pattern=r"\[-Wun(?:used|assigned|driven)-",
                source="plugin:slang",
                description="Unused, unassigned, and undriven variable/port warnings",
            ),
            FilterDefinition(
                id="conversion-warnings",
                name="Conversion Warnings",
                pattern=r"\[-W\S*conv\b",
                source="plugin:slang",
                description="Implicit type conversion warnings",
            ),
        ]

    @hookimpl
    def extract_file_reference(self, content: str) -> FileRef | None:
        """Extract a file reference from message content.

        Matches the slang diagnostic format: filepath:line:col:
        """
        match = FILE_REF_PATTERN.search(content)
        if match:
            return FileRef(path=match.group(1), line=int(match.group(2)))
        return None

    @hookimpl
    def get_grouping_fields(self) -> list[dict]:
        """Get fields available for grouping and sorting.

        Adds instance hierarchy as a metadata grouping dimension
        in addition to the standard fields.
        """
        return [
            {
                "id": "severity",
                "name": "Severity",
                "field_type": "builtin",
                "description": "Group by message severity level",
            },
            {
                "id": "id",
                "name": "Warning Flag",
                "field_type": "builtin",
                "description": "Group by warning flag (e.g. sign-compare)",
            },
            {
                "id": "file",
                "name": "Source File",
                "field_type": "file_ref",
                "description": "Group by source file path",
            },
            {
                "id": "category",
                "name": "Category",
                "field_type": "builtin",
                "description": "Group by message category",
            },
            {
                "id": "instance",
                "name": "Instance",
                "field_type": "metadata",
                "description": "Group by design instance hierarchy",
            },
        ]
