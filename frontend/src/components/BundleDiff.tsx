import { useState } from 'react';
import { ChevronDown, ChevronRight, Plus, Minus, AlertTriangle } from 'lucide-react';
import clsx from 'clsx';

interface DiffEntry {
  name: string;
  status: 'added' | 'removed' | 'modified' | 'unchanged';
  currentValue?: string;
  newValue?: string;
}

interface DiffSection {
  entityType: string;
  entries: DiffEntry[];
}

interface BundleDiffProps {
  sections: DiffSection[];
  summary?: {
    added: number;
    conflicts: number;
    removals: number;
  };
  orgName?: string;
}

function DiffSectionView({ section }: { section: DiffSection }) {
  const [isExpanded, setIsExpanded] = useState(true);

  const added = section.entries.filter(e => e.status === 'added').length;
  const removed = section.entries.filter(e => e.status === 'removed').length;
  const modified = section.entries.filter(e => e.status === 'modified').length;

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-gray-500" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-500" />
          )}
          <span className="text-sm font-medium text-gray-900">{section.entityType}</span>
          <span className="text-xs text-gray-400">({section.entries.length} items)</span>
        </div>
        <div className="flex items-center gap-2">
          {added > 0 && (
            <span className="inline-flex items-center gap-0.5 px-2 py-0.5 bg-green-50 text-green-700 rounded text-xs font-medium border border-green-200">
              <Plus className="w-3 h-3" /> {added}
            </span>
          )}
          {modified > 0 && (
            <span className="inline-flex items-center gap-0.5 px-2 py-0.5 bg-yellow-50 text-yellow-700 rounded text-xs font-medium border border-yellow-200">
              <AlertTriangle className="w-3 h-3" /> {modified}
            </span>
          )}
          {removed > 0 && (
            <span className="inline-flex items-center gap-0.5 px-2 py-0.5 bg-red-50 text-red-700 rounded text-xs font-medium border border-red-200">
              <Minus className="w-3 h-3" /> {removed}
            </span>
          )}
        </div>
      </button>

      {isExpanded && (
        <div className="divide-y divide-gray-100">
          {section.entries.map((entry, index) => (
            <DiffEntryRow key={index} entry={entry} />
          ))}
        </div>
      )}
    </div>
  );
}

function DiffEntryRow({ entry }: { entry: DiffEntry }) {
  const [showDetail, setShowDetail] = useState(false);

  return (
    <div>
      <button
        onClick={() => entry.status !== 'unchanged' && setShowDetail(!showDetail)}
        className={clsx(
          'w-full flex items-center gap-3 px-4 py-2 text-left transition-colors',
          entry.status === 'unchanged' && 'cursor-default',
          entry.status !== 'unchanged' && 'hover:bg-gray-50'
        )}
      >
        {/* Status indicator */}
        <span
          className={clsx(
            'w-5 h-5 flex items-center justify-center rounded text-xs font-bold shrink-0',
            entry.status === 'added' && 'bg-green-100 text-green-700',
            entry.status === 'removed' && 'bg-red-100 text-red-700',
            entry.status === 'modified' && 'bg-yellow-100 text-yellow-700',
            entry.status === 'unchanged' && 'bg-gray-100 text-gray-400'
          )}
        >
          {entry.status === 'added' && '+'}
          {entry.status === 'removed' && '-'}
          {entry.status === 'modified' && '~'}
          {entry.status === 'unchanged' && '='}
        </span>

        <span
          className={clsx(
            'text-sm flex-1',
            entry.status === 'added' && 'text-green-700 font-medium',
            entry.status === 'removed' && 'text-red-700 line-through',
            entry.status === 'modified' && 'text-yellow-700 font-medium',
            entry.status === 'unchanged' && 'text-gray-500'
          )}
        >
          {entry.name}
        </span>

        {entry.status !== 'unchanged' && (entry.currentValue || entry.newValue) && (
          showDetail ? (
            <ChevronDown className="w-3.5 h-3.5 text-gray-400 shrink-0" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-gray-400 shrink-0" />
          )
        )}
      </button>

      {/* Side-by-side diff detail */}
      {showDetail && (entry.currentValue || entry.newValue) && (
        <div className="grid grid-cols-2 gap-0 mx-4 mb-3 rounded-lg overflow-hidden border border-gray-200">
          {/* Current (left) */}
          <div className="bg-red-50/30">
            <div className="px-3 py-1.5 bg-red-50 border-b border-gray-200">
              <span className="text-[10px] font-medium text-red-600 uppercase tracking-wider">Current Org</span>
            </div>
            <pre className="px-3 py-2 text-xs font-mono text-gray-700 whitespace-pre-wrap overflow-auto max-h-48">
              {entry.currentValue || '(empty)'}
            </pre>
          </div>
          {/* New (right) */}
          <div className="bg-green-50/30 border-l border-gray-200">
            <div className="px-3 py-1.5 bg-green-50 border-b border-gray-200">
              <span className="text-[10px] font-medium text-green-600 uppercase tracking-wider">New Bundle</span>
            </div>
            <pre className="px-3 py-2 text-xs font-mono text-gray-700 whitespace-pre-wrap overflow-auto max-h-48">
              {entry.newValue || '(empty)'}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

export function BundleDiff({ sections, summary, orgName }: BundleDiffProps) {
  const totalAdded = summary?.added ?? sections.reduce((sum, s) => sum + s.entries.filter(e => e.status === 'added').length, 0);
  const totalConflicts = summary?.conflicts ?? sections.reduce((sum, s) => sum + s.entries.filter(e => e.status === 'modified').length, 0);
  const totalRemovals = summary?.removals ?? sections.reduce((sum, s) => sum + s.entries.filter(e => e.status === 'removed').length, 0);

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="flex items-center justify-between bg-white border border-gray-200 rounded-lg shadow-sm px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">
            Bundle Diff {orgName ? `- ${orgName}` : ''}
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">Comparing current org data vs new bundle</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
            <span className="text-sm text-gray-700">
              <span className="font-semibold text-green-700">{totalAdded}</span> new
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-yellow-500" />
            <span className="text-sm text-gray-700">
              <span className="font-semibold text-yellow-700">{totalConflicts}</span> conflicts
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
            <span className="text-sm text-gray-700">
              <span className="font-semibold text-red-700">{totalRemovals}</span> removals
            </span>
          </div>
        </div>
      </div>

      {/* Sections */}
      {sections.map((section, index) => (
        <DiffSectionView key={index} section={section} />
      ))}

      {sections.length === 0 && (
        <div className="text-center py-12 text-gray-400 border border-gray-200 rounded-lg bg-white">
          <p className="text-sm">No diff data available. Run a comparison first.</p>
        </div>
      )}
    </div>
  );
}
