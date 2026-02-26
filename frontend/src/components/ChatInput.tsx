import { useState, useRef, useCallback, useEffect } from 'react';
import { Send, Paperclip, X, Mic, MicOff, ImageIcon } from 'lucide-react';
import clsx from 'clsx';
import type { Attachment } from '../types';

interface ChatInputProps {
  onSendMessage: (content: string, attachments?: Attachment[]) => void;
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
    reader.onload = () => {
      const result = reader.result as string;
      // Remove data URL prefix (e.g., "data:image/png;base64,")
      const base64 = result.split(',')[1];
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export function ChatInput({ onSendMessage, isLoading, isListening, onToggleVoice, onImageSelect }: ChatInputProps) {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  const adjustTextareaHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    const maxHeight = 6 * 24; // 6 lines * ~24px line height
    textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`;
  }, []);

  useEffect(() => {
    adjustTextareaHeight();
  }, [text, adjustTextareaHeight]);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed && attachments.length === 0) return;
    if (isLoading) return;

    onSendMessage(trimmed, attachments.length > 0 ? attachments : undefined);
    setText('');
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [text, attachments, isLoading, onSendMessage]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>, type: 'file' | 'image') => {
    const files = e.target.files;
    if (!files) return;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const base64 = await fileToBase64(file);

      let previewUrl: string | undefined;
      if (type === 'image') {
        previewUrl = URL.createObjectURL(file);
      }

      const attachment: Attachment = {
        type,
        name: file.name,
        size: file.size,
        data: base64,
        mimeType: file.type,
        previewUrl,
      };
      setAttachments(prev => [...prev, attachment]);
    }

    // Reset input
    e.target.value = '';
  }, []);

  const removeAttachment = useCallback((index: number) => {
    setAttachments(prev => {
      const removed = prev[index];
      if (removed.previewUrl) {
        URL.revokeObjectURL(removed.previewUrl);
      }
      return prev.filter((_, i) => i !== index);
    });
  }, []);

  const canSend = (text.trim().length > 0 || attachments.length > 0) && !isLoading;

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3 sticky bottom-0">
      {/* Attachment chips */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {attachments.map((att, index) => (
            <div
              key={index}
              className="flex items-center gap-1.5 bg-gray-100 rounded-lg px-2.5 py-1.5 text-xs text-gray-700"
            >
              {att.type === 'image' && att.previewUrl ? (
                <img
                  src={att.previewUrl}
                  alt={att.name}
                  className="w-8 h-8 object-cover rounded"
                />
              ) : att.type === 'image' ? (
                <ImageIcon className="w-3.5 h-3.5 text-gray-500" />
              ) : (
                <Paperclip className="w-3.5 h-3.5 text-gray-500" />
              )}
              <div className="flex flex-col">
                <span className="truncate max-w-[120px]">{att.name}</span>
                <span className="text-gray-400 text-[10px]">{formatFileSize(att.size)}</span>
              </div>
              <button
                onClick={() => removeAttachment(index)}
                className="p-0.5 rounded hover:bg-gray-200 transition-colors"
                aria-label={`Remove ${att.name}`}
              >
                <X className="w-3 h-3 text-gray-400" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-end gap-2">
        {/* Attach file */}
        <button
          onClick={() => fileInputRef.current?.click()}
          className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 shrink-0"
          aria-label="Attach file"
          title="Attach file (.xlsx, .csv, .json, .zip)"
        >
          <Paperclip className="w-5 h-5" />
        </button>

        {/* Attach image */}
        <button
          onClick={() => {
            onImageSelect();
            imageInputRef.current?.click();
          }}
          className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 shrink-0 md:block"
          aria-label="Upload image"
          title="Upload image"
        >
          <ImageIcon className="w-5 h-5" />
        </button>

        {/* Voice toggle */}
        <button
          onClick={onToggleVoice}
          className={clsx(
            'relative p-2 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 shrink-0',
            isListening
              ? 'bg-red-100 text-red-600 hover:bg-red-200'
              : 'hover:bg-gray-100 text-gray-500'
          )}
          aria-label={isListening ? 'Stop recording' : 'Start voice capture'}
          title={isListening ? 'Stop recording' : 'Voice capture'}
        >
          {isListening && (
            <span className="absolute inset-0 rounded-lg bg-red-400/30 pulse-ring" />
          )}
          {isListening ? (
            <MicOff className="w-5 h-5 relative z-10" />
          ) : (
            <Mic className="w-5 h-5" />
          )}
        </button>

        {/* Text input */}
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            rows={1}
            className="w-full resize-none rounded-xl border border-gray-300 px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
            disabled={isLoading}
          />
        </div>

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={!canSend}
          className={clsx(
            'p-2.5 rounded-xl transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 shrink-0',
            canSend
              ? 'bg-primary-600 hover:bg-primary-700 text-white'
              : 'bg-gray-100 text-gray-300 cursor-not-allowed'
          )}
          aria-label="Send message"
        >
          <Send className="w-5 h-5" />
        </button>
      </div>

      {/* Hidden file inputs */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".xlsx,.csv,.json,.zip"
        multiple
        className="hidden"
        onChange={e => handleFileChange(e, 'file')}
      />
      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={e => handleFileChange(e, 'image')}
      />
    </div>
  );
}
