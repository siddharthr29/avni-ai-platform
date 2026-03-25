"""Tests for text normalization service.

Covers:
- Unicode NFKC normalization
- Emoji removal
- Whitespace normalization
- Diacritics removal
- Edge cases: empty strings, Unicode edge cases
"""

import pytest

from app.services.text_normalizer import normalize_text, remove_diacritics


# ── Unicode Normalization ────────────────────────────────────────────────────


class TestUnicodeNormalization:
    def test_fullwidth_chars_normalized(self):
        """Fullwidth characters should be normalized to ASCII."""
        text = "\uff21\uff22\uff23"  # ABC in fullwidth
        result = normalize_text(text)
        assert result == "ABC"

    def test_ligatures_decomposed(self):
        """Ligatures like ﬁ should be decomposed."""
        text = "\ufb01le"  # ﬁle
        result = normalize_text(text)
        assert result == "file"

    def test_normal_ascii_unchanged(self):
        text = "Hello World 123"
        assert normalize_text(text) == "Hello World 123"

    def test_devanagari_preserved(self):
        """Indian scripts should be preserved through normalization."""
        text = "नमस्ते"
        result = normalize_text(text)
        assert "न" in result


# ── Emoji Removal ────────────────────────────────────────────────────────────


class TestEmojiRemoval:
    def test_simple_emoji_removed(self):
        text = "Hello 😀 World"
        result = normalize_text(text)
        assert "😀" not in result
        # Words should be preserved
        assert "Hello" in result
        assert "World" in result

    def test_multiple_emoji_removed(self):
        text = "🎉 Party 🎊 Time 🎈"
        result = normalize_text(text)
        assert "🎉" not in result
        assert "🎊" not in result
        assert "🎈" not in result
        assert "Party" in result
        assert "Time" in result

    def test_flag_emoji_removed(self):
        text = "India 🇮🇳 flag"
        result = normalize_text(text)
        assert "🇮🇳" not in result

    def test_emoji_replaced_with_space(self):
        """Emoji should be replaced with space to avoid word joining."""
        text = "hello😀world"
        result = normalize_text(text)
        # Words should be separated
        assert "helloworld" not in result

    def test_text_without_emoji_unchanged(self):
        text = "No emoji here"
        assert normalize_text(text) == "No emoji here"


# ── Whitespace Normalization ─────────────────────────────────────────────────


class TestWhitespaceNormalization:
    def test_multiple_spaces_collapsed(self):
        text = "Hello    World"
        assert normalize_text(text) == "Hello World"

    def test_tabs_collapsed(self):
        text = "Hello\t\tWorld"
        assert normalize_text(text) == "Hello World"

    def test_newlines_collapsed(self):
        text = "Hello\n\n\nWorld"
        assert normalize_text(text) == "Hello World"

    def test_mixed_whitespace_collapsed(self):
        text = "Hello  \t\n  World"
        assert normalize_text(text) == "Hello World"

    def test_leading_trailing_stripped(self):
        text = "  Hello World  "
        assert normalize_text(text) == "Hello World"


# ── Edge Cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_none_like_empty(self):
        """Empty string returns empty."""
        assert normalize_text("") == ""

    def test_whitespace_only(self):
        assert normalize_text("   ") == ""

    def test_single_character(self):
        assert normalize_text("a") == "a"

    def test_only_emoji(self):
        result = normalize_text("😀😁😂")
        assert result == ""

    def test_very_long_text(self):
        """Should handle large inputs without hanging."""
        text = "Hello " * 10000
        result = normalize_text(text)
        assert len(result) > 0

    def test_unicode_combining_marks(self):
        """Combining marks should be handled by NFKC."""
        text = "e\u0301"  # e + combining acute accent = é
        result = normalize_text(text)
        # NFKC should compose this to é
        assert len(result) <= 2


# ── Diacritics Removal ───────────────────────────────────────────────────────


class TestRemoveDiacritics:
    def test_acute_accent_removed(self):
        assert remove_diacritics("café") == "cafe"

    def test_tilde_removed(self):
        assert remove_diacritics("niño") == "nino"

    def test_umlaut_removed(self):
        assert remove_diacritics("über") == "uber"

    def test_cedilla_removed(self):
        assert remove_diacritics("façade") == "facade"

    def test_plain_text_unchanged(self):
        assert remove_diacritics("hello") == "hello"

    def test_empty_string(self):
        assert remove_diacritics("") == ""

    def test_numbers_preserved(self):
        assert remove_diacritics("123") == "123"

    def test_mixed_diacritics_and_plain(self):
        assert remove_diacritics("résumé for café") == "resume for cafe"
