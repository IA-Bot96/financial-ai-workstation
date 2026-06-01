"""Excel worksheet name sanitization helpers."""

from __future__ import annotations

import re

EXCEL_SHEET_NAME_MAX_LENGTH = 31
_INVALID_SHEET_NAME_CHARS = re.compile(r"[\\/\?\*\[\]:]")
_WHITESPACE = re.compile(r"\s+")
_DEFAULT_SHEET_NAME = "Sheet"


def sanitize_sheet_name(name: str, existing_names: set[str]) -> str:
    """Return an Excel-safe, unique worksheet name.

    Excel worksheet names are limited to 31 characters, cannot contain
    ``\\ / ? * [ ] :``, and are effectively case-insensitive for uniqueness.
    """

    sanitized = _base_sheet_name(name)
    used_names = {existing_name.casefold() for existing_name in existing_names}
    if sanitized.casefold() not in used_names:
        return sanitized

    suffix_number = 2
    while True:
        suffix = f"_{suffix_number}"
        max_base_length = EXCEL_SHEET_NAME_MAX_LENGTH - len(suffix)
        candidate_base = sanitized[:max_base_length].rstrip()
        candidate = f"{candidate_base}{suffix}"
        if candidate.casefold() not in used_names:
            return candidate
        suffix_number += 1


def _base_sheet_name(name: str) -> str:
    cleaned = _INVALID_SHEET_NAME_CHARS.sub("", str(name))
    cleaned = _WHITESPACE.sub(" ", cleaned).rstrip()
    if not cleaned:
        cleaned = _DEFAULT_SHEET_NAME
    if len(cleaned) <= EXCEL_SHEET_NAME_MAX_LENGTH:
        return cleaned
    truncated = _truncate_readably(cleaned)
    return truncated or cleaned[:EXCEL_SHEET_NAME_MAX_LENGTH].rstrip()


def _truncate_readably(name: str) -> str:
    words = name.split(" ")
    result = ""
    for word in words:
        separator = " " if result else ""
        candidate = f"{result}{separator}{word}"
        if len(candidate) <= EXCEL_SHEET_NAME_MAX_LENGTH:
            result = candidate
            continue

        available = EXCEL_SHEET_NAME_MAX_LENGTH - len(result) - len(separator)
        if available <= 0:
            return result.rstrip()
        if available < 3:
            return result.rstrip() or word[:EXCEL_SHEET_NAME_MAX_LENGTH].rstrip()

        fragment_length = available - 2 if available >= 5 else available - 1
        fragment_length = max(3, fragment_length)
        return f"{result}{separator}{word[:fragment_length]}".rstrip()
    return result[:EXCEL_SHEET_NAME_MAX_LENGTH].rstrip()


__all__ = ["EXCEL_SHEET_NAME_MAX_LENGTH", "sanitize_sheet_name"]
