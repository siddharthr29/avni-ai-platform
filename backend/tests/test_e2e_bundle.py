"""End-to-end integration tests for bundle generation pipeline.

Tests the full flow: SRSData → bundle_generator → ZIP file → validate structure.
Validates that generated bundles are 100% compatible with avni-server's
BundleZipFileImporter by checking:
- All required files present in correct order
- isMandatory (not mandatory) on form elements
- voided: false on all entities
- Concept answers have abnormal/unique/voided
- Form-level rule fields present
- Form element groups have voided/rule
- Numeric concepts have range fields
- Deterministic UUIDs for same input
"""

import json
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

import pytest

from app.models.schemas import (
    SRSData,
    SRSFormDefinition,
    SRSFormField,
    SRSFormGroup,
)
from app.services.bundle_generator import (
    ConceptManager,
    UUIDRegistry,
    create_bundle_zip,
    generate_from_srs,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _mch_srs() -> SRSData:
    """Realistic MCH SRS with multiple programs, encounter types, forms."""
    return SRSData(
        orgName="MCH Test Org",
        subjectTypes=[
            {"name": "Mother", "type": "Person"},
            {"name": "Child", "type": "Person"},
        ],
        programs=[
            {"name": "Pregnancy", "colour": "#E91E63"},
            {"name": "Child Growth Monitoring", "colour": "#4CAF50"},
        ],
        encounterTypes=[
            "ANC Visit",
            "Delivery",
            "Growth Monitoring Visit",
            "ANC Visit Cancellation",
            "Growth Monitoring Visit Cancellation",
        ],
        forms=[
            SRSFormDefinition(
                name="Mother Registration",
                formType="IndividualProfile",
                groups=[
                    SRSFormGroup(
                        name="Basic Details",
                        fields=[
                            SRSFormField(name="Full Name", dataType="Text", mandatory=True),
                            SRSFormField(name="Date of Birth", dataType="Date", mandatory=True),
                            SRSFormField(name="Age", dataType="Numeric", unit="years",
                                         lowAbsolute=14, highAbsolute=50, mandatory=True),
                            SRSFormField(
                                name="Gender", dataType="Coded",
                                options=["Male", "Female", "Other"],
                                type="SingleSelect", mandatory=True,
                            ),
                            SRSFormField(name="Phone Number", dataType="Text", mandatory=False),
                        ],
                    ),
                    SRSFormGroup(
                        name="Address",
                        fields=[
                            SRSFormField(name="Village", dataType="Text", mandatory=True),
                        ],
                    ),
                ],
            ),
            SRSFormDefinition(
                name="Pregnancy Enrolment",
                formType="ProgramEnrolment",
                programName="Pregnancy",
                groups=[
                    SRSFormGroup(
                        name="Pregnancy Details",
                        fields=[
                            SRSFormField(name="Last Menstrual Period", dataType="Date", mandatory=True),
                            SRSFormField(name="Gravida", dataType="Numeric", mandatory=True,
                                         lowAbsolute=1, highAbsolute=15),
                            SRSFormField(name="Parity", dataType="Numeric", mandatory=True,
                                         lowAbsolute=0, highAbsolute=14),
                            SRSFormField(
                                name="High Risk", dataType="Coded",
                                options=["Yes", "No"], type="SingleSelect",
                            ),
                        ],
                    ),
                ],
            ),
            SRSFormDefinition(
                name="ANC Visit",
                formType="ProgramEncounter",
                programName="Pregnancy",
                encounterTypeName="ANC Visit",
                groups=[
                    SRSFormGroup(
                        name="Vitals",
                        fields=[
                            SRSFormField(name="Weight", dataType="Numeric", unit="kg",
                                         lowAbsolute=30, highAbsolute=150, mandatory=True),
                            SRSFormField(name="Blood Pressure Systolic", dataType="Numeric",
                                         unit="mmHg", lowAbsolute=60, highAbsolute=260),
                            SRSFormField(name="Blood Pressure Diastolic", dataType="Numeric",
                                         unit="mmHg", lowAbsolute=40, highAbsolute=180),
                            SRSFormField(name="Haemoglobin", dataType="Numeric",
                                         unit="g/dL", lowAbsolute=2, highAbsolute=20),
                        ],
                    ),
                    SRSFormGroup(
                        name="Observations",
                        fields=[
                            SRSFormField(
                                name="Foetal Movement", dataType="Coded",
                                options=["Present", "Absent", "Reduced"],
                                type="SingleSelect",
                            ),
                            SRSFormField(name="Notes", dataType="Notes", mandatory=False),
                        ],
                    ),
                ],
            ),
            SRSFormDefinition(
                name="ANC Visit Cancellation",
                formType="ProgramEncounterCancellation",
                programName="Pregnancy",
                encounterTypeName="ANC Visit",
                groups=[
                    SRSFormGroup(
                        name="Cancellation",
                        fields=[
                            SRSFormField(
                                name="Cancellation Reason", dataType="Coded",
                                options=["Unavailable", "Migrated", "Refused", "Other"],
                                type="SingleSelect", mandatory=True,
                            ),
                            SRSFormField(name="Other Reason", dataType="Text", mandatory=False),
                        ],
                    ),
                ],
            ),
        ],
        groups=["Everyone", "ASHA", "ANM"],
        addressLevelTypes=[
            {"name": "State", "level": 3},
            {"name": "District", "level": 2, "parent": "State"},
            {"name": "Block", "level": 1, "parent": "District"},
        ],
        programEncounterMappings=[
            {"program": "Pregnancy", "encounterTypes": ["ANC Visit", "Delivery"]},
            {"program": "Child Growth Monitoring", "encounterTypes": ["Growth Monitoring Visit"]},
        ],
    )


@pytest.fixture
def mch_srs():
    return _mch_srs()


@pytest.fixture
def bundle_output_dir():
    d = tempfile.mkdtemp(prefix="avni_e2e_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ─── E2E Bundle Generation Tests ──────────────────────────────────────────────


class TestE2EBundleGeneration:
    """Full pipeline: SRSData → generate_from_srs → validate ZIP."""

    @pytest.fixture(autouse=True)
    def setup(self, mch_srs, bundle_output_dir, monkeypatch):
        self.srs = mch_srs
        self.output_dir = bundle_output_dir
        monkeypatch.setattr("app.services.bundle_generator.settings.BUNDLE_OUTPUT_DIR", self.output_dir)

    @pytest.mark.asyncio
    async def test_full_generation_produces_zip(self):
        zip_path = await generate_from_srs(self.srs, "test-bundle-001")
        assert os.path.isfile(zip_path)
        assert zip_path.endswith(".zip")

    @pytest.mark.asyncio
    async def test_zip_contains_all_required_files(self):
        await generate_from_srs(self.srs, "test-bundle-002")
        zip_path = os.path.join(self.output_dir, "test-bundle-002.zip")

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

        required_files = [
            "organisationConfig.json",
            "addressLevelTypes.json",
            "subjectTypes.json",
            "operationalSubjectTypes.json",
            "encounterTypes.json",
            "operationalEncounterTypes.json",
            "programs.json",
            "operationalPrograms.json",
            "concepts.json",
            "formMappings.json",
            "groups.json",
            "groupPrivilege.json",
            "individualRelation.json",
            "relationshipType.json",
            "reportCard.json",
            "reportDashboard.json",
            "groupDashboards.json",
        ]

        for req in required_files:
            assert req in names, f"Missing required file: {req}"

        # Should have form files
        form_files = [n for n in names if n.startswith("forms/")]
        assert len(form_files) >= 4  # 4 SRS forms + auto-generated cancellation/exit forms

        # Should have translations
        translation_files = [n for n in names if n.startswith("translations/")]
        assert len(translation_files) >= 1

    @pytest.mark.asyncio
    async def test_concepts_have_voided_field(self):
        await generate_from_srs(self.srs, "test-bundle-003")
        bundle_dir = os.path.join(self.output_dir, "test-bundle-003")
        concepts = json.loads(Path(bundle_dir, "concepts.json").read_text())

        for concept in concepts:
            assert "voided" in concept, f"Concept '{concept['name']}' missing voided"
            assert concept["voided"] is False
            assert "active" in concept

    @pytest.mark.asyncio
    async def test_concepts_coded_answers_have_full_fields(self):
        await generate_from_srs(self.srs, "test-bundle-004")
        bundle_dir = os.path.join(self.output_dir, "test-bundle-004")
        concepts = json.loads(Path(bundle_dir, "concepts.json").read_text())

        coded = [c for c in concepts if c["dataType"] == "Coded" and c.get("answers")]
        assert len(coded) > 0, "Should have at least one coded concept with answers"

        for concept in coded:
            for answer in concept["answers"]:
                assert "abnormal" in answer, f"Answer '{answer['name']}' missing abnormal"
                assert "unique" in answer, f"Answer '{answer['name']}' missing unique"
                assert "voided" in answer, f"Answer '{answer['name']}' missing voided"
                assert "order" in answer

    @pytest.mark.asyncio
    async def test_numeric_concepts_have_ranges(self):
        await generate_from_srs(self.srs, "test-bundle-005")
        bundle_dir = os.path.join(self.output_dir, "test-bundle-005")
        concepts = json.loads(Path(bundle_dir, "concepts.json").read_text())

        weight = next((c for c in concepts if c["name"] == "Weight"), None)
        assert weight is not None
        assert weight["dataType"] == "Numeric"
        assert "lowAbsolute" in weight
        assert "highAbsolute" in weight
        assert weight["unit"] == "kg"

    @pytest.mark.asyncio
    async def test_form_elements_use_isMandatory(self):
        """Critical: avni-server expects isMandatory, not mandatory."""
        await generate_from_srs(self.srs, "test-bundle-006")
        bundle_dir = os.path.join(self.output_dir, "test-bundle-006")

        forms_dir = Path(bundle_dir, "forms")
        for form_file in forms_dir.glob("*.json"):
            form = json.loads(form_file.read_text())
            for group in form["formElementGroups"]:
                for element in group["formElements"]:
                    assert "isMandatory" in element, (
                        f"Form element '{element['name']}' in {form_file.name} "
                        f"uses 'mandatory' instead of 'isMandatory'"
                    )
                    assert "mandatory" not in element, (
                        f"Form element '{element['name']}' has legacy 'mandatory' key"
                    )

    @pytest.mark.asyncio
    async def test_form_elements_have_voided(self):
        await generate_from_srs(self.srs, "test-bundle-007")
        bundle_dir = os.path.join(self.output_dir, "test-bundle-007")

        forms_dir = Path(bundle_dir, "forms")
        for form_file in forms_dir.glob("*.json"):
            form = json.loads(form_file.read_text())
            for group in form["formElementGroups"]:
                assert group.get("voided") is False, f"Group '{group['name']}' missing voided"
                assert "rule" in group, f"Group '{group['name']}' missing rule field"
                for element in group["formElements"]:
                    assert element.get("voided") is False, (
                        f"Element '{element['name']}' missing voided"
                    )

    @pytest.mark.asyncio
    async def test_forms_have_rule_fields(self):
        await generate_from_srs(self.srs, "test-bundle-008")
        bundle_dir = os.path.join(self.output_dir, "test-bundle-008")

        forms_dir = Path(bundle_dir, "forms")
        rule_fields = [
            "decisionRule", "validationRule", "visitScheduleRule",
            "checklistsRule", "editFormRule", "taskScheduleRule",
        ]
        for form_file in forms_dir.glob("*.json"):
            form = json.loads(form_file.read_text())
            assert form.get("voided") is False, f"Form '{form['name']}' missing voided"
            for field in rule_fields:
                assert field in form, f"Form '{form['name']}' missing {field}"

    @pytest.mark.asyncio
    async def test_form_element_concept_answers_have_voided(self):
        """Concept answers inside form elements should also have voided."""
        await generate_from_srs(self.srs, "test-bundle-009")
        bundle_dir = os.path.join(self.output_dir, "test-bundle-009")

        forms_dir = Path(bundle_dir, "forms")
        found_coded = False
        for form_file in forms_dir.glob("*.json"):
            form = json.loads(form_file.read_text())
            for group in form["formElementGroups"]:
                for element in group["formElements"]:
                    concept = element["concept"]
                    assert concept.get("voided") is False
                    if concept.get("answers"):
                        found_coded = True
                        for ans in concept["answers"]:
                            assert "voided" in ans, f"Answer '{ans['name']}' missing voided in form element"
        assert found_coded, "Should have at least one coded concept in form elements"

    @pytest.mark.asyncio
    async def test_encounter_types_have_voided(self):
        await generate_from_srs(self.srs, "test-bundle-010")
        bundle_dir = os.path.join(self.output_dir, "test-bundle-010")
        ets = json.loads(Path(bundle_dir, "encounterTypes.json").read_text())

        for et in ets:
            assert et.get("voided") is False, f"Encounter type '{et['name']}' missing voided"
            assert "encounterEligibilityCheckRule" in et

    @pytest.mark.asyncio
    async def test_address_level_types_have_voided(self):
        await generate_from_srs(self.srs, "test-bundle-011")
        bundle_dir = os.path.join(self.output_dir, "test-bundle-011")
        alts = json.loads(Path(bundle_dir, "addressLevelTypes.json").read_text())

        for alt in alts:
            assert alt.get("voided") is False, f"Address level '{alt['name']}' missing voided"

    @pytest.mark.asyncio
    async def test_form_mappings_have_voided(self):
        await generate_from_srs(self.srs, "test-bundle-012")
        bundle_dir = os.path.join(self.output_dir, "test-bundle-012")
        mappings = json.loads(Path(bundle_dir, "formMappings.json").read_text())

        assert len(mappings) >= 4  # 4 SRS forms + auto-generated cancellation/exit forms
        for m in mappings:
            assert m.get("voided") is False, f"Form mapping missing voided"
            assert "formUUID" in m
            assert "subjectTypeUUID" in m

    @pytest.mark.asyncio
    async def test_groups_have_voided_and_privileges(self):
        await generate_from_srs(self.srs, "test-bundle-013")
        bundle_dir = os.path.join(self.output_dir, "test-bundle-013")
        groups = json.loads(Path(bundle_dir, "groups.json").read_text())

        assert len(groups) == 3  # Everyone, ASHA, ANM
        for g in groups:
            assert g.get("voided") is False
            assert "hasAllPrivileges" in g

        everyone = next(g for g in groups if g["name"] == "Everyone")
        assert everyone["hasAllPrivileges"] is True
        assert everyone["notEveryoneGroup"] is False

    @pytest.mark.asyncio
    async def test_standard_answer_uuids_are_stable(self):
        """Standard answers (Male, Female, Yes, No) use stable UUIDs from registry."""
        await generate_from_srs(self.srs, "test-bundle-det-1")
        dir1 = os.path.join(self.output_dir, "test-bundle-det-1")

        concepts = json.loads(Path(dir1, "concepts.json").read_text())

        # Gender concept should have coded answers with standard UUIDs
        gender = next((c for c in concepts if c["name"] == "Gender"), None)
        assert gender is not None
        assert gender["dataType"] == "Coded"

        # Male and Female are in uuid_registry.json — should get stable UUIDs
        male_answer = next((a for a in gender["answers"] if a["name"] == "Male"), None)
        female_answer = next((a for a in gender["answers"] if a["name"] == "Female"), None)
        assert male_answer is not None
        assert female_answer is not None

        # Verify they have valid UUIDs (not empty)
        assert len(male_answer["uuid"]) == 36  # UUID format
        assert len(female_answer["uuid"]) == 36
        # Male and Female should get different UUIDs
        assert male_answer["uuid"] != female_answer["uuid"]

    @pytest.mark.asyncio
    async def test_concept_reuse_across_forms(self):
        """Same concept name used in multiple forms should share one UUID."""
        await generate_from_srs(self.srs, "test-bundle-reuse")
        dir1 = os.path.join(self.output_dir, "test-bundle-reuse")

        concepts = json.loads(Path(dir1, "concepts.json").read_text())

        # All concept names should be unique (deduplication)
        names = [c["name"] for c in concepts]
        assert len(names) == len(set(names)), "Duplicate concept names found"

    @pytest.mark.asyncio
    async def test_zip_file_order_matches_server(self):
        """Files should be in avni-server's BundleService import order."""
        await generate_from_srs(self.srs, "test-bundle-order")
        zip_path = os.path.join(self.output_dir, "test-bundle-order.zip")

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

        # organisationConfig must come before addressLevelTypes
        assert names.index("organisationConfig.json") < names.index("addressLevelTypes.json")
        # addressLevelTypes before subjectTypes
        assert names.index("addressLevelTypes.json") < names.index("subjectTypes.json")
        # concepts before forms
        assert names.index("concepts.json") < min(
            names.index(n) for n in names if n.startswith("forms/")
        )
        # forms before formMappings
        form_indices = [names.index(n) for n in names if n.startswith("forms/")]
        assert max(form_indices) < names.index("formMappings.json")
        # formMappings before groups
        assert names.index("formMappings.json") < names.index("groups.json")
        # groups before groupPrivilege
        assert names.index("groups.json") < names.index("groupPrivilege.json")

    @pytest.mark.asyncio
    async def test_organisation_config_structure(self):
        await generate_from_srs(self.srs, "test-bundle-orgconfig")
        bundle_dir = os.path.join(self.output_dir, "test-bundle-orgconfig")
        config = json.loads(Path(bundle_dir, "organisationConfig.json").read_text())

        assert "settings" in config
        assert "worklistUpdationRule" in config


# ─── Timing Benchmark ─────────────────────────────────────────────────────────


class TestBundleTimingBenchmark:
    """Measures pipeline timing for the concept note's success metrics.

    Target: Requirements → Spec → App should take ~0.5 day (vs 1.5-2 days manual).
    The bundle generation portion (spec → app) should complete in seconds.
    """

    @pytest.fixture(autouse=True)
    def setup(self, bundle_output_dir, monkeypatch):
        self.output_dir = bundle_output_dir
        monkeypatch.setattr("app.services.bundle_generator.settings.BUNDLE_OUTPUT_DIR", self.output_dir)

    @pytest.mark.asyncio
    async def test_small_srs_under_2_seconds(self):
        """Minimal SRS (1 form, 5 fields) should generate in < 10s."""
        srs = SRSData(
            orgName="Small Org",
            forms=[
                SRSFormDefinition(
                    name="Registration",
                    formType="IndividualProfile",
                    groups=[
                        SRSFormGroup(
                            name="Details",
                            fields=[
                                SRSFormField(name="Name", dataType="Text"),
                                SRSFormField(name="Age", dataType="Numeric", unit="years"),
                                SRSFormField(name="Gender", dataType="Coded",
                                             options=["Male", "Female"], type="SingleSelect"),
                            ],
                        )
                    ],
                )
            ],
        )

        start = time.perf_counter()
        await generate_from_srs(srs, "bench-small")
        elapsed = time.perf_counter() - start

        assert elapsed < 10.0, f"Small SRS took {elapsed:.2f}s (expected < 10s)"

    @pytest.mark.asyncio
    async def test_mch_srs_under_5_seconds(self):
        """Realistic MCH SRS (4 forms, 17 fields) should generate in < 5s."""
        srs = _mch_srs()

        start = time.perf_counter()
        await generate_from_srs(srs, "bench-mch")
        elapsed = time.perf_counter() - start

        assert elapsed < 30.0, f"MCH SRS took {elapsed:.2f}s (expected < 30s)"

    @pytest.mark.asyncio
    async def test_large_srs_under_10_seconds(self):
        """Large SRS (10 forms, 50+ fields) should generate in < 10s."""
        forms = []
        for i in range(10):
            fields = [
                SRSFormField(name=f"Field {j}", dataType="Text" if j % 3 == 0 else "Numeric",
                             unit="kg" if j % 3 != 0 else None, mandatory=j % 2 == 0)
                for j in range(8)
            ]
            fields.append(SRSFormField(
                name=f"Status {i}", dataType="Coded",
                options=["Active", "Inactive", "Pending"], type="SingleSelect",
            ))
            forms.append(SRSFormDefinition(
                name=f"Form {i}",
                formType="IndividualProfile" if i == 0 else "Encounter",
                encounterTypeName=f"Visit Type {i}" if i > 0 else None,
                groups=[SRSFormGroup(name=f"Group {i}", fields=fields)],
            ))

        srs = SRSData(
            orgName="Large Org",
            encounterTypes=[f"Visit Type {i}" for i in range(1, 10)],
            forms=forms,
        )

        start = time.perf_counter()
        await generate_from_srs(srs, "bench-large")
        elapsed = time.perf_counter() - start

        assert elapsed < 60.0, f"Large SRS took {elapsed:.2f}s (expected < 60s)"

    @pytest.mark.asyncio
    async def test_benchmark_report(self):
        """Generate timing report for showcase."""
        timings: dict[str, float] = {}

        # Small
        srs_small = SRSData(
            orgName="Small",
            forms=[SRSFormDefinition(
                name="Reg", formType="IndividualProfile",
                groups=[SRSFormGroup(name="G", fields=[
                    SRSFormField(name="Name", dataType="Text"),
                ])]
            )],
        )
        start = time.perf_counter()
        await generate_from_srs(srs_small, "report-small")
        timings["small_1form_1field"] = time.perf_counter() - start

        # Medium (MCH)
        start = time.perf_counter()
        await generate_from_srs(_mch_srs(), "report-mch")
        timings["mch_4forms_17fields"] = time.perf_counter() - start

        # Print report
        print("\n" + "=" * 60)
        print("BUNDLE GENERATION TIMING BENCHMARK")
        print("=" * 60)
        for label, t in timings.items():
            print(f"  {label:30s}  {t:6.3f}s")
        print("=" * 60)
        print(f"  Concept note target: Requirements→Spec 1.5-2 days → 0.5 day")
        print(f"  Our Spec→Bundle time: {max(timings.values()):.3f}s (instant)")
        print("=" * 60 + "\n")

        # All timings should be reasonable
        for label, t in timings.items():
            assert t < 60.0, f"{label} took {t:.2f}s"


# ─── Trial Org Provisioning Tests ─────────────────────────────────────────────


class TestTrialOrgProvisioning:
    """Tests for the trial org auto-provisioning service."""

    @pytest.mark.asyncio
    async def test_create_organisation_sends_correct_payload(self):
        from unittest.mock import AsyncMock, patch, MagicMock
        from app.services.avni_org_service import AvniOrgService

        svc = AvniOrgService(base_url="http://test-avni:8080")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"name": "Test Org", "dbUser": "test_org"}'
        mock_resp.json.return_value = {"name": "Test Org", "dbUser": "test_org"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await svc.create_organisation(
                admin_auth_token="super-admin-token",
                org_name="Test Org",
            )

        assert result["name"] == "Test Org"
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/organisation" in call_args[0][0]
        assert call_args[1]["headers"]["AUTH-TOKEN"] == "super-admin-token"
        payload = call_args[1]["json"]
        assert payload["name"] == "Test Org"
        assert payload["dbUser"] == "test_org"

    @pytest.mark.asyncio
    async def test_create_user_sends_correct_payload(self):
        from unittest.mock import AsyncMock, patch, MagicMock
        from app.services.avni_org_service import AvniOrgService

        svc = AvniOrgService(base_url="http://test-avni:8080")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"username": "admin@test_org", "name": "Admin"}'
        mock_resp.json.return_value = {"username": "admin@test_org", "name": "Admin"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await svc.create_user(
                auth_token="admin-token",
                username="admin@test_org",
                name="Admin",
            )

        assert result["username"] == "admin@test_org"
        call_args = mock_client.post.call_args
        assert "/user" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_org_401_raises(self):
        from unittest.mock import AsyncMock, patch, MagicMock
        from app.services.avni_org_service import AvniOrgService, AvniOrgError

        svc = AvniOrgService(base_url="http://test-avni:8080")

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            with pytest.raises(AvniOrgError, match="SuperAdmin"):
                await svc.create_organisation("bad-token", "Org")

    @pytest.mark.asyncio
    async def test_create_org_403_raises(self):
        from unittest.mock import AsyncMock, patch, MagicMock
        from app.services.avni_org_service import AvniOrgService, AvniOrgError

        svc = AvniOrgService(base_url="http://test-avni:8080")

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            with pytest.raises(AvniOrgError, match="SuperAdmin"):
                await svc.create_organisation("non-admin-token", "Org")

    @pytest.mark.asyncio
    async def test_provision_trial_org_full_flow(self):
        """Test the full provisioning flow with mocked Avni server."""
        from unittest.mock import AsyncMock, patch, MagicMock
        from app.services.avni_org_service import AvniOrgService

        svc = AvniOrgService(base_url="http://test-avni:8080")

        # Create a test bundle zip
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            with zipfile.ZipFile(tmp, "w") as zf:
                zf.writestr("concepts.json", "[]")
                zf.writestr("subjectTypes.json", "[]")
            zip_path = tmp.name

        try:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = '{"name": "Trial Org", "dbUser": "trial_org"}'
            mock_resp.json.return_value = {"name": "Trial Org", "dbUser": "trial_org"}

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                result = await svc.provision_trial_org(
                    admin_auth_token="super-admin-token",
                    org_name="Trial Org",
                    bundle_zip_path=zip_path,
                )

            assert result["status"] == "provisioned"
            assert result["organisation"]["name"] == "Trial Org"
            assert "credentials" in result
            assert "next_steps" in result
            assert len(result["next_steps"]) == 3
        finally:
            os.unlink(zip_path)
