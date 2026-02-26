export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  attachments?: Attachment[];
  metadata?: {
    type?: 'text' | 'progress' | 'voice_mapped' | 'image_extracted' | 'bundle_ready' | 'rule' | 'error';
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
  type: 'text' | 'progress' | 'voice_mapped' | 'image_extracted' | 'bundle_ready' | 'rule' | 'error' | 'done';
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
