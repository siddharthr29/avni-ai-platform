"""Configurable per-org ban list validator for AI content safety.

Supports per-org banned words. Example use case: blocking "sonography"
in maternal health contexts (sex determination tests illegal in India per PCPNDT Act).

Ban lists are loaded from the database and cached in-memory. They can be
managed via the guardrails admin API.
"""

import logging
import re
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


# ── In-memory cache ──────────────────────────────────────────────────────────
# org_id -> list of {"word": str, "reason": str}
_ban_lists: dict[str, list[dict[str, str]]] = {}

# Global ban list (applies to ALL orgs)
_GLOBAL_ORG_ID = "__global__"


# ── Default ban words for Indian NGO contexts ────────────────────────────────

DEFAULT_BAN_WORDS: dict[str, list[tuple[str, str]]] = {
    "healthcare": [
        ("sonography", "Sex determination tests are illegal in India (PCPNDT Act)"),
        ("sex determination", "Sex determination is illegal in India"),
        ("gender test", "Prenatal gender testing is prohibited"),
        ("sex selection", "Sex selection is illegal in India (PCPNDT Act)"),
        ("sex test", "Prenatal sex testing is prohibited under PCPNDT Act"),
    ],
}


def _build_word_pattern(word: str) -> re.Pattern:
    """Build a case-insensitive word-boundary regex for a banned word."""
    return re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)


async def load_ban_lists() -> None:
    """Load all org ban lists from database into memory cache."""
    from app import db

    if not db.is_connected():
        logger.info("DB not connected — ban lists not loaded (will use defaults)")
        return

    try:
        rows = await db.load_all_ban_lists()
        _ban_lists.clear()
        for row in rows:
            org_id = row["org_id"]
            if org_id not in _ban_lists:
                _ban_lists[org_id] = []
            _ban_lists[org_id].append({
                "word": row["word"],
                "reason": row.get("reason", ""),
            })
        logger.info(
            "Loaded ban lists for %d org(s), %d total words",
            len(_ban_lists),
            sum(len(v) for v in _ban_lists.values()),
        )
    except Exception as e:
        logger.warning("Failed to load ban lists from DB: %s", e)


def _get_effective_ban_list(org_id: str) -> list[dict[str, str]]:
    """Get the effective ban list for an org (org-specific + global)."""
    result = list(_ban_lists.get(_GLOBAL_ORG_ID, []))
    if org_id and org_id != _GLOBAL_ORG_ID:
        result.extend(_ban_lists.get(org_id, []))
    return result


async def check_ban_list(text: str, org_id: str) -> dict[str, Any]:
    """Check text against an org's ban list.

    Args:
        text: The text to check.
        org_id: The organisation ID for scoped ban list lookup.

    Returns:
        {
            "has_banned": bool,
            "banned_words_found": [{"word": str, "reason": str}],
            "fixed_text": str  # text with banned words replaced by [BANNED]
        }
    """
    if not settings.BAN_LIST_ENABLED:
        return {"has_banned": False, "banned_words_found": [], "fixed_text": text}

    ban_list = _get_effective_ban_list(org_id)
    if not ban_list:
        return {"has_banned": False, "banned_words_found": [], "fixed_text": text}

    banned_found: list[dict[str, str]] = []
    fixed_text = text

    for entry in ban_list:
        word = entry["word"]
        reason = entry.get("reason", "")
        pattern = _build_word_pattern(word)
        if pattern.search(fixed_text):
            banned_found.append({"word": word, "reason": reason})
            fixed_text = pattern.sub("[BANNED]", fixed_text)

    has_banned = len(banned_found) > 0
    if has_banned:
        logger.info(
            "Ban list check for org '%s' found %d banned word(s): %s",
            org_id,
            len(banned_found),
            [b["word"] for b in banned_found],
        )

    return {
        "has_banned": has_banned,
        "banned_words_found": banned_found,
        "fixed_text": fixed_text,
    }


async def add_banned_word(org_id: str, word: str, reason: str = "", created_by: str = "") -> None:
    """Add a word to an org's ban list (DB + cache)."""
    from app import db

    word_lower = word.lower().strip()
    if not word_lower:
        return

    await db.add_ban_word(org_id, word_lower, reason, created_by)

    # Update in-memory cache
    if org_id not in _ban_lists:
        _ban_lists[org_id] = []
    # Avoid duplicates in cache
    if not any(e["word"] == word_lower for e in _ban_lists[org_id]):
        _ban_lists[org_id].append({"word": word_lower, "reason": reason})

    logger.info("Added banned word '%s' for org '%s'", word_lower, org_id)


async def remove_banned_word(org_id: str, word: str) -> None:
    """Remove a word from an org's ban list (DB + cache)."""
    from app import db

    word_lower = word.lower().strip()
    await db.remove_ban_word(org_id, word_lower)

    # Update in-memory cache
    if org_id in _ban_lists:
        _ban_lists[org_id] = [e for e in _ban_lists[org_id] if e["word"] != word_lower]

    logger.info("Removed banned word '%s' for org '%s'", word_lower, org_id)


async def get_ban_list(org_id: str) -> list[dict]:
    """Get the full ban list for an org from database."""
    from app import db

    return await db.get_org_ban_list(org_id)


async def seed_default_ban_lists() -> None:
    """Seed default ban lists for common Indian NGO contexts.

    Only adds words if the global ban list is empty (first-time setup).
    """
    from app import db

    if not db.is_connected():
        return

    existing = await db.get_org_ban_list(_GLOBAL_ORG_ID)
    if existing:
        logger.info("Global ban list already has %d entries, skipping seed", len(existing))
        return

    count = 0
    for _category, words in DEFAULT_BAN_WORDS.items():
        for word, reason in words:
            try:
                await db.add_ban_word(_GLOBAL_ORG_ID, word, reason, "system")
                count += 1
            except Exception as e:
                logger.debug("Seed ban word '%s' failed (may already exist): %s", word, e)

    if count:
        logger.info("Seeded %d default ban words to global ban list", count)

    # Reload cache
    await load_ban_lists()
