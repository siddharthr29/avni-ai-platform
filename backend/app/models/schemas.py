from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, EmailStr, Field


# --- Enums ---

class IntentType(str, Enum):
    BUNDLE = "bundle"
    RULE = "rule"
    VOICE = "voice"
    IMAGE = "image"
    CONFIG = "config"
    SUPPORT = "support"
    KNOWLEDGE = "knowledge"
    CHAT = "chat"


class SSEEventType(str, Enum):
    TEXT = "text"
    PROGRESS = "progress"
    DONE = "done"
    ERROR = "error"
    CONFIRM_ACTION = "confirm_action"  # Human-in-the-loop approval
    AGENT_STEP = "agent_step"  # ReAct agent step update


class BundleStatusType(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


# --- Chat ---

class Attachment(BaseModel):
    type: str = Field(description="Type of attachment: 'file' or 'image'")
    data: str = Field(description="Base64-encoded data or text content")
    filename: str | None = None
    mime_type: str | None = None


class ChatMessage(BaseModel):
    role: str = Field(description="Message role: 'user' or 'assistant'")
    content: str = Field(description="Message content")


class ChatRequest(BaseModel):
    message: str = Field(description="User message text")
    session_id: str = Field(description="Session identifier for conversation continuity")
    attachments: list[Attachment] = Field(default_factory=list)
    org_name: str | None = Field(default=None, description="Organisation name for context")
    sector: str | None = Field(default=None, description="Sector e.g. MCH, WASH, Education")
    org_context: str | None = Field(default=None, description="Free-text description of the organisation")
    # BYOK (Bring Your Own Key) — per-request LLM override
    byok_provider: str | None = Field(default=None, description="LLM provider override: 'groq', 'anthropic', 'gemini', 'cerebras', 'openai'")
    byok_api_key: str | None = Field(default=None, description="User's own API key for the provider")


class ChatResponse(BaseModel):
    session_id: str
    intent: IntentType
    content: str


class SSEEvent(BaseModel):
    type: SSEEventType
    content: str


# --- Intent ---

class IntentResult(BaseModel):
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    extracted_params: dict[str, Any] = Field(default_factory=dict)


# --- Bundle ---

class SRSFormField(BaseModel):
    name: str
    dataType: str
    mandatory: bool = True
    options: list[str] | None = None
    type: str | None = None
    unit: str | None = None
    lowAbsolute: float | None = None
    highAbsolute: float | None = None
    lowNormal: float | None = None
    highNormal: float | None = None
    keyValues: list[dict[str, Any]] | None = None


class SRSFormGroup(BaseModel):
    name: str
    fields: list[SRSFormField]


class SRSFormDefinition(BaseModel):
    name: str
    formType: str
    groups: list[SRSFormGroup]
    programName: str | None = None
    encounterTypeName: str | None = None
    subjectTypeName: str | None = None


class SRSData(BaseModel):
    orgName: str = "Organisation"
    subjectTypes: list[dict[str, Any]] = Field(
        default_factory=lambda: [{"name": "Individual", "type": "Person"}]
    )
    programs: list[dict[str, Any]] = Field(default_factory=list)
    encounterTypes: list[str] = Field(default_factory=list)
    forms: list[SRSFormDefinition] = Field(default_factory=list)
    groups: list[str] = Field(
        default_factory=lambda: ["Everyone"]
    )
    addressLevelTypes: list[dict[str, Any]] | None = None
    programEncounterMappings: list[dict[str, Any]] | None = None
    generalEncounterTypes: list[str] | None = None
    visitSchedules: list[dict[str, Any]] | None = None
    decisions: list[dict[str, Any]] | None = None
    eligibilityRules: list[dict[str, Any]] | None = None
    reportCards: list[dict[str, Any]] | None = None


class BundleGenerateRequest(BaseModel):
    srs_data: SRSData | None = None
    srs_text: str | None = None


class BundleStatus(BaseModel):
    id: str
    status: BundleStatusType
    progress: int = Field(ge=0, le=100)
    message: str = ""
    download_url: str | None = None
    error: str | None = None


# --- Voice ---

class VoiceMapRequest(BaseModel):
    transcript: str = Field(description="Voice transcript text")
    form_json: dict[str, Any] = Field(description="Avni form JSON definition")
    language: str = Field(default="en", description="Language code of the transcript")


class FieldMapping(BaseModel):
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)


class VoiceMapResponse(BaseModel):
    fields: dict[str, Any] = Field(description="Mapped field name -> value")
    confidence: dict[str, float] = Field(description="Mapped field name -> confidence score")
    unmapped_text: str = Field(default="", description="Portions of transcript that could not be mapped")


# --- Image ---

class ImageExtractResponse(BaseModel):
    fields: dict[str, Any] = Field(description="Extracted field name -> value")
    confidence: dict[str, float] = Field(description="Extracted field name -> confidence score")
    notes: str = Field(default="", description="Additional observations from the image")


# --- Knowledge ---

class KnowledgeSearchRequest(BaseModel):
    query: str = Field(description="Search query")
    category: str | None = Field(
        default=None,
        description="Category to search: 'concepts', 'rules', 'tickets', or None for all"
    )
    limit: int = Field(default=10, ge=1, le=50)


class KnowledgeResult(BaseModel):
    text: str
    category: str
    score: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchResponse(BaseModel):
    results: list[KnowledgeResult]
    total: int
    query: str


# --- Rules ---

class RuleGenerateRequest(BaseModel):
    description: str = Field(description="Natural language description of the desired rule")
    rule_type: str | None = Field(
        default=None,
        description="Target rule type: ViewFilter, Decision, VisitSchedule, Validation, Checklist, EnrolmentSummary, or Eligibility",
    )
    form_json: dict[str, Any] | None = Field(
        default=None,
        description="Avni form JSON definition for accurate concept names and UUIDs",
    )
    concepts_json: list[Any] | None = Field(
        default=None,
        description="List of concept definitions for cross-referencing",
    )
    complexity_hint: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Complexity hint (1-5). Lower values prefer declarative rules.",
    )


class RuleGenerateResponse(BaseModel):
    code: str = Field(description="Generated rule code (JavaScript or declarative JSON)")
    rule_type: str = Field(description="Rule type: ViewFilter, Decision, VisitSchedule, etc.")
    format: str = Field(description="Rule format: 'declarative' or 'javascript'")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score for the generated rule")
    explanation: str = Field(description="Human-readable explanation of what the rule does")
    warnings: list[str] = Field(default_factory=list, description="Any warnings about the generated rule")
    template_used: str | None = Field(default=None, description="ID of the template used as reference, if any")


class RuleTestRequest(BaseModel):
    code: str = Field(description="Rule code to validate (JavaScript or declarative JSON)")
    rule_type: str = Field(description="Rule type: ViewFilter, Decision, VisitSchedule, etc.")
    concepts: list[Any] | None = Field(
        default=None,
        description="List of concept definitions for cross-reference checking",
    )


class RuleTestResponse(BaseModel):
    valid: bool = Field(description="Whether the rule passed all checks")
    syntax_ok: bool = Field(description="Whether the syntax is valid")
    concept_refs_ok: bool = Field(description="Whether all concept references were found")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings")
    errors: list[str] = Field(default_factory=list, description="Fatal errors found")


class RuleTemplateSummary(BaseModel):
    id: str = Field(description="Unique template identifier")
    name: str = Field(description="Human-readable template name")
    type: str = Field(description="Rule type this template implements")
    description: str = Field(description="What this template does")
    complexity: int = Field(ge=1, le=5, description="Complexity rating 1-5")
    format: str = Field(description="'declarative' or 'javascript'")
    sectors: list[str] = Field(description="Applicable sectors or ['all']")


class RuleValidateRequest(BaseModel):
    code: str = Field(description="JavaScript rule code to validate")
    rule_type: str | None = Field(
        default=None,
        description="Rule type: ViewFilter, VisitSchedule, Decision, Validation, etc.",
    )


# --- Avni Sync ---

# --- Admin User Management ---

class AdminUserListResponse(BaseModel):
    id: str
    name: str
    email: str | None = None
    org_name: str
    sector: str = ""
    role: str
    is_active: bool = True
    last_login: Any | None = None
    created_at: Any | None = None


class AdminUserCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    org_name: str = Field(min_length=1, max_length=200)
    sector: str = ""
    role: str = Field(default="implementor", description="One of: ngo_user, implementor, org_admin, platform_admin")
    org_context: str = ""


class AdminUserRoleUpdateRequest(BaseModel):
    role: str = Field(description="New role: ngo_user, implementor, org_admin, platform_admin")


class AdminUserStatusUpdateRequest(BaseModel):
    is_active: bool


class AdminUserInviteRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    org_name: str = Field(min_length=1, max_length=200)
    role: str = Field(default="implementor")


class AdminBootstrapRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    org_name: str = Field(min_length=1, max_length=200)
    sector: str = ""
    org_context: str = ""


class AdminStatsResponse(BaseModel):
    total_users: int = 0
    active_users: int = 0
    users_by_role: dict[str, int] = Field(default_factory=dict)
    users_by_org: dict[str, int] = Field(default_factory=dict)
    total_sessions: int = 0
    messages_24h: int = 0
    messages_7d: int = 0
    messages_30d: int = 0


class SaveObservationsRequest(BaseModel):
    subject_uuid: str | None = None
    encounter_type: str = Field(description="Avni encounter type name")
    program: str | None = Field(default=None, description="Program name for program encounters")
    fields: dict = Field(description="Mapped observation field values (concept name -> value)")
    auth_token: str = Field(description="Avni AUTH-TOKEN")
    subject_type: str = Field(default="Individual", description="Subject type name")
    first_name: str | None = Field(default=None, description="First name for new subject creation")
    last_name: str | None = Field(default=None, description="Last name for new subject creation")


class SaveObservationsResponse(BaseModel):
    success: bool
    subject_uuid: str
    encounter_uuid: str | None = None
    message: str


# --- Support Diagnosis ---

class SupportDiagnoseRequest(BaseModel):
    description: str = Field(description="Natural-language description of the issue")
    error_message: str | None = Field(default=None, description="Exact error message if available")
    context: str | None = Field(default=None, description="Additional context (org name, device, etc.)")


class SupportDiagnoseResponse(BaseModel):
    pattern: str = Field(description="Matched issue pattern name")
    diagnosis: str = Field(description="Summary diagnosis")
    checks: list[str] = Field(description="Diagnostic steps to verify the issue")
    common_fixes: list[str] = Field(description="Known fixes for this issue type")
    confidence: float = Field(ge=0.0, le=1.0, description="Match confidence score")
    ai_analysis: str | None = Field(default=None, description="Claude's additional analysis if keyword match was weak")
