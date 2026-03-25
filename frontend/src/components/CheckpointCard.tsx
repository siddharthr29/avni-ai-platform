import { useState, useCallback, memo } from 'react';
import { Check, X, Pencil, Pause, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '../lib/utils';

// ── Types ────────────────────────────────────────────────────────────────────

export interface CheckpointCardProps {
  workflowId: string;
  stepId: string;
  stepName: string;
  checkpointLevel: 'review' | 'approve' | 'block';
  summary: string;
  details?: Record<string, any>;
  onApprove: (workflowId: string, stepId: string, feedback?: string) => void;
  onReject: (workflowId: string, stepId: string, feedback: string) => void;
  onEdit?: (workflowId: string, stepId: string) => void;
}

type CardState = 'waiting' | 'approved' | 'rejected';

// ── Component ────────────────────────────────────────────────────────────────

export const CheckpointCard = memo(function CheckpointCard({
  workflowId,
  stepId,
  stepName,
  checkpointLevel,
  summary,
  details,
  onApprove,
  onReject,
  onEdit,
}: CheckpointCardProps) {
  const [state, setState] = useState<CardState>('waiting');
  const [feedback, setFeedback] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [showConfirmApprove, setShowConfirmApprove] = useState(false);

  const handleApprove = useCallback(() => {
    // APPROVE level requires a confirmation dialog
    if (checkpointLevel === 'approve' && !showConfirmApprove) {
      setShowConfirmApprove(true);
      return;
    }
    setState('approved');
    onApprove(workflowId, stepId, feedback || undefined);
  }, [checkpointLevel, showConfirmApprove, workflowId, stepId, feedback, onApprove]);

  const handleReject = useCallback(() => {
    if (!showRejectInput) {
      setShowRejectInput(true);
      return;
    }
    if (!feedback.trim()) return;
    setState('rejected');
    onReject(workflowId, stepId, feedback);
  }, [showRejectInput, feedback, workflowId, stepId, onReject]);

  const handleEdit = useCallback(() => {
    onEdit?.(workflowId, stepId);
  }, [onEdit, workflowId, stepId]);

  const handleCancelReject = useCallback(() => {
    setShowRejectInput(false);
    setFeedback('');
  }, []);

  const handleCancelConfirm = useCallback(() => {
    setShowConfirmApprove(false);
  }, []);

  // ── Styles based on state ──────────────────────────────────────────────

  const cardStyles = {
    waiting: 'bg-amber-50 border-amber-200',
    approved: 'bg-green-50 border-green-200',
    rejected: 'bg-red-50 border-red-200',
  };

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div
      className={cn(
        'rounded-xl border shadow-sm overflow-hidden transition-colors duration-300',
        cardStyles[state]
      )}
    >
      {/* Header */}
      <div className="px-4 pt-4 pb-2">
        <div className="flex items-center gap-2 mb-1">
          {state === 'waiting' && (
            <Pause className="w-4 h-4 text-amber-600 shrink-0" />
          )}
          {state === 'approved' && (
            <Check className="w-4 h-4 text-green-600 shrink-0" />
          )}
          {state === 'rejected' && (
            <X className="w-4 h-4 text-red-600 shrink-0" />
          )}

          <h3 className="text-sm font-semibold text-gray-900 flex-1 min-w-0">
            {state === 'waiting' && 'Checkpoint: '}
            {state === 'approved' && 'Approved: '}
            {state === 'rejected' && 'Rejected: '}
            {stepName}
          </h3>

          {state !== 'waiting' && (
            <span
              className={cn(
                'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
                state === 'approved'
                  ? 'bg-green-100 text-green-700'
                  : 'bg-red-100 text-red-700'
              )}
            >
              {state === 'approved' ? (
                <>
                  <Check className="w-3 h-3" /> Approved
                </>
              ) : (
                <>
                  <X className="w-3 h-3" /> Rejected
                </>
              )}
            </span>
          )}
        </div>
      </div>

      {/* Summary */}
      <div className="px-4 pb-3">
        <p className="text-sm text-gray-700 whitespace-pre-line">{summary}</p>
      </div>

      {/* Details (collapsible) */}
      {details && Object.keys(details).length > 0 && (
        <div className="px-4 pb-3">
          <button
            onClick={() => setShowDetails((v) => !v)}
            className="inline-flex items-center gap-1 text-xs font-medium text-teal-700 hover:text-teal-800 transition-colors"
          >
            {showDetails ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
            {showDetails ? 'Hide Details' : 'View Details'}
          </button>

          {showDetails && (
            <div className="mt-2 rounded-lg bg-white/60 border border-gray-100 p-3 space-y-1.5">
              {Object.entries(details).map(([key, value]) => (
                <div key={key} className="flex items-start gap-2 text-xs">
                  <span className="font-medium text-gray-600 shrink-0">
                    {key}:
                  </span>
                  <span className="text-gray-700 break-all">
                    {typeof value === 'object'
                      ? JSON.stringify(value, null, 2)
                      : String(value)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Approve confirmation for APPROVE-level checkpoints */}
      {showConfirmApprove && state === 'waiting' && (
        <div className="px-4 pb-3">
          <div className="rounded-lg border border-amber-300 bg-amber-100/60 p-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-medium text-amber-800">
                  This will upload to Avni
                </p>
                <p className="text-xs text-amber-700 mt-0.5">
                  Are you sure you want to approve? This action cannot be undone.
                </p>
                <div className="flex items-center gap-2 mt-2">
                  <button
                    onClick={handleApprove}
                    className="inline-flex items-center gap-1 rounded-md bg-teal-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-teal-700 transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-1"
                  >
                    <Check className="w-3 h-3" />
                    Confirm Approve
                  </button>
                  <button
                    onClick={handleCancelConfirm}
                    className="inline-flex items-center rounded-md px-3 py-1.5 text-xs font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-100 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Action buttons — only shown in waiting state */}
      {state === 'waiting' && !showConfirmApprove && (
        <div className="px-4 pb-4 space-y-3">
          {/* Reject feedback input */}
          {showRejectInput && (
            <div className="space-y-2">
              <label className="block text-xs font-medium text-gray-700">
                Reason for rejection (required):
              </label>
              <textarea
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="Explain what needs to change..."
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent resize-none"
                rows={2}
                autoFocus
              />
              <div className="flex items-center gap-2">
                <button
                  onClick={handleReject}
                  disabled={!feedback.trim()}
                  className={cn(
                    'inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1',
                    feedback.trim()
                      ? 'bg-red-100 text-red-700 hover:bg-red-200'
                      : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  )}
                >
                  <X className="w-3 h-3" />
                  Confirm Reject
                </button>
                <button
                  onClick={handleCancelReject}
                  className="inline-flex items-center rounded-md px-3 py-1.5 text-xs font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-100 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Main action buttons */}
          {!showRejectInput && (
            <div className="flex items-center gap-2">
              <button
                onClick={handleApprove}
                className="inline-flex items-center gap-1.5 rounded-md bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-700 transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-1"
              >
                <Check className="w-4 h-4" />
                Approve
              </button>

              {onEdit && (
                <button
                  onClick={handleEdit}
                  className="inline-flex items-center gap-1.5 rounded-md bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 transition-colors focus:outline-none focus:ring-2 focus:ring-gray-400 focus:ring-offset-1"
                >
                  <Pencil className="w-4 h-4" />
                  Edit
                </button>
              )}

              <button
                onClick={handleReject}
                className="inline-flex items-center gap-1.5 rounded-md bg-red-100 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-200 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1"
              >
                <X className="w-4 h-4" />
                Reject
              </button>
            </div>
          )}

          {/* Optional feedback for approval */}
          {!showRejectInput && (
            <div>
              <input
                type="text"
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="Optional feedback..."
                className="w-full rounded-lg border border-gray-200 bg-white/60 px-3 py-1.5 text-xs text-gray-700 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
});
