"""Regex patterns for slang log parsing.

Slang produces GCC-style diagnostics:
    filepath:line:col: severity: message [-Wflag]
      source_context
                     ^~~~
      in instance: hierarchy.path
"""

from __future__ import annotations

import re

# Primary diagnostic line: filepath:line:col: severity: message
# Captures: (filepath, line, column, severity, message_text)
DIAGNOSTIC_PATTERN = re.compile(r"^(\S+):(\d+):(\d+):\s+(warning|error|note):\s+(.+)$")

# Warning flag at end of message: [-Wflag-name]
# Captures: (flag_name) e.g. "sign-compare" from [-Wsign-compare]
WARNING_FLAG_PATTERN = re.compile(r"\[-W([\w-]+)\]\s*$")

# Instance hierarchy context line
INSTANCE_PATTERN = re.compile(r"^\s+in instance:\s+(.+)$")

# Slang signature for can_handle: diagnostic with SV/V file extensions
SLANG_SIGNATURE = re.compile(r"^\S+\.(?:sv|v|svh|vh):\d+:\d+:\s+(?:warning|error|note):")

# Build system error line (not a slang diagnostic)
BUILD_ERROR_PATTERN = re.compile(r"^ERROR:\s+(.+)$")

# File reference in arbitrary text: filepath:line:col:
FILE_REF_PATTERN = re.compile(r"(\S+\.\w+):(\d+):\d+:")

# Slang only emits -W flags for warnings; errors have no machine-readable
# identifier in the text or JSON output (the internal C++ DiagCode names like
# "ExpectedExpression" are never serialised).  Since we still want a usable
# message_id for grouping and filtering, we slugify the error text into a
# kebab-case ID.  This is inherently fragile — if slang rewords a message
# between versions the ID will change — but it's the best we can do without
# an upstream change.  An alternative would be to maintain a curated regex
# lookup table mapping common error texts to stable IDs.
_QUOTED_RE = re.compile(r"'[^']*'")


def slugify_error_message(msg_text: str) -> str:
    """Derive a kebab-case ID from an error message.

    Strips quoted identifiers, lowercases, keeps only alpha words,
    and joins with hyphens.

    Examples:
        "unknown module 'BUFG'"          -> "unknown-module"
        "identifier 'X' used before its declaration" -> "identifier-used-before-its-declaration"
        "could not resolve net type"     -> "could-not-resolve-net-type"
    """
    text = _QUOTED_RE.sub("", msg_text)
    words = [w.lower() for w in text.split() if w.isalpha()]
    return "-".join(words)
