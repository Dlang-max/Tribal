"""Operational errors using the public parser diagnostic envelope."""
from __future__ import annotations


class TribalError(Exception):
    """An operational failure with safe, JSON-compatible diagnostic values.

    Callers must supply bounded messages and must not include credentials,
    connection strings, provider response bodies, or complete notes.
    """

    def __init__(self, code, message, *, path=None, field=None, expected=None,
                 actual=None, hint=None):
        super().__init__(message)
        self.code = code
        self.diagnostic = {
            "code": code,
            "severity": "error",
            "message": message,
            "path": path,
            "line": None,
            "column": None,
            "field": field,
            "expected": expected,
            "actual": actual,
            "hint": hint,
            "excerpt": None,
        }

    def as_dict(self):
        """Return a new operational failure envelope for CLI/library callers."""
        return {"ok": False, "diagnostics": [self.diagnostic.copy()]}
