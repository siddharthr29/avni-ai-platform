"""Tests for per-org ban list service.

Covers:
- Ban list matching with word boundaries
- Case-insensitive matching
- Replacement with [BANNED] placeholder
- Effective ban list (org-specific + global)
- Cache operations (add, remove, dedup)
- Default ban words for Indian healthcare contexts
- Edge cases: empty text, empty ban list, special characters
"""

import pytest
from unittest.mock import patch, AsyncMock

from app.services.ban_list import (
    _build_word_pattern,
    _get_effective_ban_list,
    check_ban_list,
    add_banned_word,
    remove_banned_word,
    DEFAULT_BAN_WORDS,
    _ban_lists,
    _GLOBAL_ORG_ID,
)


# ── Word Pattern Building ────────────────────────────────────────────────────


class TestBuildWordPattern:
    def test_matches_exact_word(self):
        pattern = _build_word_pattern("sonography")
        assert pattern.search("The sonography was done.")

    def test_case_insensitive(self):
        pattern = _build_word_pattern("sonography")
        assert pattern.search("SONOGRAPHY results")

    def test_word_boundary_left(self):
        """Should not match inside other words."""
        pattern = _build_word_pattern("son")
        # 'son' should match as standalone but not inside 'sonography'
        assert pattern.search("her son is here")
        # This tests word boundary — 'son' in 'sonography' should match
        # because \bson\b won't match inside 'sonography' (no right boundary)

    def test_word_boundary_right(self):
        pattern = _build_word_pattern("test")
        assert pattern.search("run test now")
        # 'test' inside 'testing' — \btest\b should NOT match 'testing'
        assert not pattern.search("testing phase")

    def test_multi_word_pattern(self):
        pattern = _build_word_pattern("sex determination")
        assert pattern.search("about sex determination tests")

    def test_special_characters_escaped(self):
        """Regex special chars in ban words should be escaped."""
        pattern = _build_word_pattern("test+case")
        assert pattern.search("this is a test+case here")
        # Should not treat + as regex quantifier
        assert not pattern.search("testttcase")


# ── Effective Ban List ───────────────────────────────────────────────────────


class TestEffectiveBanList:
    def setup_method(self):
        """Set up fresh ban list cache for each test."""
        _ban_lists.clear()

    def test_global_words_included(self):
        _ban_lists[_GLOBAL_ORG_ID] = [{"word": "global_banned", "reason": "test"}]
        result = _get_effective_ban_list("org-1")
        assert any(e["word"] == "global_banned" for e in result)

    def test_org_specific_words_included(self):
        _ban_lists["org-1"] = [{"word": "org_banned", "reason": "test"}]
        result = _get_effective_ban_list("org-1")
        assert any(e["word"] == "org_banned" for e in result)

    def test_global_plus_org_combined(self):
        _ban_lists[_GLOBAL_ORG_ID] = [{"word": "global", "reason": ""}]
        _ban_lists["org-1"] = [{"word": "local", "reason": ""}]
        result = _get_effective_ban_list("org-1")
        assert len(result) == 2

    def test_empty_org_only_global(self):
        _ban_lists[_GLOBAL_ORG_ID] = [{"word": "global", "reason": ""}]
        result = _get_effective_ban_list("org-unknown")
        assert len(result) == 1

    def test_no_ban_lists_returns_empty(self):
        result = _get_effective_ban_list("org-1")
        assert result == []

    def test_global_org_id_not_duplicated(self):
        """Requesting ban list for __global__ should not duplicate."""
        _ban_lists[_GLOBAL_ORG_ID] = [{"word": "test", "reason": ""}]
        result = _get_effective_ban_list(_GLOBAL_ORG_ID)
        assert len(result) == 1

    def teardown_method(self):
        _ban_lists.clear()


# ── check_ban_list ───────────────────────────────────────────────────────────


class TestCheckBanList:
    def setup_method(self):
        _ban_lists.clear()

    @pytest.mark.asyncio
    async def test_banned_word_detected(self):
        _ban_lists["org-1"] = [{"word": "sonography", "reason": "PCPNDT Act"}]
        result = await check_ban_list("Schedule a sonography scan.", "org-1")
        assert result["has_banned"]
        assert len(result["banned_words_found"]) == 1
        assert result["banned_words_found"][0]["word"] == "sonography"

    @pytest.mark.asyncio
    async def test_banned_word_replaced(self):
        _ban_lists["org-1"] = [{"word": "sonography", "reason": "PCPNDT Act"}]
        result = await check_ban_list("Schedule a sonography scan.", "org-1")
        assert "[BANNED]" in result["fixed_text"]
        assert "sonography" not in result["fixed_text"].lower()

    @pytest.mark.asyncio
    async def test_no_banned_words(self):
        _ban_lists["org-1"] = [{"word": "sonography", "reason": "PCPNDT Act"}]
        result = await check_ban_list("Schedule an ultrasound scan.", "org-1")
        assert not result["has_banned"]
        assert result["fixed_text"] == "Schedule an ultrasound scan."

    @pytest.mark.asyncio
    async def test_multiple_banned_words(self):
        _ban_lists["org-1"] = [
            {"word": "sonography", "reason": "PCPNDT Act"},
            {"word": "sex determination", "reason": "Illegal"},
        ]
        text = "Do a sonography for sex determination."
        result = await check_ban_list(text, "org-1")
        assert result["has_banned"]
        assert len(result["banned_words_found"]) == 2

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(self):
        _ban_lists["org-1"] = [{"word": "sonography", "reason": "test"}]
        result = await check_ban_list("SONOGRAPHY report", "org-1")
        assert result["has_banned"]

    @pytest.mark.asyncio
    async def test_empty_text(self):
        _ban_lists["org-1"] = [{"word": "test", "reason": ""}]
        result = await check_ban_list("", "org-1")
        assert not result["has_banned"]

    @pytest.mark.asyncio
    async def test_empty_ban_list(self):
        result = await check_ban_list("Any text here.", "org-no-list")
        assert not result["has_banned"]

    @pytest.mark.asyncio
    async def test_disabled_returns_clean(self):
        with patch("app.services.ban_list.settings") as mock:
            mock.BAN_LIST_ENABLED = False
            _ban_lists["org-1"] = [{"word": "test", "reason": ""}]
            result = await check_ban_list("test text", "org-1")
            assert not result["has_banned"]

    def teardown_method(self):
        _ban_lists.clear()


# ── Cache Operations ─────────────────────────────────────────────────────────


class TestCacheOperations:
    def setup_method(self):
        _ban_lists.clear()

    @pytest.mark.asyncio
    async def test_add_updates_cache(self):
        import app.db as db_mod
        with patch.object(db_mod, "add_ban_word", new_callable=AsyncMock):
            await add_banned_word("org-1", "BadWord", "reason")
            assert "org-1" in _ban_lists
            assert any(e["word"] == "badword" for e in _ban_lists["org-1"])

    @pytest.mark.asyncio
    async def test_add_lowercases(self):
        import app.db as db_mod
        with patch.object(db_mod, "add_ban_word", new_callable=AsyncMock):
            await add_banned_word("org-1", "UPPERCASE", "reason")
            assert any(e["word"] == "uppercase" for e in _ban_lists["org-1"])

    @pytest.mark.asyncio
    async def test_add_strips_whitespace(self):
        import app.db as db_mod
        with patch.object(db_mod, "add_ban_word", new_callable=AsyncMock):
            await add_banned_word("org-1", "  spaced  ", "reason")
            assert any(e["word"] == "spaced" for e in _ban_lists["org-1"])

    @pytest.mark.asyncio
    async def test_add_empty_word_ignored(self):
        import app.db as db_mod
        with patch.object(db_mod, "add_ban_word", new_callable=AsyncMock):
            await add_banned_word("org-1", "", "reason")
            assert "org-1" not in _ban_lists

    @pytest.mark.asyncio
    async def test_add_duplicate_not_cached_twice(self):
        import app.db as db_mod
        with patch.object(db_mod, "add_ban_word", new_callable=AsyncMock):
            await add_banned_word("org-1", "word", "r1")
            await add_banned_word("org-1", "word", "r2")
            assert len(_ban_lists["org-1"]) == 1

    @pytest.mark.asyncio
    async def test_remove_updates_cache(self):
        _ban_lists["org-1"] = [{"word": "banned", "reason": "test"}]
        import app.db as db_mod
        with patch.object(db_mod, "remove_ban_word", new_callable=AsyncMock):
            await remove_banned_word("org-1", "Banned")
            assert not any(e["word"] == "banned" for e in _ban_lists["org-1"])

    @pytest.mark.asyncio
    async def test_remove_nonexistent_word_safe(self):
        import app.db as db_mod
        with patch.object(db_mod, "remove_ban_word", new_callable=AsyncMock):
            await remove_banned_word("org-1", "nonexistent")
            # Should not crash

    def teardown_method(self):
        _ban_lists.clear()


# ── Default Ban Words ────────────────────────────────────────────────────────


class TestDefaultBanWords:
    def test_healthcare_defaults_exist(self):
        assert "healthcare" in DEFAULT_BAN_WORDS
        words = DEFAULT_BAN_WORDS["healthcare"]
        assert len(words) >= 3

    def test_sonography_in_defaults(self):
        words = [w for w, r in DEFAULT_BAN_WORDS["healthcare"]]
        assert "sonography" in words

    def test_sex_determination_in_defaults(self):
        words = [w for w, r in DEFAULT_BAN_WORDS["healthcare"]]
        assert "sex determination" in words

    def test_all_defaults_have_reasons(self):
        for category, words in DEFAULT_BAN_WORDS.items():
            for word, reason in words:
                assert reason.strip(), f"Empty reason for '{word}' in {category}"
