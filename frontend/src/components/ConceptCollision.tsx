import { useState } from 'react';
import { AlertTriangle, Check } from 'lucide-react';
import clsx from 'clsx';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ConceptCollisionOccurrence {
  form: string;
  dataType: string;
  options?: string[];
  context: string;
}

export interface ConceptCollision {
  name: string;
  occurrences: ConceptCollisionOccurrence[];
}

export interface ConceptCollisionProps {
  collisions: ConceptCollision[];
  onResolve: (resolutions: Record<string, string>) => void;
}

// ---------------------------------------------------------------------------
// Resolution helpers
// ---------------------------------------------------------------------------

type ResolutionKind = 'rename' | 'unify' | 'keep';

interface Resolution {
  kind: ResolutionKind;
  /** For "rename": which occurrence index to rename.
   *  For "unify": which data-type to keep.
   *  For "keep": unused. */
  value: string;
}

function resolutionLabel(collision: ConceptCollision, res: Resolution): string {
  if (res.kind === 'rename') {
    const idx = Number(res.value);
    const occ = collision.occurrences[idx];
    return `${collision.name} - ${occ.form}`;
  }
  if (res.kind === 'unify') {
    return `Use data type: ${res.value}`;
  }
  return 'Keep both as separate concepts';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ConceptCollisionPanel({ collisions, onResolve }: ConceptCollisionProps) {
  const [selections, setSelections] = useState<Record<string, Resolution>>({});

  const allResolved = collisions.length > 0 && collisions.every(c => selections[c.name] !== undefined);

  function select(conceptName: string, res: Resolution) {
    setSelections(prev => ({ ...prev, [conceptName]: res }));
  }

  function handleResolveAll() {
    const result: Record<string, string> = {};
    for (const collision of collisions) {
      const sel = selections[collision.name];
      if (sel) {
        result[collision.name] = resolutionLabel(collision, sel);
      }
    }
    onResolve(result);
  }

  if (collisions.length === 0) return null;

  return (
    <div className="rounded-lg border-2 border-amber-300 bg-amber-50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 bg-amber-100 border-b border-amber-300">
        <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
        <h3 className="text-sm font-semibold text-amber-900">
          Concept Name Collisions ({collisions.length})
        </h3>
      </div>

      <p className="px-4 pt-3 pb-1 text-xs text-amber-800">
        The following concept names are used with different data types across forms.
        Please choose how to resolve each collision before generating the bundle.
      </p>

      {/* Collision list */}
      <div className="divide-y divide-amber-200">
        {collisions.map(collision => {
          const current = selections[collision.name];
          const uniqueTypes = [...new Set(collision.occurrences.map(o => o.dataType))];

          return (
            <div key={collision.name} className="px-4 py-3">
              {/* Concept name */}
              <div className="flex items-center gap-2 mb-2">
                <span className="font-semibold text-sm text-gray-900">{collision.name}</span>
                {current && (
                  <span className="inline-flex items-center gap-1 text-xs text-green-700 bg-green-100 px-2 py-0.5 rounded-full">
                    <Check className="w-3 h-3" />
                    Resolved
                  </span>
                )}
              </div>

              {/* Where it's used */}
              <div className="mb-3 space-y-1">
                {collision.occurrences.map((occ, i) => (
                  <div
                    key={`${collision.name}-occ-${i}`}
                    className="flex items-start gap-2 text-xs text-gray-700"
                  >
                    <span className="shrink-0 mt-0.5 w-1.5 h-1.5 rounded-full bg-amber-400" />
                    <span>
                      <span className="font-medium text-gray-900">{occ.form}</span>
                      {' '}
                      <span className="text-gray-500">({occ.dataType}{occ.options ? `: ${occ.options.join(', ')}` : ''})</span>
                      {occ.context && (
                        <span className="text-gray-500 italic"> &mdash; {occ.context}</span>
                      )}
                    </span>
                  </div>
                ))}
              </div>

              {/* Resolution options */}
              <fieldset className="space-y-1.5">
                <legend className="sr-only">Resolution for {collision.name}</legend>

                {/* Option: Rename per occurrence */}
                {collision.occurrences.map((occ, idx) => {
                  const res: Resolution = { kind: 'rename', value: String(idx) };
                  const isSelected = current?.kind === 'rename' && current.value === String(idx);
                  return (
                    <label
                      key={`rename-${collision.name}-${idx}`}
                      className={clsx(
                        'flex items-center gap-2 px-3 py-1.5 rounded-md border text-xs cursor-pointer transition-colors',
                        isSelected
                          ? 'border-amber-500 bg-amber-100 text-amber-900'
                          : 'border-transparent hover:bg-amber-100/50 text-gray-700'
                      )}
                    >
                      <input
                        type="radio"
                        name={`resolution-${collision.name}`}
                        checked={isSelected}
                        onChange={() => select(collision.name, res)}
                        className="accent-amber-600"
                      />
                      Rename to &ldquo;{collision.name} - {occ.form}&rdquo;
                    </label>
                  );
                })}

                {/* Option: Unify data type */}
                {uniqueTypes.map(dt => {
                  const res: Resolution = { kind: 'unify', value: dt };
                  const isSelected = current?.kind === 'unify' && current.value === dt;
                  return (
                    <label
                      key={`unify-${collision.name}-${dt}`}
                      className={clsx(
                        'flex items-center gap-2 px-3 py-1.5 rounded-md border text-xs cursor-pointer transition-colors',
                        isSelected
                          ? 'border-amber-500 bg-amber-100 text-amber-900'
                          : 'border-transparent hover:bg-amber-100/50 text-gray-700'
                      )}
                    >
                      <input
                        type="radio"
                        name={`resolution-${collision.name}`}
                        checked={isSelected}
                        onChange={() => select(collision.name, res)}
                        className="accent-amber-600"
                      />
                      Use data type: <span className="font-medium">{dt}</span> for all occurrences
                    </label>
                  );
                })}

                {/* Option: Keep both */}
                {(() => {
                  const res: Resolution = { kind: 'keep', value: '' };
                  const isSelected = current?.kind === 'keep';
                  return (
                    <label
                      className={clsx(
                        'flex items-center gap-2 px-3 py-1.5 rounded-md border text-xs cursor-pointer transition-colors',
                        isSelected
                          ? 'border-amber-500 bg-amber-100 text-amber-900'
                          : 'border-transparent hover:bg-amber-100/50 text-gray-700'
                      )}
                    >
                      <input
                        type="radio"
                        name={`resolution-${collision.name}`}
                        checked={isSelected}
                        onChange={() => select(collision.name, res)}
                        className="accent-amber-600"
                      />
                      Keep both as separate concepts (rename one automatically)
                    </label>
                  );
                })()}
              </fieldset>
            </div>
          );
        })}
      </div>

      {/* Resolve all button */}
      <div className="px-4 py-3 bg-amber-100 border-t border-amber-300 flex justify-end">
        <button
          onClick={handleResolveAll}
          disabled={!allResolved}
          className={clsx(
            'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-2',
            allResolved
              ? 'bg-amber-600 hover:bg-amber-700 text-white'
              : 'bg-gray-200 text-gray-400 cursor-not-allowed'
          )}
        >
          <Check className="w-4 h-4" />
          Resolve All
        </button>
      </div>
    </div>
  );
}
