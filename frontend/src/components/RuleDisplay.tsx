import { useState } from 'react';
import { Copy, Check, Play, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import { testRule } from '../services/api';

interface RuleDisplayProps {
  code: string;
  ruleType?: string;
}

const RULE_TYPE_COLORS: Record<string, string> = {
  ViewFilter: 'bg-blue-100 text-blue-800',
  Decision: 'bg-purple-100 text-purple-800',
  VisitSchedule: 'bg-green-100 text-green-800',
  Validation: 'bg-orange-100 text-orange-800',
  Checklists: 'bg-teal-100 text-teal-800',
  EnrolmentSummary: 'bg-indigo-100 text-indigo-800',
};

export function RuleDisplay({ code, ruleType }: RuleDisplayProps) {
  const [copied, setCopied] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; output?: string; error?: string } | null>(null);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleTest = async () => {
    setIsTesting(true);
    setTestResult(null);
    try {
      const result = await testRule(code, ruleType ?? 'ViewFilter');
      setTestResult(result);
    } catch (err) {
      setTestResult({ success: false, error: err instanceof Error ? err.message : 'Test failed' });
    } finally {
      setIsTesting(false);
    }
  };

  const badgeColor = ruleType ? (RULE_TYPE_COLORS[ruleType] ?? 'bg-gray-100 text-gray-800') : null;

  return (
    <div className="my-2 rounded-lg overflow-hidden border border-gray-200">
      <div className="bg-gray-800 px-3 py-1.5 flex items-center gap-2">
        <span className="text-xs text-gray-400">javascript</span>
        {ruleType && badgeColor && (
          <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium', badgeColor)}>
            {ruleType}
          </span>
        )}
        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={handleTest}
            disabled={isTesting}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-50 px-1.5 py-0.5 rounded hover:bg-gray-700"
          >
            {isTesting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Testing...
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" />
                Test Rule
              </>
            )}
          </button>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors px-1.5 py-0.5 rounded hover:bg-gray-700"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5" />
                Copied
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                Copy
              </>
            )}
          </button>
        </div>
      </div>
      <pre className="bg-gray-900 p-3 overflow-x-auto">
        <code className="text-xs text-gray-200 font-mono whitespace-pre">{code}</code>
      </pre>

      {testResult && (
        <div className={clsx(
          'px-3 py-2 text-xs border-t',
          testResult.success
            ? 'bg-green-50 border-green-200 text-green-800'
            : 'bg-red-50 border-red-200 text-red-800'
        )}>
          {testResult.success ? (
            <div>
              <span className="font-medium">Test passed.</span>
              {testResult.output && (
                <pre className="mt-1 text-xs font-mono whitespace-pre-wrap">{testResult.output}</pre>
              )}
            </div>
          ) : (
            <div>
              <span className="font-medium">Test failed:</span>{' '}
              {testResult.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
