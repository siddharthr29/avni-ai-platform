"""Tests for gender bias detection and neutral term substitution.

Covers:
- Generic gendered terms (chairman, businessman, mankind, etc.)
- Healthcare terms (lady doctor, male nurse)
- Education terms (headmaster, schoolmistress)
- Case-preserving replacement
- Multi-word term matching (lady doctor vs doctor)
- Category filtering
- Empty/edge cases
- Pattern map building
"""

import pytest
from unittest.mock import patch

from app.services.gender_bias_guard import (
    GENDER_NEUTRAL_MAP,
    check_gender_bias,
    _build_pattern_map,
)


# ── Generic Category ─────────────────────────────────────────────────────────


class TestGenericGenderBias:
    def test_chairman_to_chairperson(self):
        result = check_gender_bias("The chairman will decide.")
        assert result["has_bias"]
        assert "chairperson" in result["fixed_text"].lower()

    def test_businessman_to_businessperson(self):
        result = check_gender_bias("A businessman visited.")
        assert result["has_bias"]
        assert "businessperson" in result["fixed_text"].lower()

    def test_mankind_to_humanity(self):
        result = check_gender_bias("For the benefit of mankind.")
        assert result["has_bias"]
        assert "humanity" in result["fixed_text"]

    def test_manpower_to_workforce(self):
        result = check_gender_bias("We need more manpower.")
        assert result["has_bias"]
        assert "workforce" in result["fixed_text"]

    def test_housewife_to_homemaker(self):
        result = check_gender_bias("She is a housewife.")
        assert result["has_bias"]
        assert "homemaker" in result["fixed_text"]

    def test_fireman_to_firefighter(self):
        result = check_gender_bias("The fireman arrived.")
        assert result["has_bias"]
        assert "firefighter" in result["fixed_text"]

    def test_policeman_to_police_officer(self):
        result = check_gender_bias("A policeman was present.")
        assert result["has_bias"]
        assert "police officer" in result["fixed_text"]

    def test_stewardess_to_flight_attendant(self):
        result = check_gender_bias("The stewardess served drinks.")
        assert result["has_bias"]
        assert "flight attendant" in result["fixed_text"]

    def test_he_she_to_they(self):
        result = check_gender_bias("He/she should fill the form.")
        assert result["has_bias"]
        assert "they" in result["fixed_text"].lower()

    def test_his_her_to_their(self):
        result = check_gender_bias("Submit his/her report.")
        assert result["has_bias"]
        assert "their" in result["fixed_text"]


# ── Healthcare Category ──────────────────────────────────────────────────────


class TestHealthcareGenderBias:
    def test_lady_doctor_to_doctor(self):
        result = check_gender_bias("The lady doctor examined the patient.")
        assert result["has_bias"]
        subs = result["substitutions"]
        assert any(s["original"] == "lady doctor" for s in subs)
        assert "lady doctor" not in result["fixed_text"].lower()

    def test_male_nurse_to_nurse(self):
        result = check_gender_bias("The male nurse administered the vaccine.")
        assert result["has_bias"]
        assert "male nurse" not in result["fixed_text"].lower()

    def test_cleaning_lady_to_cleaner(self):
        result = check_gender_bias("The cleaning lady will come.")
        assert result["has_bias"]
        assert "cleaner" in result["fixed_text"]


# ── Education Category ──────────────────────────────────────────────────────


class TestEducationGenderBias:
    def test_headmaster_to_head_teacher(self):
        result = check_gender_bias("The headmaster spoke.")
        assert result["has_bias"]
        assert "head teacher" in result["fixed_text"]

    def test_headmistress_to_head_teacher(self):
        result = check_gender_bias("The headmistress spoke.")
        assert result["has_bias"]
        assert "head teacher" in result["fixed_text"]

    def test_schoolmaster_to_teacher(self):
        result = check_gender_bias("The schoolmaster taught class.")
        assert result["has_bias"]
        assert "teacher" in result["fixed_text"]


# ── Case Preservation ────────────────────────────────────────────────────────


class TestCasePreservation:
    def test_capitalized_word_preserved(self):
        result = check_gender_bias("The Chairman called the meeting.")
        assert "Chairperson" in result["fixed_text"]

    def test_lowercase_word_stays_lowercase(self):
        result = check_gender_bias("the chairman called.")
        assert "chairperson" in result["fixed_text"]

    def test_uppercase_first_char(self):
        result = check_gender_bias("Businessman Smith arrived.")
        assert "Businessperson" in result["fixed_text"]

    def test_all_caps_preserved(self):
        """ALL CAPS input should produce ALL CAPS output."""
        result = check_gender_bias("THE BUSINESSMAN ARRIVED.")
        assert "BUSINESSPERSON" in result["fixed_text"]

    def test_all_caps_chairman(self):
        result = check_gender_bias("CHAIRMAN OF THE BOARD")
        assert "CHAIRPERSON" in result["fixed_text"]


# ── Multiple Substitutions ───────────────────────────────────────────────────


class TestMultipleSubstitutions:
    def test_multiple_terms_in_text(self):
        result = check_gender_bias("The chairman and the businessman discussed.")
        assert result["has_bias"]
        assert len(result["substitutions"]) >= 2

    def test_same_word_multiple_times(self):
        result = check_gender_bias("The chairman told the chairman to chair.")
        assert result["has_bias"]
        subs = [s for s in result["substitutions"] if s["original"] == "chairman"]
        assert subs[0]["count"] >= 2

    def test_substitutions_have_correct_structure(self):
        result = check_gender_bias("The chairman spoke.")
        assert result["has_bias"]
        sub = result["substitutions"][0]
        assert "original" in sub
        assert "neutral" in sub
        assert "category" in sub
        assert "count" in sub


# ── Category Filtering ───────────────────────────────────────────────────────


class TestCategoryFiltering:
    def test_only_generic_category(self):
        result = check_gender_bias("The headmaster and chairman met.", categories=["generic"])
        # headmaster is education, not generic — should not be detected
        subs = result["substitutions"]
        assert any(s["original"] == "chairman" for s in subs)
        assert not any(s["original"] == "headmaster" for s in subs)

    def test_only_healthcare_category(self):
        result = check_gender_bias("The chairman and lady doctor met.", categories=["healthcare"])
        subs = result["substitutions"]
        assert any(s["original"] == "lady doctor" for s in subs)
        assert not any(s["original"] == "chairman" for s in subs)

    def test_empty_categories_no_bias(self):
        result = check_gender_bias("The chairman spoke.", categories=[])
        assert not result["has_bias"]

    def test_invalid_category_ignored(self):
        result = check_gender_bias("The chairman spoke.", categories=["invalid"])
        assert not result["has_bias"]


# ── Edge Cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_text(self):
        result = check_gender_bias("")
        assert not result["has_bias"]
        assert result["fixed_text"] == ""

    def test_no_gendered_language(self):
        result = check_gender_bias("The team reviewed the form.")
        assert not result["has_bias"]
        assert result["fixed_text"] == "The team reviewed the form."

    def test_word_boundary_prevents_partial_match(self):
        """'man' inside 'management' should NOT trigger."""
        result = check_gender_bias("The management team met.")
        subs = [s for s in result["substitutions"] if s["original"] == "man"]
        assert len(subs) == 0 or not result["has_bias"]

    def test_multi_word_term_priority(self):
        """'lady doctor' should match before 'lady' alone."""
        result = check_gender_bias("The lady doctor is here.")
        subs = result["substitutions"]
        # Should have 'lady doctor' -> 'doctor', not 'lady' alone
        assert any(s["original"] == "lady doctor" for s in subs)

    def test_disabled_returns_original(self):
        with patch("app.services.gender_bias_guard.settings") as mock:
            mock.GENDER_BIAS_CHECK_ENABLED = False
            result = check_gender_bias("The chairman spoke.")
            assert not result["has_bias"]
            assert result["fixed_text"] == "The chairman spoke."


# ── Pattern Map Building ─────────────────────────────────────────────────────


class TestBuildPatternMap:
    def test_sorted_by_length_descending(self):
        """Multi-word terms should come before single-word terms."""
        pattern_map = _build_pattern_map(["generic", "healthcare"])
        entries = list(pattern_map.values())
        # Check that longer terms appear first
        for i in range(len(entries) - 1):
            assert len(entries[i][0]) >= len(entries[i + 1][0])

    def test_all_categories_loaded(self):
        pattern_map = _build_pattern_map(["generic", "healthcare", "education"])
        total = sum(len(m) for m in GENDER_NEUTRAL_MAP.values())
        assert len(pattern_map) == total

    def test_empty_category_list(self):
        pattern_map = _build_pattern_map([])
        assert len(pattern_map) == 0


# ── Data Integrity ───────────────────────────────────────────────────────────


class TestDataIntegrity:
    def test_all_categories_exist(self):
        assert "generic" in GENDER_NEUTRAL_MAP
        assert "healthcare" in GENDER_NEUTRAL_MAP
        assert "education" in GENDER_NEUTRAL_MAP

    def test_generic_has_reasonable_count(self):
        assert len(GENDER_NEUTRAL_MAP["generic"]) >= 20

    def test_no_empty_values(self):
        for cat, mapping in GENDER_NEUTRAL_MAP.items():
            for gendered, neutral in mapping.items():
                assert gendered.strip(), f"Empty key in {cat}"
                assert neutral.strip(), f"Empty value for '{gendered}' in {cat}"
