import { useState } from 'react';
import { Mic, MicOff, Globe } from 'lucide-react';
import clsx from 'clsx';
import { useVoice } from '../hooks/useVoice';
import { SUPPORTED_LANGUAGES } from '../types';

interface VoiceCaptureProps {
  onTranscriptReady: (transcript: string, language: string) => void;
  compact?: boolean;
}

export function VoiceCapture({ onTranscriptReady, compact = false }: VoiceCaptureProps) {
  const [language, setLanguage] = useState('en-IN');
  const {
    isListening,
    transcript,
    interimTranscript,
    error,
    isSupported,
    startListening,
    stopListening,
    clearTranscript,
  } = useVoice();

  const handleToggle = () => {
    if (isListening) {
      stopListening();
    } else {
      clearTranscript();
      startListening(language);
    }
  };

  const handleMapToForm = () => {
    if (transcript.trim()) {
      onTranscriptReady(transcript, language);
      clearTranscript();
    }
  };

  if (!isSupported) {
    return (
      <div className="text-sm text-gray-500 p-3">
        Speech recognition is not supported in this browser.
      </div>
    );
  }

  if (compact) {
    return (
      <button
        onClick={handleToggle}
        className={clsx(
          'relative p-2 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500',
          isListening
            ? 'bg-red-100 text-red-600 hover:bg-red-200'
            : 'hover:bg-gray-100 text-gray-500'
        )}
        aria-label={isListening ? 'Stop recording' : 'Start recording'}
        title={isListening ? 'Stop recording' : 'Start voice capture'}
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
    );
  }

  return (
    <div className="mt-2 rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-center gap-3 mb-3">
        {/* Language selector */}
        <div className="flex items-center gap-1.5">
          <Globe className="w-4 h-4 text-gray-400" />
          <select
            value={language}
            onChange={e => setLanguage(e.target.value)}
            className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white"
            disabled={isListening}
          >
            {SUPPORTED_LANGUAGES.map(lang => (
              <option key={lang.code} value={lang.code}>
                {lang.name}
              </option>
            ))}
          </select>
        </div>

        {/* Mic button */}
        <button
          onClick={handleToggle}
          className={clsx(
            'relative flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2',
            isListening
              ? 'bg-red-600 hover:bg-red-700 text-white focus:ring-red-500'
              : 'bg-primary-600 hover:bg-primary-700 text-white focus:ring-primary-500'
          )}
        >
          {isListening && (
            <span className="absolute inset-0 rounded-lg bg-red-400/30 pulse-ring" />
          )}
          {isListening ? (
            <>
              <MicOff className="w-4 h-4 relative z-10" />
              <span className="relative z-10">Stop</span>
            </>
          ) : (
            <>
              <Mic className="w-4 h-4" />
              <span>Record</span>
            </>
          )}
        </button>
      </div>

      {/* Live transcript */}
      {(transcript || interimTranscript || isListening) && (
        <div className="bg-gray-50 rounded-lg p-3 mb-3 min-h-[60px]">
          <p className="text-sm text-gray-800">
            {transcript}
            {interimTranscript && (
              <span className="text-gray-400 italic">{transcript ? ' ' : ''}{interimTranscript}</span>
            )}
            {isListening && !transcript && !interimTranscript && (
              <span className="text-gray-400 italic">Listening...</span>
            )}
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="text-sm text-red-600 mb-3">{error}</p>
      )}

      {/* Map to form button */}
      {transcript && !isListening && (
        <div className="flex justify-end gap-2">
          <button
            onClick={clearTranscript}
            className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            Clear
          </button>
          <button
            onClick={handleMapToForm}
            className="px-4 py-1.5 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
          >
            Send Transcript
          </button>
        </div>
      )}
    </div>
  );
}
