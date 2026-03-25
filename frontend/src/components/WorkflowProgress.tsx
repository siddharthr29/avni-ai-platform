import { useMemo, memo } from 'react';
import { CheckCircle2, Circle, XCircle, Loader2, Cpu, Zap } from 'lucide-react';
import { cn } from '../lib/utils';

// ── Types ────────────────────────────────────────────────────────────────────

export interface WorkflowStepData {
  id: string;
  name: string;
  description: string;
  status: 'pending' | 'running' | 'waiting_approval' | 'completed' | 'failed' | 'skipped';
  resultSummary?: string;
  providerUsed?: string;
}

export interface WorkflowProgressProps {
  workflowId: string;
  name: string;
  steps: WorkflowStepData[];
  currentStepIndex: number;
  status: 'pending' | 'running' | 'paused' | 'completed' | 'failed';
  currentDetail?: string;
  provider?: string;
  tokensUsed?: number;
  tokensBudget?: number;
}

// ── Component ────────────────────────────────────────────────────────────────

export const WorkflowProgress = memo(function WorkflowProgress({
  name,
  steps,
  currentStepIndex,
  status,
  currentDetail,
  provider,
  tokensUsed,
  tokensBudget,
}: WorkflowProgressProps) {
  const progressPercent = useMemo(() => {
    if (steps.length === 0) return 0;
    const completed = steps.filter(
      (s) => s.status === 'completed' || s.status === 'skipped'
    ).length;
    // If a step is running, count it as partially done
    const running = steps.some((s) => s.status === 'running') ? 0.5 : 0;
    return Math.round(((completed + running) / steps.length) * 100);
  }, [steps]);

  const tokenPercent = useMemo(() => {
    if (!tokensUsed || !tokensBudget) return 0;
    return Math.min(100, Math.round((tokensUsed / tokensBudget) * 100));
  }, [tokensUsed, tokensBudget]);

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-4 pt-4 pb-3">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-gray-900">{name}</h3>
          <span
            className={cn(
              'text-xs font-medium tabular-nums',
              status === 'completed'
                ? 'text-green-600'
                : status === 'failed'
                  ? 'text-red-600'
                  : 'text-teal-700'
            )}
          >
            {progressPercent}%
          </span>
        </div>

        {/* Progress bar */}
        <div className="h-1.5 w-full rounded-full bg-gray-100 overflow-hidden">
          <div
            className={cn(
              'h-full rounded-full transition-all duration-500 ease-out',
              status === 'completed'
                ? 'bg-green-500'
                : status === 'failed'
                  ? 'bg-red-500'
                  : 'bg-teal-500'
            )}
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Steps list */}
      <div className="px-4 pb-3 space-y-1">
        {steps.map((step, index) => (
          <StepRow
            key={step.id}
            step={step}
            isCurrent={index === currentStepIndex && status === 'running'}
          />
        ))}
      </div>

      {/* Footer: current detail, provider, tokens */}
      {(currentDetail || provider || tokensUsed) && (
        <div className="px-4 pb-4 space-y-2 border-t border-gray-100 pt-3">
          {currentDetail && (
            <p className="text-xs text-gray-600 truncate">
              <span className="font-medium text-gray-700">Current:</span>{' '}
              {currentDetail}
            </p>
          )}

          <div className="flex items-center gap-3 flex-wrap">
            {provider && (
              <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                <Cpu className="w-3 h-3" />
                {provider}
              </span>
            )}

            {tokensUsed != null && tokensBudget != null && (
              <span className="inline-flex items-center gap-1 text-xs text-gray-600">
                <Zap className="w-3 h-3" />
                <span className="tabular-nums">
                  {tokensUsed.toLocaleString()} / {tokensBudget.toLocaleString()}
                </span>
                <span className="ml-1 h-1 w-12 rounded-full bg-gray-100 overflow-hidden inline-block align-middle">
                  <span
                    className="block h-full rounded-full bg-teal-400 transition-all duration-300"
                    style={{ width: `${tokenPercent}%` }}
                  />
                </span>
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
});

// ── Step Row ─────────────────────────────────────────────────────────────────

function StepRow({
  step,
  isCurrent,
}: {
  step: WorkflowStepData;
  isCurrent: boolean;
}) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-lg px-2 py-1.5 transition-colors',
        isCurrent && 'bg-teal-50'
      )}
    >
      <StepIcon status={step.status} />
      <span
        className={cn(
          'text-sm flex-1 min-w-0 truncate',
          step.status === 'completed'
            ? 'text-gray-700'
            : step.status === 'running' || isCurrent
              ? 'text-teal-700 font-medium'
              : step.status === 'failed'
                ? 'text-red-700'
                : 'text-gray-400'
        )}
      >
        {step.name}
      </span>
      {step.resultSummary && (
        <span className="text-xs text-gray-500 shrink-0 tabular-nums">
          {step.resultSummary}
        </span>
      )}
    </div>
  );
}

// ── Step Icon ────────────────────────────────────────────────────────────────

function StepIcon({ status }: { status: WorkflowStepData['status'] }) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />;
    case 'running':
      return <Loader2 className="w-4 h-4 text-teal-500 shrink-0 animate-spin" />;
    case 'waiting_approval':
      return <Loader2 className="w-4 h-4 text-amber-500 shrink-0 animate-spin" />;
    case 'failed':
      return <XCircle className="w-4 h-4 text-red-500 shrink-0" />;
    case 'skipped':
      return <Circle className="w-4 h-4 text-gray-300 shrink-0" />;
    case 'pending':
    default:
      return <Circle className="w-4 h-4 text-gray-300 shrink-0" />;
  }
}
