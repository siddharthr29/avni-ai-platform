import { useEffect, useRef, useState } from 'react';
import { Bot, Sparkles } from 'lucide-react';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { VoiceCapture } from './VoiceCapture';
import type { Message, Attachment } from '../types';

interface ChatProps {
  messages: Message[];
  isLoading: boolean;
  onSendMessage: (content: string, attachments?: Attachment[]) => void;
}

export function Chat({ messages, isLoading, onSendMessage }: ChatProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [showVoice, setShowVoice] = useState(false);
  const [isVoiceListening, setIsVoiceListening] = useState(false);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleVoiceTranscript = (transcript: string) => {
    setShowVoice(false);
    setIsVoiceListening(false);
    onSendMessage(`[Voice] ${transcript}`);
  };

  const handleToggleVoice = () => {
    setShowVoice(prev => !prev);
    setIsVoiceListening(prev => !prev);
  };

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Messages area */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto"
      >
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="py-4">
            {messages.map(message => (
              <ChatMessage key={message.id} message={message} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Voice capture panel */}
      {showVoice && (
        <div className="px-4 pb-2">
          <VoiceCapture onTranscriptReady={handleVoiceTranscript} />
        </div>
      )}

      {/* Input area */}
      <ChatInput
        onSendMessage={onSendMessage}
        isLoading={isLoading}
        isListening={isVoiceListening}
        onToggleVoice={handleToggleVoice}
      />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4 text-center">
      <div className="w-16 h-16 bg-primary-100 rounded-2xl flex items-center justify-center mb-4">
        <Bot className="w-8 h-8 text-primary-600" />
      </div>
      <h2 className="text-xl font-semibold text-gray-900 mb-2">Welcome to Avni AI</h2>
      <p className="text-sm text-gray-500 max-w-md mb-6">
        I can help you implement Avni for your field data collection needs.
        Ask me to generate bundles, capture data via voice, extract data from images, or get help with rules.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg w-full">
        <SuggestionCard
          icon={<Sparkles className="w-4 h-4 text-primary-600" />}
          title="Generate a bundle"
          description="Create implementation bundles from an SRS document"
        />
        <SuggestionCard
          icon={<Sparkles className="w-4 h-4 text-primary-600" />}
          title="Voice data entry"
          description="Capture field data using voice in any Indian language"
        />
        <SuggestionCard
          icon={<Sparkles className="w-4 h-4 text-primary-600" />}
          title="Extract from image"
          description="Pull tabular data from photos of registers or forms"
        />
        <SuggestionCard
          icon={<Sparkles className="w-4 h-4 text-primary-600" />}
          title="Write a rule"
          description="Get help writing Avni rules for skip logic or calculations"
        />
      </div>
    </div>
  );
}

function SuggestionCard({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex items-start gap-3 p-3 rounded-xl border border-gray-200 hover:border-primary-300 hover:bg-primary-50/30 transition-colors cursor-pointer text-left">
      <div className="shrink-0 mt-0.5">{icon}</div>
      <div>
        <p className="text-sm font-medium text-gray-900">{title}</p>
        <p className="text-xs text-gray-500 mt-0.5">{description}</p>
      </div>
    </div>
  );
}
