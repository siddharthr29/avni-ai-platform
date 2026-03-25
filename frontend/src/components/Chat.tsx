import { useEffect, useRef, useState, useCallback, lazy, Suspense } from 'react';
import { Package, Mic, ImageIcon, Code, RefreshCw, BookOpen, ArrowDown, Wrench, GraduationCap, HeadphonesIcon } from 'lucide-react';
import { AvniLogo } from './AvniLogo';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import type { SlashCommand } from './ChatInput';
import { VoiceCapture } from './VoiceCapture';
import { ImageUpload } from './ImageUpload';
import { FormContextPanel } from './FormContext';
import { ArtifactPanel, type Artifact } from './ArtifactPanel';
import { parseCSVToSpreadsheet, spreadsheetToCSV } from './SpreadsheetEditor';
import type { Message, Attachment, FormContext, UserProfile, SRSData } from '../types';
import type { FeedbackAPI } from '../hooks/useFeedback';

const SRSPreviewPanel = lazy(() => import('./srs/SRSPreviewPanel').then(m => ({ default: m.SRSPreviewPanel })));

interface ChatProps {
  messages: Message[];
  isLoading: boolean;
  onSendMessage: (content: string, attachments?: Attachment[]) => void;
  onCommand?: (command: SlashCommand) => void;
  onToast: (type: 'success' | 'error' | 'info', message: string) => void;
  profile?: UserProfile | null;
  currentSessionId?: string | null;
  // SRS mode props
  srsMode?: boolean;
  srsData?: SRSData;
  srsPhase?: string;
  srsBundleStatus?: 'idle' | 'generating' | 'done' | 'error';
  srsBundleId?: string | null;
  onSrsChange?: (data: SRSData) => void;
  onGenerateSrsBundle?: () => void;
  onStopSrsMode?: () => void;
  feedback?: FeedbackAPI;
}

export function Chat({ messages, isLoading, onSendMessage, onCommand, onToast, profile, currentSessionId, srsMode, srsData, srsPhase, srsBundleStatus, srsBundleId, onSrsChange, onGenerateSrsBundle, onStopSrsMode, feedback }: ChatProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [showVoice, setShowVoice] = useState(false);
  const [showImage, setShowImage] = useState(false);
  const [isVoiceListening, setIsVoiceListening] = useState(false);
  const [formContext, setFormContext] = useState<FormContext | null>(null);
  const [showScrollDown, setShowScrollDown] = useState(false);
  const [hasNewMessages, setHasNewMessages] = useState(false);
  const [backendStatus, setBackendStatus] = useState<'connected' | 'disconnected' | 'checking'>('checking');
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [activeArtifactId, setActiveArtifactId] = useState<string | null>(null);
  const [showArtifacts, setShowArtifacts] = useState(false);
  const prevMessageCountRef = useRef(messages.length);

  // Trigger feedback sound when a new assistant message arrives
  useEffect(() => {
    if (messages.length > prevMessageCountRef.current) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg?.role === 'assistant') {
        feedback?.onMessageReceived();
      }
    }
    // Note: prevMessageCountRef is updated in the auto-scroll effect below
  }, [messages.length, feedback]);

  // Auto-scroll to bottom on new messages (smooth)
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    const isNearBottom = distanceFromBottom < 200;

    if (isNearBottom) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    } else if (messages.length > prevMessageCountRef.current) {
      // User is scrolled up and new messages arrived
      setHasNewMessages(true);
    }
    prevMessageCountRef.current = messages.length;
  }, [messages]);

  // Show scroll-to-bottom button when user scrolls up
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const handleScroll = () => {
      const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      setShowScrollDown(distanceFromBottom > 200);
      if (distanceFromBottom < 200) setHasNewMessages(false);
    };
    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  // Backend health check
  useEffect(() => {
    let mounted = true;
    let timeoutId: ReturnType<typeof setTimeout>;
    const checkHealth = async () => {
      try {
        const controller = new AbortController();
        const id = setTimeout(() => controller.abort(), 4000);
        const res = await fetch('/api/health', { signal: controller.signal });
        clearTimeout(id);
        if (mounted) setBackendStatus(res.ok ? 'connected' : 'disconnected');
      } catch {
        if (mounted) setBackendStatus('disconnected');
      }
      if (mounted) timeoutId = setTimeout(checkHealth, 30000);
    };
    checkHealth();
    return () => { mounted = false; clearTimeout(timeoutId); };
  }, []);

  // Network online/offline detection
  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    setHasNewMessages(false);
  }, []);

  // Wrap send to trigger feedback sound/haptic — must be defined BEFORE hooks that use it
  const handleSendWithFeedback = useCallback((content: string, attachments?: Attachment[]) => {
    feedback?.onMessageSent();
    onSendMessage(content, attachments);
  }, [onSendMessage, feedback]);

  const handleVoiceTranscript = useCallback((transcript: string, language: string) => {
    setShowVoice(false);
    setIsVoiceListening(false);
    const msg = formContext
      ? `[Voice Input] ${transcript}\n\n[Language: ${language}, Form: ${formContext.name}]`
      : `[Voice Input] ${transcript}`;
    handleSendWithFeedback(msg);
  }, [formContext, handleSendWithFeedback]);

  const handleToggleVoice = useCallback(() => {
    setShowVoice(prev => !prev);
    setIsVoiceListening(prev => !prev);
    if (!showVoice) setShowImage(false);
  }, [showVoice]);

  const handleToggleImage = useCallback(() => {
    setShowImage(prev => !prev);
    if (!showImage) { setShowVoice(false); setIsVoiceListening(false); }
  }, [showImage]);

  const handleImageReady = useCallback((file: File) => {
    setShowImage(false);
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const base64 = result.split(',')[1];
      const previewUrl = URL.createObjectURL(file);
      const attachment: Attachment = { type: 'image', name: file.name, size: file.size, data: base64, mimeType: file.type, previewUrl };
      const message = formContext
        ? `Please extract data from this image using the form context: ${formContext.name}`
        : 'Please extract data from this image';
      handleSendWithFeedback(message, [attachment]);
      setTimeout(() => URL.revokeObjectURL(previewUrl), 5000);
    };
    reader.readAsDataURL(file);
  }, [formContext, handleSendWithFeedback]);

  const handleSuggestionClick = useCallback((suggestion: string) => { handleSendWithFeedback(suggestion); }, [handleSendWithFeedback]);

  const handleFormContextChange = useCallback((ctx: FormContext | null) => {
    setFormContext(ctx);
    if (ctx) onToast('success', `Form "${ctx.name}" loaded with ${ctx.fieldCount} fields`);
  }, [onToast]);

  // ── Artifact handlers ──────────────────────────────────────────────────────

  const handleOpenArtifact = useCallback(async (messageId: string, attachment: { name: string; data: string; mimeType: string }) => {
    const existing = artifacts.find(a => a.fileName === attachment.name && a.messageId === messageId);
    if (existing) { setActiveArtifactId(existing.id); setShowArtifacts(true); return; }
    try {
      const decoded = atob(attachment.data);
      const isCSV = /\.(csv|tsv)$/i.test(attachment.name);
      if (isCSV) {
        const spreadsheetData = await parseCSVToSpreadsheet(decoded, attachment.name);
        const newArtifact: Artifact = { id: crypto.randomUUID(), type: 'spreadsheet', title: attachment.name, fileName: attachment.name, spreadsheetData, messageId, createdAt: new Date() };
        setArtifacts(prev => [...prev, newArtifact]);
        setActiveArtifactId(newArtifact.id);
        setShowArtifacts(true);
      } else if (/\.(xlsx|xls)$/i.test(attachment.name)) {
        onToast('info', `Opening ${attachment.name} -- Excel files are parsed by the server`);
        onSendMessage(`Parse and show the contents of ${attachment.name} as a table`);
      } else {
        const newArtifact: Artifact = { id: crypto.randomUUID(), type: attachment.name.endsWith('.json') ? 'json' : 'text', title: attachment.name, fileName: attachment.name, textContent: decoded, messageId, createdAt: new Date() };
        setArtifacts(prev => [...prev, newArtifact]);
        setActiveArtifactId(newArtifact.id);
        setShowArtifacts(true);
      }
    } catch { onToast('error', 'Failed to open file'); }
  }, [artifacts, onToast, onSendMessage]);

  const handleCloseArtifact = useCallback((id: string) => {
    setArtifacts(prev => prev.filter(a => a.id !== id));
    if (activeArtifactId === id) {
      const remaining = artifacts.filter(a => a.id !== id);
      setActiveArtifactId(remaining.length > 0 ? remaining[0].id : null);
    }
    if (artifacts.length <= 1) setShowArtifacts(false);
  }, [activeArtifactId, artifacts]);

  const handleUpdateArtifact = useCallback((id: string, updates: Partial<Artifact>) => {
    setArtifacts(prev => prev.map(a => a.id === id ? { ...a, ...updates } : a));
  }, []);

  const handleReferenceInChat = useCallback(async (artifact: Artifact) => {
    if (artifact.type === 'spreadsheet' && artifact.spreadsheetData) {
      const csv = await spreadsheetToCSV(artifact.spreadsheetData);
      handleSendWithFeedback(`[Referencing: ${artifact.fileName} -- ${artifact.spreadsheetData.rows.length} rows, ${artifact.spreadsheetData.headers.length} columns]\n\nData:\n${csv.slice(0, 2000)}${csv.length > 2000 ? '\n... (truncated)' : ''}`);
    } else if (artifact.textContent) {
      handleSendWithFeedback(`[Referencing: ${artifact.fileName}]\n\n${artifact.textContent.slice(0, 2000)}${artifact.textContent.length > 2000 ? '\n... (truncated)' : ''}`);
    }
  }, [handleSendWithFeedback]);

  const handleSaveArtifact = useCallback((artifact: Artifact) => { onToast('success', `${artifact.fileName} saved`); }, [onToast]);
  const handleCloseArtifactPanel = useCallback(() => { setShowArtifacts(false); }, []);

  const showSrsPanel = srsMode && srsData && onSrsChange && onGenerateSrsBundle && onStopSrsMode;

  return (
    <div className="flex flex-1 min-h-0 bg-white relative">
      {/* Main chat column */}
      <div className={`flex flex-col ${showArtifacts && artifacts.length > 0 ? 'flex-1 min-w-0' : showSrsPanel ? 'flex-1 min-w-0' : 'w-full'}`}>
        {/* Loading progress bar */}
        {isLoading && (
          <div className="h-0.5 w-full bg-gray-100 overflow-hidden shrink-0">
            <div className="h-full w-1/4 bg-teal-500 rounded-full progress-bar" />
          </div>
        )}

        {/* Form context panel */}
        <FormContextPanel formContext={formContext} onFormContextChange={handleFormContextChange} />

        {/* Messages area */}
        {/* TODO: Virtualize with react-window when message count exceeds 100+ for scroll performance */}
        <div ref={containerRef} className="flex-1 overflow-y-auto relative scroll-smooth">
          {messages.length === 0 ? (
            <EmptyState onSuggestionClick={handleSuggestionClick} profile={profile} />
          ) : (
            <div className="py-3 sm:py-4">
              {messages.map((message, index) => (
                <ChatMessage
                  key={message.id}
                  message={message}
                  onToast={onToast}
                  isLoading={isLoading}
                  isLastMessage={index === messages.length - 1}
                  onOpenArtifact={handleOpenArtifact}
                  sessionId={currentSessionId ?? undefined}
                />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}

          {/* Scroll to bottom / new messages indicator */}
          {showScrollDown && messages.length > 0 && (
            <div className="sticky bottom-4 flex justify-end pr-4 pointer-events-none z-10">
              <button
                onClick={scrollToBottom}
                className="pointer-events-auto flex items-center gap-1.5 px-3 py-2 bg-white border border-gray-200 rounded-full shadow-md hover:bg-gray-50 transition-all duration-150 active:scale-95 scale-in"
                aria-label={hasNewMessages ? 'New messages below' : 'Scroll to bottom'}
              >
                {hasNewMessages && (
                  <span className="text-xs font-medium text-teal-600">New messages</span>
                )}
                <ArrowDown className="w-4 h-4 text-gray-600" />
              </button>
            </div>
          )}
        </div>

        {/* Connection status */}
        <div className="absolute top-2 right-3 z-10 flex items-center gap-1.5" title={
          !isOnline ? 'No internet connection' :
          backendStatus === 'connected' ? 'Connected' :
          backendStatus === 'disconnected' ? 'Backend unreachable' : 'Checking connection...'
        }>
          <span className={`inline-block w-2 h-2 rounded-full transition-colors duration-300 ${
            !isOnline ? 'bg-red-500' :
            backendStatus === 'connected' ? 'bg-green-500' :
            backendStatus === 'disconnected' ? 'bg-red-500' :
            'bg-gray-400 connection-pulse'
          }`} />
          {!isOnline && (
            <span className="text-xs text-red-500 hidden sm:inline">No internet</span>
          )}
          {isOnline && backendStatus === 'disconnected' && (
            <span className="text-xs text-red-500 hidden sm:inline">Offline</span>
          )}
        </div>

        {/* Network offline banner */}
        {!isOnline && (
          <div className="absolute top-0 left-0 right-0 z-20 bg-red-50 border-b border-red-200 px-4 py-2 text-center">
            <p className="text-xs text-red-700 font-medium">
              Connection lost. Messages will be sent when reconnected.
            </p>
          </div>
        )}

        {/* Voice capture panel */}
        {showVoice && (
          <div className="px-2 sm:px-4 pb-2">
            <VoiceCapture onTranscriptReady={handleVoiceTranscript} />
          </div>
        )}

        {/* Image upload panel */}
        {showImage && (
          <div className="px-2 sm:px-4 pb-2">
            <ImageUpload onImageReady={handleImageReady} />
          </div>
        )}

        {/* Input area */}
        <ChatInput
          onSendMessage={handleSendWithFeedback}
          onCommand={onCommand}
          isLoading={isLoading}
          isListening={isVoiceListening}
          onToggleVoice={handleToggleVoice}
          onImageSelect={handleToggleImage}
        />
      </div>

      {/* Artifact panel */}
      {showArtifacts && artifacts.length > 0 && (
        <ArtifactPanel
          artifacts={artifacts}
          activeArtifactId={activeArtifactId}
          onSelectArtifact={setActiveArtifactId}
          onCloseArtifact={handleCloseArtifact}
          onClosePanel={handleCloseArtifactPanel}
          onUpdateArtifact={handleUpdateArtifact}
          onReferenceInChat={handleReferenceInChat}
          onSaveArtifact={handleSaveArtifact}
        />
      )}

      {/* SRS Preview Panel */}
      {showSrsPanel && (
        <Suspense fallback={<div className="w-[40%] border-l border-gray-200 bg-gray-50 flex items-center justify-center"><div className="w-6 h-6 border-2 border-teal-600 border-t-transparent rounded-full animate-spin" /></div>}>
          <SRSPreviewPanel
            srsData={srsData!}
            phase={srsPhase || 'start'}
            onSrsChange={onSrsChange!}
            onGenerateBundle={onGenerateSrsBundle!}
            bundleStatus={srsBundleStatus || 'idle'}
            bundleId={srsBundleId || null}
            onClose={onStopSrsMode!}
            onItemAdded={feedback?.onItemAdded}
          />
        </Suspense>
      )}
    </div>
  );
}

// ── Empty State ──────────────────────────────────────────────────────────────

interface EmptyStateProps {
  onSuggestionClick: (suggestion: string) => void;
  profile?: UserProfile | null;
}

interface SuggestionItem { icon: React.ReactNode; title: string; description: string; }
interface SuggestionCategory { label: string; icon: React.ReactNode; items: SuggestionItem[]; }

function EmptyState({ onSuggestionClick, profile }: EmptyStateProps) {
  const categories: SuggestionCategory[] = [
    {
      label: 'Build',
      icon: <Wrench className="w-4 h-4" />,
      items: [
        { icon: <Package className="w-5 h-5 text-teal-600" />, title: 'Generate an implementation bundle from SRS', description: 'Create concepts, forms, and mappings from a requirements document' },
        { icon: <Code className="w-5 h-5 text-teal-600" />, title: 'Help me write a skip logic rule', description: 'Generate ViewFilter, Decision, or Validation rules for Avni' },
      ],
    },
    {
      label: 'Learn',
      icon: <GraduationCap className="w-4 h-4" />,
      items: [
        { icon: <BookOpen className="w-5 h-5 text-teal-600" />, title: 'Explain Avni concepts', description: 'Learn about subject types, programs, encounters, and more' },
        { icon: <Mic className="w-5 h-5 text-teal-600" />, title: 'Capture field data with voice', description: 'Dictate observations in any Indian language and map them to form fields' },
      ],
    },
    {
      label: 'Support',
      icon: <HeadphonesIcon className="w-4 h-4" />,
      items: [
        { icon: <RefreshCw className="w-5 h-5 text-teal-600" />, title: 'Troubleshoot a sync issue', description: 'Diagnose and fix data synchronization problems in Avni' },
        { icon: <ImageIcon className="w-5 h-5 text-teal-600" />, title: 'Extract data from an image', description: 'Upload a photo of a register or paper form to extract tabular data' },
      ],
    },
  ];

  const firstName = profile?.name?.split(' ')[0];

  return (
    <div className="flex flex-col items-center justify-center h-full px-3 sm:px-4 text-center">
      <div className="mb-4 empty-state-stagger" style={{ '--stagger-index': 0 } as React.CSSProperties}>
        <AvniLogo size={28} />
      </div>

      <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 mb-2 empty-state-stagger" style={{ '--stagger-index': 1 } as React.CSSProperties}>
        {firstName ? `Hello, ${firstName}!` : 'Welcome to Avni AI'}
      </h2>
      <p className="text-sm text-gray-600 max-w-md mb-6 sm:mb-8 empty-state-stagger" style={{ '--stagger-index': 2 } as React.CSSProperties}>
        {firstName
          ? 'How can I help you today? Pick a suggestion below or type your own question.'
          : 'Your AI-powered assistant for implementing Avni field data collection. I can help you generate bundles, write rules, capture data via voice, extract data from images, and more.'
        }
      </p>

      <div className="max-w-3xl w-full space-y-5 sm:space-y-6">
        {categories.map((category, catIdx) => (
          <div key={category.label} className="empty-state-stagger" style={{ '--stagger-index': catIdx + 3 } as React.CSSProperties}>
            <div className="flex items-center gap-2 mb-2.5 px-1">
              <span className="text-gray-500">{category.icon}</span>
              <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">{category.label}</span>
              <div className="flex-1 h-px bg-gray-100" />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 sm:gap-3">
              {category.items.map((suggestion, itemIdx) => (
                <button
                  key={suggestion.title}
                  onClick={() => onSuggestionClick(suggestion.title)}
                  className="flex items-start gap-3 p-3 rounded-xl border border-gray-200 hover:border-teal-300 hover:bg-teal-50/30 hover:shadow-sm transition-all duration-200 cursor-pointer text-left focus:outline-none focus:ring-2 focus:ring-teal-500 empty-state-card"
                  style={{ '--card-index': catIdx * 2 + itemIdx } as React.CSSProperties}
                >
                  <div className="shrink-0 mt-0.5 w-9 h-9 rounded-lg bg-teal-50 flex items-center justify-center">
                    {suggestion.icon}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-900">{suggestion.title}</p>
                    <p className="text-xs text-gray-500 mt-0.5 hidden sm:block">{suggestion.description}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
