import { useState, useMemo, useCallback, memo } from 'react';
import { Search, Send, SkipForward, Lightbulb } from 'lucide-react';
import { cn } from '../lib/utils';

// ── Types ────────────────────────────────────────────────────────────────────

export interface ClarityQuestion {
  id: string;
  category: string;
  severity: 'critical' | 'important' | 'nice_to_have';
  question: string;
  context: string;
  suggestions: string[];
  default?: string;
}

export interface AmbiguityResolverProps {
  questions: ClarityQuestion[];
  onSubmit: (answers: Record<string, string>) => void;
  onSkipAll?: () => void;
  similarOrgs?: string[];
}

// ── Component ────────────────────────────────────────────────────────────────

export const AmbiguityResolver = memo(function AmbiguityResolver({
  questions,
  onSubmit,
  onSkipAll,
  similarOrgs,
}: AmbiguityResolverProps) {
  const [answers, setAnswers] = useState<Record<string, string>>(() => {
    // Pre-fill defaults
    const initial: Record<string, string> = {};
    for (const q of questions) {
      if (q.default) {
        initial[q.id] = q.default;
      }
    }
    return initial;
  });

  const [submitted, setSubmitted] = useState(false);

  const criticalIds = useMemo(
    () => new Set(questions.filter((q) => q.severity === 'critical').map((q) => q.id)),
    [questions]
  );

  const allCriticalAnswered = useMemo(() => {
    for (const id of criticalIds) {
      if (!answers[id]) return false;
    }
    return true;
  }, [criticalIds, answers]);

  const hasNonCriticalOnly = useMemo(
    () => criticalIds.size === 0 && questions.length > 0,
    [criticalIds, questions]
  );

  const handleSelect = useCallback((questionId: string, value: string) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
  }, []);

  const handleSubmit = useCallback(() => {
    if (!allCriticalAnswered) return;
    setSubmitted(true);
    onSubmit(answers);
  }, [allCriticalAnswered, answers, onSubmit]);

  const handleSkipAll = useCallback(() => {
    setSubmitted(true);
    onSkipAll?.();
  }, [onSkipAll]);

  if (submitted) {
    return (
      <div className="rounded-xl border border-green-200 bg-green-50 px-4 py-3">
        <p className="text-sm text-green-700 font-medium">
          Answers submitted. Continuing workflow...
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-4 pt-4 pb-2">
        <div className="flex items-center gap-2">
          <Search className="w-4 h-4 text-blue-600 shrink-0" />
          <h3 className="text-sm font-semibold text-gray-900">
            Need your input
            <span className="ml-1.5 text-xs font-normal text-gray-600">
              ({questions.length} question{questions.length !== 1 ? 's' : ''})
            </span>
          </h3>
        </div>
      </div>

      {/* Questions */}
      <div className="px-4 pb-3 space-y-4">
        {questions.map((question, index) => (
          <QuestionBlock
            key={question.id}
            question={question}
            index={index + 1}
            selectedValue={answers[question.id] ?? ''}
            onSelect={(value) => handleSelect(question.id, value)}
          />
        ))}
      </div>

      {/* Similar orgs hint */}
      {similarOrgs && similarOrgs.length > 0 && (
        <div className="px-4 pb-3">
          <div className="inline-flex items-center gap-1.5 rounded-full bg-teal-50 px-2.5 py-1 text-xs text-teal-700">
            <Lightbulb className="w-3 h-3" />
            Suggestions based on similar orgs ({similarOrgs.join(', ')})
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="px-4 pb-4 flex items-center gap-3">
        <button
          onClick={handleSubmit}
          disabled={!allCriticalAnswered}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-1',
            allCriticalAnswered
              ? 'bg-teal-600 text-white hover:bg-teal-700'
              : 'bg-gray-200 text-gray-400 cursor-not-allowed'
          )}
        >
          <Send className="w-4 h-4" />
          Submit Answers
        </button>

        {onSkipAll && hasNonCriticalOnly && (
          <button
            onClick={handleSkipAll}
            className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 transition-colors"
          >
            <SkipForward className="w-3.5 h-3.5" />
            Skip All
          </button>
        )}

        {!allCriticalAnswered && criticalIds.size > 0 && (
          <span className="text-xs text-gray-500">
            Answer all critical questions to continue
          </span>
        )}
      </div>
    </div>
  );
});

// ── Question Block ───────────────────────────────────────────────────────────

const SEVERITY_DOT: Record<ClarityQuestion['severity'], string> = {
  critical: 'bg-red-500',
  important: 'bg-amber-500',
  nice_to_have: 'bg-gray-400',
};

const SEVERITY_LABEL: Record<ClarityQuestion['severity'], string> = {
  critical: 'Critical',
  important: 'Important',
  nice_to_have: 'Nice to have',
};

function QuestionBlock({
  question,
  index,
  selectedValue,
  onSelect,
}: {
  question: ClarityQuestion;
  index: number;
  selectedValue: string;
  onSelect: (value: string) => void;
}) {
  return (
    <div className="space-y-2">
      {/* Question text */}
      <div className="flex items-start gap-2">
        <span className="text-xs font-semibold text-gray-500 mt-0.5 shrink-0 tabular-nums">
          {index}.
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span
              className={cn(
                'inline-block w-2 h-2 rounded-full shrink-0',
                SEVERITY_DOT[question.severity]
              )}
              title={SEVERITY_LABEL[question.severity]}
            />
            <span className="text-xs text-gray-500">
              {question.category}
              {question.severity === 'critical' && (
                <span className="ml-1 text-red-600 font-medium">*</span>
              )}
            </span>
          </div>
          <p className="text-sm text-gray-800">{question.question}</p>
          {question.context && (
            <p className="text-xs text-gray-500 mt-0.5">{question.context}</p>
          )}
        </div>
      </div>

      {/* Options (radio buttons) */}
      <div className="ml-5 rounded-lg border border-gray-200 bg-white/70 overflow-hidden divide-y divide-gray-100">
        {question.suggestions.map((suggestion) => {
          const isSelected = selectedValue === suggestion;
          return (
            <label
              key={suggestion}
              className={cn(
                'flex items-center gap-2.5 px-3 py-2 cursor-pointer transition-colors hover:bg-teal-50/50',
                isSelected && 'bg-teal-50'
              )}
            >
              <span
                className={cn(
                  'w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center transition-colors',
                  isSelected
                    ? 'border-teal-600'
                    : 'border-gray-300'
                )}
              >
                {isSelected && (
                  <span className="w-2 h-2 rounded-full bg-teal-600" />
                )}
              </span>
              <span
                className={cn(
                  'text-sm truncate',
                  isSelected ? 'text-teal-800 font-medium' : 'text-gray-700'
                )}
              >
                {suggestion}
              </span>
              <input
                type="radio"
                name={`question-${question.id}`}
                value={suggestion}
                checked={isSelected}
                onChange={() => onSelect(suggestion)}
                className="sr-only"
              />
            </label>
          );
        })}
      </div>
    </div>
  );
}
