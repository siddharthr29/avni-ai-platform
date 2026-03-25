"""Test fixtures for Avni AI Platform.

Provides:
- Test FastAPI client (async)
- Mock database pool
- Mock LLM client (returns predictable responses)
- Sample bundle data (valid and invalid)
- Sample user/session data
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Ensure no real DB or external connections during tests
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("API_KEYS", "")
# Enable dev mode for tests (grants platform_admin without auth)
os.environ["AVNI_DEV_MODE"] = "true"


@pytest_asyncio.fixture
async def client():
    """Async test client for FastAPI with mocked DB and RAG."""
    with patch("app.db.init_db", new_callable=AsyncMock), \
         patch("app.db.close_db", new_callable=AsyncMock), \
         patch("app.db._pool", None), \
         patch("app.config.settings.AVNI_DEV_MODE", True), \
         patch("app.services.rag.fallback.rag_service.initialize", new_callable=AsyncMock), \
         patch("app.services.rag.fallback.rag_service.close", new_callable=AsyncMock), \
         patch("app.services.rag.fallback.rag_service._rag_available", False), \
         patch("app.services.pageindex_service.pageindex_service.initialize", new_callable=AsyncMock), \
         patch("app.services.pageindex_service.pageindex_service.close", new_callable=AsyncMock), \
         patch("app.services.pageindex_service.pageindex_service.get_stats", new_callable=AsyncMock, return_value={"total_documents": 0, "collections": []}):
        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
def sample_valid_bundle():
    """A minimal valid Avni bundle structure."""
    return {
        "concepts.json": [
            {"uuid": "uuid-1", "name": "Weight", "dataType": "Numeric", "unit": "kg"},
            {"uuid": "uuid-2", "name": "Gender", "dataType": "Coded",
             "answers": [
                 {"uuid": "uuid-yes", "name": "Male"},
                 {"uuid": "uuid-no", "name": "Female"},
             ]},
            {"uuid": "uuid-yes", "name": "Male", "dataType": "NA"},
            {"uuid": "uuid-no", "name": "Female", "dataType": "NA"},
        ],
        "subjectTypes.json": [
            {"uuid": "st-1", "name": "Individual", "type": "Person"},
        ],
        "programs.json": [
            {"uuid": "pg-1", "name": "Maternal Health", "colour": "#E91E63"},
        ],
        "encounterTypes.json": [
            {"uuid": "et-1", "name": "ANC Visit"},
        ],
        "forms/Registration.json": {
            "uuid": "form-1", "name": "Registration", "formType": "IndividualProfile",
            "formElementGroups": [
                {"uuid": "feg-1", "name": "Details", "formElements": [
                    {"uuid": "fe-1", "concept": {"uuid": "uuid-1", "name": "Weight"}, "mandatory": True},
                    {"uuid": "fe-2", "concept": {"uuid": "uuid-2", "name": "Gender"}, "mandatory": True},
                ]}
            ]
        },
        "formMappings.json": [
            {"uuid": "fm-1", "formUUID": "form-1", "subjectTypeUUID": "st-1",
             "programUUID": None, "encounterTypeUUID": None},
        ],
        "groups.json": [
            {"uuid": "grp-1", "name": "Users", "hasAllPrivileges": False},
        ],
        "groupPrivilege.json": [
            {"uuid": "gp-1", "groupUUID": "grp-1", "privilegeType": "ViewSubject",
             "subjectTypeUUID": "st-1", "programUUID": "", "encounterTypeUUID": ""},
        ],
        "operationalSubjectTypes.json": {"operationalSubjectTypes": [
            {"uuid": "ost-1", "name": "Individual", "subjectType": {"uuid": "st-1"}},
        ]},
        "operationalPrograms.json": {"operationalPrograms": [
            {"uuid": "op-1", "name": "Maternal Health", "program": {"uuid": "pg-1"}},
        ]},
        "operationalEncounterTypes.json": {"operationalEncounterTypes": [
            {"uuid": "oet-1", "name": "ANC Visit", "encounterType": {"uuid": "et-1"}},
        ]},
    }


@pytest.fixture
def sample_invalid_bundle():
    """Bundle with known issues for validation testing."""
    return {
        "concepts.json": [
            {"uuid": "uuid-1", "name": "Weight", "dataType": "Numeric"},
            {"uuid": "uuid-dup", "name": "weight", "dataType": "Numeric"},  # duplicate (case-insensitive)
            {"uuid": "uuid-2", "name": "Status", "dataType": "Coded",
             "answers": [
                 {"uuid": "uuid-missing-answer", "name": "Active"},  # missing NA concept
             ]},
        ],
        "subjectTypes.json": [
            {"uuid": "st-1", "name": "Individual", "type": "Person"},
        ],
        "programs.json": [],
        "encounterTypes.json": [
            {"uuid": "et-1", "name": "ANC Visit"},
        ],
        "forms/Registration.json": {
            "uuid": "form-1", "name": "Registration", "formType": "IndividualProfile",
            "formElementGroups": [
                {"uuid": "feg-1", "name": "Details", "formElements": [
                    {"uuid": "fe-1", "concept": {"uuid": "uuid-missing", "name": "Missing Concept"}, "mandatory": True},
                ]}
            ]
        },
        "formMappings.json": [
            {"uuid": "fm-1", "formUUID": "form-1", "subjectTypeUUID": "st-1",
             "programUUID": None, "encounterTypeUUID": None},
            {"uuid": "fm-2", "formUUID": "form-orphan", "formName": "Orphaned Form",
             "subjectTypeUUID": "st-1", "programUUID": None, "encounterTypeUUID": None},
            {"uuid": "fm-3", "formUUID": "form-1", "subjectTypeUUID": "st-missing",
             "programUUID": None, "encounterTypeUUID": None},
            # Missing cancellation form: ProgramEncounter without ProgramEncounterCancellation
            {"uuid": "fm-4", "formUUID": "form-1", "formType": "ProgramEncounter",
             "subjectTypeUUID": "st-1", "programUUID": None, "encounterTypeUUID": "et-1"},
        ],
        "groupPrivilege.json": [
            {"groupUUID": "g1", "privilegeType": "EditSubject", "subjectTypeUUID": "st-1",
             "programUUID": "", "encounterTypeUUID": ""},
            {"groupUUID": "g1", "privilegeType": "EditSubject", "subjectTypeUUID": "st-1",
             "programUUID": "", "encounterTypeUUID": ""},  # duplicate
        ],
    }


@pytest.fixture
def bundle_dir(sample_valid_bundle, tmp_path):
    """Create a temporary directory with valid bundle files."""
    _write_bundle_to_dir(tmp_path, sample_valid_bundle)
    return str(tmp_path)


@pytest.fixture
def invalid_bundle_dir(sample_invalid_bundle, tmp_path):
    """Create a temporary directory with invalid bundle files."""
    _write_bundle_to_dir(tmp_path, sample_invalid_bundle)
    return str(tmp_path)


def _write_bundle_to_dir(base_path: Path, bundle: dict) -> None:
    """Write a bundle dictionary to a directory structure."""
    for key, value in bundle.items():
        if key.startswith("forms/"):
            forms_dir = base_path / "forms"
            forms_dir.mkdir(exist_ok=True)
            fname = key.split("/", 1)[1]
            (forms_dir / fname).write_text(json.dumps(value))
        else:
            (base_path / key).write_text(json.dumps(value))
