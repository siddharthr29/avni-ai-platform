export type UserRole = 'ngo_user' | 'implementor' | 'org_admin' | 'platform_admin';

export interface UserProfile {
  id: string;
  name: string;
  email: string;
  orgName: string;
  sector: string;
  orgContext: string;
  role: UserRole;
  isActive: boolean;
  createdAt: string;
  accessToken: string;
  refreshToken: string;
  // BYOK (Bring Your Own Key) — per-user LLM provider override
  byokProvider?: string;
  byokApiKey?: string;
}

export interface AdminUser {
  id: string;
  name: string;
  email: string;
  orgName: string;
  sector: string;
  role: string;
  isActive: boolean;
  lastLogin: string | null;
  createdAt: string;
  sessionCount?: number;
}

export interface PlatformStats {
  totalUsers: number;
  activeUsers: number;
  usersByRole: Record<string, number>;
  usersByOrg: Record<string, number>;
  totalSessions: number;
  recentMessages24h: number;
  recentMessages7d: number;
  recentMessages30d: number;
}

export interface InviteUserRequest {
  email: string;
  name: string;
  orgName: string;
  role: string;
  sector?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  attachments?: Attachment[];
  metadata?: {
    type?: 'text' | 'progress' | 'voice_mapped' | 'image_extracted' | 'bundle_ready' | 'rule' | 'error'
      | 'workflow_progress' | 'checkpoint' | 'clarification';
    fields?: Record<string, unknown>;
    confidence?: Record<string, number>;
    downloadUrl?: string;
    bundleId?: string;
    code?: string;
    ruleType?: string;
    progress?: { step: string; current: number; total: number };
    bundleFiles?: BundleFile[];
    records?: Record<string, unknown>[];
    warnings?: string[];
    // Workflow-related metadata
    workflowId?: string;
    step?: WorkflowStep;
    needs?: 'approval' | 'review' | 'input';
    resultSummary?: any;
    questions?: ClarityQuestion[];
  };
}

export interface Attachment {
  type: 'file' | 'image';
  name: string;
  size: number;
  data: string;
  mimeType: string;
  previewUrl?: string;
}

export interface Session {
  id: string;
  title: string;
  createdAt: Date;
  messages: Message[];
  _messageCount?: number;
}

export interface VoiceMapResult {
  fields: Record<string, unknown>;
  confidence: Record<string, number>;
  unmapped_text: string;
}

export interface ImageExtractResult {
  records: Record<string, unknown>[];
  warnings: string[];
}

export interface BundleFile {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: BundleFile[];
  content?: string;
  status?: 'pass' | 'fail' | 'warning';
}

export interface SSEEvent {
  type: 'text' | 'progress' | 'voice_mapped' | 'image_extracted' | 'bundle_ready' | 'rule' | 'error' | 'done'
    | 'workflow_progress' | 'checkpoint' | 'clarification';
  data: string;
  metadata?: Record<string, unknown>;
}

export interface FormContext {
  name: string;
  json: Record<string, unknown>;
  fieldCount: number;
}

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'info';
  message: string;
}

export interface RuleTestResult {
  success: boolean;
  output?: string;
  error?: string;
}

export type SupportedLanguage = {
  code: string;
  name: string;
};

export const SUPPORTED_LANGUAGES: SupportedLanguage[] = [
  { code: 'en-IN', name: 'English (India)' },
  { code: 'hi-IN', name: 'Hindi' },
  { code: 'mr-IN', name: 'Marathi' },
  { code: 'or-IN', name: 'Odia' },
  { code: 'ta-IN', name: 'Tamil' },
  { code: 'te-IN', name: 'Telugu' },
  { code: 'kn-IN', name: 'Kannada' },
  { code: 'bn-IN', name: 'Bengali' },
  { code: 'gu-IN', name: 'Gujarati' },
  { code: 'pa-IN', name: 'Punjabi' },
  { code: 'ml-IN', name: 'Malayalam' },
];

// ─── SRS Types ───────────────────────────────────────────────────────────────

export interface ProgramSummaryData {
  organizationName: string;
  location: string;
  locationHierarchy: string;
  previousSystem: string;
  challenges: string;
  programStartDate: string;
  rolloutDate: string;
  numberOfUsers: number;
  dataMigration: boolean;
}

export interface ProgramDetailData {
  id: string;
  name: string;
  objective: string;
  eligibility: string;
  entryPoint: string;
  exitCriteria: string;
  totalBeneficiaries: number;
  successIndicators: string;
  forms: string[];
  reportsNeeded: string;
}

export interface UserPersonaData {
  id: string;
  type: string;
  description: string;
  count: number;
}

export interface W3HEntryData {
  id: string;
  what: string;
  when: string;
  who: string;
  how: 'Mobile' | 'Web' | 'Both';
  formsToSchedule: string;
  notes: string;
}

export type FormFieldDataType =
  | 'Text'
  | 'Numeric'
  | 'Date'
  | 'Coded'
  | 'Notes'
  | 'Time'
  | 'Image'
  | 'PhoneNumber'
  | 'Subject'
  | 'QuestionGroup';

export interface FormFieldData {
  id: string;
  pageName: string;
  fieldName: string;
  dataType: FormFieldDataType;
  mandatory: boolean;
  userOrSystem: 'User Enter' | 'System Generated';
  options: string;
  selectionType: 'Single' | 'Multi';
  unit: string;
  min: string;
  max: string;
  skipLogic: string;
}

export interface FormDefinitionData {
  id: string;
  name: string;
  fields: FormFieldData[];
}

export interface VisitScheduleData {
  id: string;
  onCompletionOf: string;
  scheduleForm: string;
  frequency: 'Daily' | 'Weekly' | 'Monthly' | 'Quarterly' | 'Yearly' | 'One-time';
  scheduleFor: string;
  conditionToSchedule: string;
  conditionNotToSchedule: string;
  scheduleDate: string;
  overdueDate: string;
  onCancellation: string;
  weekendHoliday: string;
  onEdit: string;
}

export interface DashboardCardData {
  id: string;
  cardName: string;
  logic: string;
  userType: string;
}

export interface PermissionEntry {
  view: boolean;
  register: boolean;
  edit: boolean;
  void: boolean;
}

export interface PermissionMatrixData {
  // formId -> userPersonaId -> PermissionEntry
  [formId: string]: {
    [userPersonaId: string]: PermissionEntry;
  };
}

export interface SRSData {
  summary: ProgramSummaryData;
  programs: ProgramDetailData[];
  users: UserPersonaData[];
  w3h: W3HEntryData[];
  forms: FormDefinitionData[];
  visitScheduling: VisitScheduleData[];
  dashboardCards: DashboardCardData[];
  permissions: PermissionMatrixData;
}

export type SRSTabName =
  | 'summary'
  | 'programs'
  | 'users'
  | 'w3h'
  | 'forms'
  | 'visitScheduling'
  | 'dashboardCards'
  | 'permissions';

// ─── Workflow Types ──────────────────────────────────────────────────────────

export interface WorkflowStep {
  id: string;
  name: string;
  description: string;
  checkpoint: 'auto' | 'review' | 'approve' | 'block';
  status: 'pending' | 'running' | 'waiting_approval' | 'approved' | 'rejected' | 'completed' | 'failed' | 'skipped';
  result?: any;
  errors: string[];
  warnings: string[];
  started_at?: number;
  completed_at?: number;
  provider_used?: string;
}

export interface Workflow {
  id: string;
  name: string;
  steps: WorkflowStep[];
  status: 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
  current_step_index: number;
  created_at: number;
}

export interface ClarityQuestion {
  id: string;
  category: string;
  severity: 'critical' | 'important' | 'nice_to_have';
  question: string;
  context: string;
  suggestions: string[];
  default?: string;
  answer?: string;
}

export interface ProviderInfo {
  provider: string;
  model: string;
  latency_ms: number;
  cost_usd: number;
  fallback_used: boolean;
}

export interface RegenerationResult {
  success: boolean;
  changes_made: { file: string; field?: string; old_value: any; new_value: any; reason: string }[];
  remaining_errors: any[];
  iterations: number;
  needs_human_input: any[];
}

// ─── Document Extractor Types ─────────────────────────────────────────────────

export interface ExtractedDocumentData {
  text: string;
  tables: string[][][];
  metadata: Record<string, string>;
}

export interface StructuredRequirementsData {
  title: string;
  subject_types: string[];
  programs: string[];
  encounter_types: { name: string; program?: string; frequency?: string }[];
  data_fields: { name: string; type: string; form?: string; section?: string; unit?: string; options?: string[] }[];
  visit_schedules: string[];
  rules: string[];
  ambiguities: string[];
}

export interface BackendSRSForm {
  name: string;
  formType: string;
  programName?: string;
  encounterTypeName?: string;
  groups: {
    name: string;
    fields: {
      name: string;
      dataType: string;
      mandatory: boolean;
      options?: string[];
      type?: string;
      unit?: string;
      lowAbsolute?: number;
      highAbsolute?: number;
    }[];
  }[];
}

export interface BackendSRSData {
  orgName: string;
  subjectTypes: { name: string; type: string }[];
  programs: { name: string; colour?: string; enrolmentEligibility?: boolean }[];
  encounterTypes: string[];
  forms: BackendSRSForm[];
  groups: string[];
  addressLevelTypes?: { name: string; level: number }[];
  programEncounterMappings?: { encounterType: string; program: string }[];
  generalEncounterTypes?: string[];
}

export interface DocumentClarification {
  question: string;
  context: string;
  options?: string[];
  field?: string;
}

export interface ProcessDocumentResult {
  extracted: ExtractedDocumentData;
  requirements: StructuredRequirementsData;
  srs_data: BackendSRSData;
  clarifications: DocumentClarification[];
}

// ─── Data Type Display Labels ─────────────────────────────────────────────────

/** Maps internal Avni data type values to user-friendly display labels. */
export const DATA_TYPE_DISPLAY_LABELS: Record<string, string> = {
  Coded: 'Multiple Choice',
  Numeric: 'Number',
  Text: 'Free Text',
  Date: 'Date',
  DateTime: 'Date & Time',
  Image: 'Photo',
  Video: 'Video',
  Audio: 'Audio Recording',
  NA: 'Section Header',
  Notes: 'Long Text',
  Time: 'Time',
  PhoneNumber: 'Phone Number',
  Subject: 'Subject Link',
  QuestionGroup: 'Question Group',
};

/** Tooltips explaining each data type in plain language. */
export const DATA_TYPE_TOOLTIPS: Record<string, string> = {
  Coded: 'A field with predefined answer options. The user picks one or more choices from a list.',
  Numeric: 'A numeric value like age, weight, or count. Can have min/max limits and units.',
  Text: 'A short free-text answer typed by the user.',
  Date: 'A calendar date (day, month, year).',
  DateTime: 'A date combined with a specific time.',
  Image: 'A photo taken with the device camera or selected from gallery.',
  Video: 'A video recording captured on the device.',
  Audio: 'An audio recording captured on the device.',
  NA: 'A section header or label -- not a data-entry field.',
  Notes: 'A longer free-text area for detailed notes or descriptions.',
  Time: 'A time of day (hours and minutes).',
  PhoneNumber: 'A phone number with built-in format validation.',
  Subject: 'A link to another registered person or entity in the system.',
  QuestionGroup: 'A repeatable group of related questions that can be answered multiple times.',
};
