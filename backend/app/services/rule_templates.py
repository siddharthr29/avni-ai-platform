"""Avni rule templates -- 42 production-quality patterns.

This module provides the canonical import path for rule templates.
Templates are defined in rule_generator.py (for now) and re-exported here
to establish a clean module boundary.

Future: move template definitions here once the migration is complete.

Usage:
    from app.services.rule_templates import RULE_TEMPLATES, get_template_by_id
"""

from __future__ import annotations

# Templates are defined in rule_generator.py to avoid a massive file copy.
# This module re-exports them so callers can migrate to the new import path.
# Circular import is avoided because rule_generator.py does NOT import from
# this module -- the dependency is one-way: rule_templates -> rule_generator.
#
# TODO: When ready, move the RULE_TEMPLATES list here and have rule_generator.py
#       import from this module instead (reversing the dependency direction).

__all__ = [
    "RULE_TEMPLATES",
    "_TEMPLATE_INDEX",
]

# Deferred import to document the intended future direction.
# Callers should use: from app.services.rule_templates import RULE_TEMPLATES


def __getattr__(name: str):
    """Lazy re-export from rule_generator to avoid circular imports."""
    if name in ("RULE_TEMPLATES", "_TEMPLATE_INDEX"):
        from app.services import rule_generator as _rg

        return getattr(_rg, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
