import { useState } from 'react';
import { Copy, Check, ThumbsUp, ThumbsDown, MessageSquareText, Send } from 'lucide-react';
import clsx from 'clsx';
import { authFetch } from '../../services/api';

interface MessageFeedbackProps {
  messageId: string;
  sessionId?: string;
  content: string;
  onToast: (type: 'success' | 'error' | 'info', message: string) => void;
}

export function MessageFeedback({ messageId, sessionId, content, onToast }: MessageFeedbackProps) {
  const [copiedContent, setCopiedContent] = useState(false);
  const [rating, setRating] = useState<'up' | 'down' | null>(null);
  const [showCorrection, setShowCorrection] = useState(false);
  const [correction, setCorrection] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleCopyContent = async () => {
    await navigator.clipboard.writeText(content);
    setCopiedContent(true);
    onToast('success', 'Message copied to clipboard');
    setTimeout(() => setCopiedContent(false), 2000);
  };

  const submitFeedback = async (r: 'up' | 'down', correctionText?: string) => {
    setSubmitting(true);
    try {
      await authFetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId || 'unknown',
          message_id: messageId,
          rating: correctionText ? 'correction' : r,
          correction: correctionText || undefined,
        }),
      });
      setRating(r);
      if (correctionText) {
        setShowCorrection(false);
        setCorrection('');
        onToast('success', 'Correction saved -- AI will learn from this');
      }
    } catch {
      onToast('error', 'Failed to submit feedback');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col mt-1">
      <div className="flex items-center gap-2">
        {/* Copy button */}
        <button
          onClick={handleCopyContent}
          className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 opacity-0 group-hover:opacity-100 transition-opacity"
          title="Copy message"
        >
          {copiedContent ? (
            <><Check className="w-3.5 h-3.5" /> Copied</>
          ) : (
            <><Copy className="w-3.5 h-3.5" /> Copy</>
          )}
        </button>

        {/* Feedback buttons */}
        {rating && !showCorrection ? (
          <div className="flex items-center gap-1.5">
            <span className={clsx('text-xs', rating === 'up' ? 'text-green-500' : 'text-gray-500')}>
              {rating === 'up' ? <ThumbsUp className="w-3.5 h-3.5 fill-current" /> : <ThumbsDown className="w-3.5 h-3.5 fill-current" />}
            </span>
            <span className="text-[10px] text-gray-500">Thanks for the feedback</span>
            {rating === 'down' && (
              <button onClick={() => setShowCorrection(true)} className="text-[10px] text-teal-600 hover:text-teal-800 underline">
                Add correction
              </button>
            )}
          </div>
        ) : !showCorrection ? (
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={() => submitFeedback('up')}
              disabled={submitting}
              className="p-1 rounded hover:bg-gray-100 text-gray-500 hover:text-green-500 transition-colors"
              title="Good response"
            >
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => { setRating('down'); setShowCorrection(true); }}
              disabled={submitting}
              className="p-1 rounded hover:bg-gray-100 text-gray-500 hover:text-red-400 transition-colors"
              title="Bad response"
            >
              <ThumbsDown className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : null}
      </div>

      {/* Correction input */}
      {showCorrection && (
        <div className="mt-2 border border-gray-200 rounded-lg p-2 bg-white">
          <div className="flex items-center gap-1.5 mb-1.5">
            <MessageSquareText className="w-3.5 h-3.5 text-gray-500" />
            <span className="text-xs font-medium text-gray-600">What should the correct response be?</span>
          </div>
          <div className="flex gap-2">
            <input
              value={correction}
              onChange={e => setCorrection(e.target.value)}
              placeholder="Type correction... (indexed for future learning)"
              className="flex-1 text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-teal-500"
              onKeyDown={e => { if (e.key === 'Enter' && correction.trim()) submitFeedback('down', correction.trim()); }}
              autoFocus
            />
            <button
              onClick={() => correction.trim() && submitFeedback('down', correction.trim())}
              disabled={!correction.trim() || submitting}
              className="p-1.5 rounded-lg bg-teal-600 text-white disabled:opacity-40 hover:bg-teal-700 transition-colors"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => { setShowCorrection(false); submitFeedback('down'); }}
              className="text-xs text-gray-500 hover:text-gray-700 px-2"
            >
              Skip
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
