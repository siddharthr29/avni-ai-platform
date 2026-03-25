import { useState, useRef, useCallback, useEffect } from 'react';
import { Send, Paperclip, X, Mic, MicOff, ImageIcon, Package, Code, HeadphonesIcon, FileSpreadsheet, BookOpen, Sparkles, Upload, ArrowUp } from 'lucide-react';
import clsx from 'clsx';
import type { Attachment } from '../types';

// ── Slash Commands ────────────────────────────────────────────────────────────

export interface SlashCommand {
  name: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  viewAction?: 'srs' | 'docs';
  promptTemplate?: string;
  tags: string[];
}

export const SLASH_COMMANDS: SlashCommand[] = [
  { name: 'bundle', label: 'Generate Bundle', description: 'Create an Avni implementation bundle from SRS', icon: <Package className="w-4 h-4" />, promptTemplate: 'Generate an Avni implementation bundle. ', tags: ['bundle', 'generate', 'srs', 'create'] },
  { name: 'rule', label: 'Generate Rule', description: 'Write skip logic, decision, validation rules', icon: <Code className="w-4 h-4" />, promptTemplate: 'Help me write a rule: ', tags: ['rule', 'skip', 'logic', 'decision', 'validation'] },
  { name: 'voice', label: 'Voice Capture', description: 'Dictate field data in any Indian language', icon: <Mic className="w-4 h-4" />, promptTemplate: '[Voice Input] ', tags: ['voice', 'dictate', 'speech'] },
  { name: 'image', label: 'Extract from Image', description: 'Upload a register or form photo to extract data', icon: <ImageIcon className="w-4 h-4" />, promptTemplate: 'Extract data from the attached image. ', tags: ['image', 'extract', 'photo', 'ocr'] },
  { name: 'support', label: 'Troubleshoot', description: 'Diagnose sync issues, data problems, or setup errors', icon: <HeadphonesIcon className="w-4 h-4" />, promptTemplate: 'I need help troubleshooting: ', tags: ['support', 'troubleshoot', 'sync'] },
  { name: 'srs', label: 'SRS Builder', description: 'Open the step-by-step SRS builder', icon: <FileSpreadsheet className="w-4 h-4" />, viewAction: 'srs', tags: ['srs', 'spec', 'requirement'] },
  { name: 'upload', label: 'Upload to Avni', description: 'Upload a generated bundle to your Avni server', icon: <Upload className="w-4 h-4" />, promptTemplate: 'Upload my latest bundle to Avni server. ', tags: ['upload', 'deploy', 'avni'] },
  { name: 'docs', label: 'Documentation', description: 'Browse Avni documentation and guides', icon: <BookOpen className="w-4 h-4" />, viewAction: 'docs', tags: ['docs', 'documentation', 'guide'] },
  { name: 'autofill', label: 'AI Auto-Fill', description: 'Use AI to suggest values for empty SRS fields', icon: <Sparkles className="w-4 h-4" />, promptTemplate: 'Auto-fill the empty fields in my SRS. ', tags: ['autofill', 'ai', 'suggest'] },
];

interface ChatInputProps {
  onSendMessage: (content: string, attachments?: Attachment[]) => void;
  onCommand?: (command: SlashCommand) => void;
  isLoading: boolean;
  isListening: boolean;
  onToggleVoice: () => void;
  onImageSelect: () => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(',')[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export function ChatInput({ onSendMessage, onCommand, isLoading, isListening, onToggleVoice, onImageSelect }: ChatInputProps) {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [showCommands, setShowCommands] = useState(false);
  const [commandFilter, setCommandFilter] = useState('');
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [activeCommand, setActiveCommand] = useState<SlashCommand | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const commandsRef = useRef<HTMLDivElement>(null);

  const filtered = SLASH_COMMANDS.filter(cmd => {
    if (!commandFilter) return true;
    const q = commandFilter.toLowerCase();
    return cmd.name.includes(q) || cmd.label.toLowerCase().includes(q) || cmd.tags.some(t => t.includes(q));
  });

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 144)}px`; // max 6 lines
  }, [text]);

  useEffect(() => { setSelectedIdx(0); }, [commandFilter]);

  // Close dropdown on outside click
  useEffect(() => {
    if (!showCommands) return;
    const handler = (e: MouseEvent) => {
      if (commandsRef.current && !commandsRef.current.contains(e.target as Node)) {
        setShowCommands(false);
        setCommandFilter('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showCommands]);

  const selectCommand = useCallback((cmd: SlashCommand) => {
    setShowCommands(false);
    setCommandFilter('');
    if (cmd.viewAction) { onCommand?.(cmd); setText(''); return; }
    setActiveCommand(cmd);
    setText(cmd.promptTemplate ?? '');
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, [onCommand]);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if ((!trimmed && attachments.length === 0) || isLoading) return;
    onSendMessage(trimmed, attachments.length > 0 ? attachments : undefined);
    setText('');
    setAttachments([]);
    setActiveCommand(null);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }, [text, attachments, isLoading, onSendMessage]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (showCommands && filtered.length > 0) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedIdx(i => (i + 1) % filtered.length); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedIdx(i => (i - 1 + filtered.length) % filtered.length); return; }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); selectCommand(filtered[selectedIdx]); return; }
      if (e.key === 'Escape') { e.preventDefault(); setShowCommands(false); setCommandFilter(''); setText(''); return; }
    }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }, [handleSend, showCommands, filtered, selectedIdx, selectCommand]);

  const handleTextChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setText(val);
    if (val.startsWith('/') && !activeCommand) {
      setCommandFilter(val.slice(1).toLowerCase());
      setShowCommands(true);
    } else if (showCommands && !val.startsWith('/')) {
      setShowCommands(false);
      setCommandFilter('');
    }
  }, [activeCommand, showCommands]);

  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>, type: 'file' | 'image') => {
    const files = e.target.files;
    if (!files) return;
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const base64 = await fileToBase64(file);
      const previewUrl = type === 'image' ? URL.createObjectURL(file) : undefined;
      setAttachments(prev => [...prev, { type, name: file.name, size: file.size, data: base64, mimeType: file.type, previewUrl }]);
    }
    e.target.value = '';
  }, []);

  const removeAttachment = useCallback((index: number) => {
    setAttachments(prev => {
      const removed = prev[index];
      if (removed.previewUrl) URL.revokeObjectURL(removed.previewUrl);
      return prev.filter((_, i) => i !== index);
    });
  }, []);

  const canSend = (text.trim().length > 0 || attachments.length > 0) && !isLoading;
  const charCount = text.length;

  return (
    <div className="border-t border-gray-200 bg-white px-2 sm:px-4 py-2 sm:py-3 sticky bottom-0">
      {/* Slash command dropdown */}
      {showCommands && filtered.length > 0 && (
        <div ref={commandsRef} className="mb-2 border border-gray-200 rounded-xl bg-white shadow-lg overflow-hidden max-h-[320px] overflow-y-auto">
          <div className="px-3 py-1.5 border-b border-gray-100 bg-gray-50">
            <span className="text-[11px] font-medium uppercase tracking-wider text-gray-500">Commands</span>
          </div>
          {filtered.map((cmd, idx) => (
            <button
              key={cmd.name}
              onClick={() => selectCommand(cmd)}
              onMouseEnter={() => setSelectedIdx(idx)}
              className={clsx(
                'w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors',
                idx === selectedIdx ? 'bg-teal-50 text-teal-900' : 'hover:bg-gray-50 text-gray-700'
              )}
            >
              <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center shrink-0', idx === selectedIdx ? 'bg-teal-100 text-teal-600' : 'bg-gray-100 text-gray-500')}>
                {cmd.icon}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">/{cmd.name}</span>
                  <span className="text-xs text-gray-500">{cmd.label}</span>
                </div>
                <p className="text-xs text-gray-500 truncate">{cmd.description}</p>
              </div>
              {idx === selectedIdx && <span className="text-[10px] text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded shrink-0">Enter</span>}
            </button>
          ))}
        </div>
      )}

      {/* Active command banner */}
      {activeCommand && (
        <div className="flex items-center gap-2 mb-2 px-3 py-2 rounded-lg bg-teal-50 border border-teal-200">
          <div className="w-6 h-6 rounded-md bg-teal-100 flex items-center justify-center text-teal-600 shrink-0">{activeCommand.icon}</div>
          <span className="text-sm font-medium text-teal-800">/{activeCommand.name}</span>
          <span className="text-xs text-teal-600">{activeCommand.label}</span>
          <div className="flex-1" />
          <button onClick={() => { setActiveCommand(null); setText(''); textareaRef.current?.focus(); }} className="p-0.5 rounded hover:bg-teal-100 text-teal-400 hover:text-teal-600 transition-colors" aria-label="Clear command">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Attachment chips */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {attachments.map((att, index) => (
            <div key={index} className="flex items-center gap-1.5 bg-gray-100 rounded-lg px-2.5 py-1.5 text-xs text-gray-700">
              {att.type === 'image' && att.previewUrl ? (
                <img src={att.previewUrl} alt={att.name} className="w-8 h-8 object-cover rounded" />
              ) : att.type === 'image' ? (
                <ImageIcon className="w-3.5 h-3.5 text-gray-500" />
              ) : (
                <Paperclip className="w-3.5 h-3.5 text-gray-500" />
              )}
              <div className="flex flex-col">
                <span className="truncate max-w-[120px]">{att.name}</span>
                <span className="text-gray-500 text-xs">{formatFileSize(att.size)}</span>
              </div>
              <button onClick={() => removeAttachment(index)} className="p-0.5 rounded hover:bg-gray-200 transition-colors" aria-label={`Remove ${att.name}`}>
                <X className="w-3 h-3 text-gray-500" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input row */}
      <div className="flex items-end gap-1 sm:gap-2">
        <button onClick={() => fileInputRef.current?.click()} className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors shrink-0" aria-label="Attach file" title="Attach file (.xlsx, .csv, .json, .zip)">
          <Paperclip className="w-5 h-5" />
        </button>

        <button onClick={onToggleVoice} className={clsx('relative p-2 rounded-lg transition-colors shrink-0', isListening ? 'bg-red-100 text-red-600 hover:bg-red-200' : 'hover:bg-gray-100 text-gray-500')} aria-label={isListening ? 'Stop recording' : 'Start voice capture'}>
          {isListening && <span className="absolute inset-0 rounded-lg bg-red-400/30 pulse-ring" />}
          {isListening ? <MicOff className="w-5 h-5 relative z-10" /> : <Mic className="w-5 h-5" />}
        </button>

        <div className="flex-1 relative min-w-0">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleTextChange}
            onKeyDown={handleKeyDown}
            placeholder="Type / for commands, or ask a question..."
            rows={1}
            className="w-full resize-none rounded-xl border border-gray-300 px-3 sm:px-4 py-2.5 pr-12 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500 transition-colors"
            disabled={isLoading}
            style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
          />
          {charCount > 0 && (
            <span className="absolute right-3 bottom-2.5 text-[10px] text-gray-400">{charCount}</span>
          )}
        </div>

        <button
          onClick={handleSend}
          disabled={!canSend}
          className={clsx(
            'p-2.5 rounded-xl transition-colors shrink-0',
            canSend
              ? 'bg-teal-600 hover:bg-teal-700 text-white'
              : 'bg-gray-100 text-gray-300 cursor-not-allowed opacity-50'
          )}
          aria-label="Send message"
        >
          <ArrowUp className="w-5 h-5" />
        </button>
      </div>

      {/* Hidden file inputs */}
      <input ref={fileInputRef} type="file" accept=".xlsx,.csv,.json,.zip" multiple className="hidden" onChange={e => handleFileChange(e, 'file')} />
      <input ref={imageInputRef} type="file" accept="image/*" className="hidden" onChange={e => handleFileChange(e, 'image')} />
    </div>
  );
}
