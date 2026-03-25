"""Tests for Pydantic models and schemas."""

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    Attachment,
    BundleGenerateRequest,
    BundleStatus,
    BundleStatusType,
    ChatRequest,
    IntentResult,
    IntentType,
    KnowledgeSearchRequest,
    RuleGenerateRequest,
    RuleValidateRequest,
    SRSData,
    SRSFormDefinition,
    SRSFormField,
    SRSFormGroup,
    SSEEvent,
    SSEEventType,
)


class TestChatRequest:
    def test_chat_request_valid(self):
        req = ChatRequest(message="Hello", session_id="sess-1")
        assert req.message == "Hello"
        assert req.session_id == "sess-1"
        assert req.attachments == []
        assert req.org_name is None

    def test_chat_request_with_all_fields(self):
        req = ChatRequest(
            message="Help me",
            session_id="s1",
            attachments=[Attachment(type="file", data="base64data")],
            org_name="TestOrg",
            sector="MCH",
            org_context="Rural health program",
        )
        assert req.org_name == "TestOrg"
        assert len(req.attachments) == 1

    def test_chat_request_missing_message(self):
        with pytest.raises(ValidationError):
            ChatRequest(session_id="s1")

    def test_chat_request_missing_session_id(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="Hello")


class TestSRSData:
    def test_srs_data_defaults(self):
        srs = SRSData()
        assert srs.orgName == "Organisation"
        assert len(srs.subjectTypes) == 1
        assert srs.subjectTypes[0]["name"] == "Individual"
        assert srs.programs == []
        assert srs.encounterTypes == []
        assert srs.forms == []
        assert srs.groups == ["Everyone"]

    def test_srs_data_with_full_spec(self):
        srs = SRSData(
            orgName="Test Org",
            subjectTypes=[{"name": "Patient", "type": "Person"}],
            programs=[{"name": "TB", "colour": "#FF0000"}],
            encounterTypes=["Screening", "Follow-up"],
            forms=[
                SRSFormDefinition(
                    name="Registration",
                    formType="IndividualProfile",
                    groups=[
                        SRSFormGroup(
                            name="Basic Details",
                            fields=[
                                SRSFormField(name="Name", dataType="Text"),
                                SRSFormField(name="Age", dataType="Numeric", unit="years"),
                            ]
                        )
                    ]
                )
            ],
            groups=["Everyone", "Admin"],
            addressLevelTypes=[{"name": "District", "level": 2}],
        )
        assert srs.orgName == "Test Org"
        assert len(srs.forms) == 1
        assert len(srs.forms[0].groups[0].fields) == 2

    def test_srs_form_field_defaults(self):
        field = SRSFormField(name="Weight", dataType="Numeric")
        assert field.mandatory is True
        assert field.options is None
        assert field.unit is None


class TestIntentType:
    def test_intent_type_enum_values(self):
        assert IntentType.BUNDLE.value == "bundle"
        assert IntentType.RULE.value == "rule"
        assert IntentType.VOICE.value == "voice"
        assert IntentType.IMAGE.value == "image"
        assert IntentType.CONFIG.value == "config"
        assert IntentType.SUPPORT.value == "support"
        assert IntentType.KNOWLEDGE.value == "knowledge"
        assert IntentType.CHAT.value == "chat"

    def test_intent_type_count(self):
        assert len(IntentType) == 8


class TestSSEEventType:
    def test_sse_event_type_enum_values(self):
        assert SSEEventType.TEXT.value == "text"
        assert SSEEventType.PROGRESS.value == "progress"
        assert SSEEventType.DONE.value == "done"
        assert SSEEventType.ERROR.value == "error"
        assert SSEEventType.CONFIRM_ACTION.value == "confirm_action"
        assert SSEEventType.AGENT_STEP.value == "agent_step"

    def test_sse_event_type_count(self):
        assert len(SSEEventType) == 6


class TestBundleStatusType:
    def test_bundle_status_type_enum(self):
        assert BundleStatusType.PENDING.value == "pending"
        assert BundleStatusType.GENERATING.value == "generating"
        assert BundleStatusType.COMPLETED.value == "completed"
        assert BundleStatusType.FAILED.value == "failed"


class TestBundleStatus:
    def test_bundle_status_valid(self):
        status = BundleStatus(id="b1", status=BundleStatusType.PENDING, progress=0)
        assert status.id == "b1"
        assert status.message == ""
        assert status.download_url is None

    def test_bundle_status_progress_bounds(self):
        with pytest.raises(ValidationError):
            BundleStatus(id="b1", status=BundleStatusType.PENDING, progress=-1)
        with pytest.raises(ValidationError):
            BundleStatus(id="b1", status=BundleStatusType.PENDING, progress=101)


class TestRuleGenerateRequest:
    def test_rule_generate_request_valid(self):
        req = RuleGenerateRequest(description="Show field when age > 18")
        assert req.description == "Show field when age > 18"
        assert req.rule_type is None
        assert req.complexity_hint is None

    def test_rule_generate_request_complexity_bounds(self):
        req = RuleGenerateRequest(description="test", complexity_hint=1)
        assert req.complexity_hint == 1
        req = RuleGenerateRequest(description="test", complexity_hint=5)
        assert req.complexity_hint == 5

        with pytest.raises(ValidationError):
            RuleGenerateRequest(description="test", complexity_hint=0)
        with pytest.raises(ValidationError):
            RuleGenerateRequest(description="test", complexity_hint=6)


class TestKnowledgeSearchRequest:
    def test_knowledge_search_request_valid(self):
        req = KnowledgeSearchRequest(query="form mapping")
        assert req.limit == 10
        assert req.category is None

    def test_knowledge_search_request_limit_bounds(self):
        req = KnowledgeSearchRequest(query="test", limit=1)
        assert req.limit == 1
        req = KnowledgeSearchRequest(query="test", limit=50)
        assert req.limit == 50

        with pytest.raises(ValidationError):
            KnowledgeSearchRequest(query="test", limit=0)
        with pytest.raises(ValidationError):
            KnowledgeSearchRequest(query="test", limit=51)


class TestAttachment:
    def test_attachment_model(self):
        att = Attachment(type="file", data="base64content")
        assert att.type == "file"
        assert att.filename is None
        assert att.mime_type is None

    def test_attachment_with_metadata(self):
        att = Attachment(
            type="image", data="b64", filename="photo.jpg", mime_type="image/jpeg"
        )
        assert att.filename == "photo.jpg"
        assert att.mime_type == "image/jpeg"


class TestIntentResult:
    def test_intent_result_valid(self):
        r = IntentResult(intent=IntentType.BUNDLE, confidence=0.95)
        assert r.intent == IntentType.BUNDLE
        assert r.extracted_params == {}

    def test_intent_result_confidence_bounds(self):
        with pytest.raises(ValidationError):
            IntentResult(intent=IntentType.CHAT, confidence=1.5)
        with pytest.raises(ValidationError):
            IntentResult(intent=IntentType.CHAT, confidence=-0.1)


class TestRuleValidateRequest:
    def test_rule_validate_request(self):
        req = RuleValidateRequest(code="const x = 1;")
        assert req.rule_type is None

    def test_rule_validate_request_with_type(self):
        req = RuleValidateRequest(code="code", rule_type="ViewFilter")
        assert req.rule_type == "ViewFilter"


class TestBundleGenerateRequest:
    def test_bundle_generate_request_empty(self):
        req = BundleGenerateRequest()
        assert req.srs_data is None
        assert req.srs_text is None

    def test_bundle_generate_request_with_text(self):
        req = BundleGenerateRequest(srs_text="Create a TB program")
        assert req.srs_text == "Create a TB program"


class TestSSEEvent:
    def test_sse_event(self):
        evt = SSEEvent(type=SSEEventType.TEXT, content="hello")
        assert evt.type == SSEEventType.TEXT
        assert evt.content == "hello"
