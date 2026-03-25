import { useCallback, useState } from 'react';
import { Plus, Trash2, ChevronDown, ChevronRight, X, Pencil, Sparkles } from 'lucide-react';
import type { ProgramDetailData } from '../../types/index.ts';

interface ProgramDetailProps {
  data: ProgramDetailData[];
  onChange: (data: ProgramDetailData[]) => void;
}

export function ProgramDetail({ data, onChange }: ProgramDetailProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set(data.map(p => p.id)));

  const toggleExpanded = useCallback((id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const addProgram = useCallback(() => {
    const newId = crypto.randomUUID();
    const newProgram: ProgramDetailData = {
      id: newId,
      name: '',
      objective: '',
      eligibility: '',
      entryPoint: '',
      exitCriteria: '',
      totalBeneficiaries: 0,
      successIndicators: '',
      forms: [],
      reportsNeeded: '',
    };
    onChange([...data, newProgram]);
    setExpandedIds(prev => new Set([...prev, newId]));
  }, [data, onChange]);

  const removeProgram = useCallback((id: string) => {
    onChange(data.filter(p => p.id !== id));
    setExpandedIds(prev => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, [data, onChange]);

  const updateProgram = useCallback(
    (id: string, updates: Partial<ProgramDetailData>) => {
      onChange(data.map(p => (p.id === id ? { ...p, ...updates } : p)));
    },
    [data, onChange]
  );

  const addFormTag = useCallback(
    (programId: string, formName: string) => {
      const program = data.find(p => p.id === programId);
      if (!program || !formName.trim()) return;
      if (program.forms.includes(formName.trim())) return;
      updateProgram(programId, { forms: [...program.forms, formName.trim()] });
    },
    [data, updateProgram]
  );

  const removeFormTag = useCallback(
    (programId: string, index: number) => {
      const program = data.find(p => p.id === programId);
      if (!program) return;
      updateProgram(programId, { forms: program.forms.filter((_, i) => i !== index) });
    },
    [data, updateProgram]
  );

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Programs</h3>
          <p className="text-sm text-gray-600">Define the programs that will be implemented in Avni.</p>
        </div>
        <button
          onClick={addProgram}
          className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500"
        >
          <Plus className="w-4 h-4" />
          Add Program
        </button>
      </div>

      {/* AI Suggestion */}
      <div className="bg-teal-50 border border-teal-200 rounded-lg p-3">
        <div className="flex items-start gap-2">
          <Sparkles className="w-4 h-4 text-teal-600 mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="text-sm text-teal-800">
              Similar orgs (CInI, Ashwini) also have programs for: <span className="font-medium">Child Growth Monitoring, Immunization</span>
            </p>
            <div className="flex gap-2 mt-2">
              <button className="px-2.5 py-1 text-xs font-medium text-teal-700 bg-teal-100 hover:bg-teal-200 rounded-md transition-colors">
                Add
              </button>
              <button className="px-2.5 py-1 text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors">
                Dismiss
              </button>
            </div>
          </div>
        </div>
      </div>

      {data.length === 0 ? (
        <div className="text-center py-12 text-gray-400 border border-gray-200 rounded-lg">
          <p className="text-sm">No programs yet. Click "Add Program" to get started.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {data.map((program, pIndex) => (
            <div
              key={program.id}
              className="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm"
            >
              {/* Header */}
              <div
                className="flex items-center gap-3 px-4 py-3 bg-gray-50 cursor-pointer hover:bg-gray-100 transition-colors"
                onClick={() => toggleExpanded(program.id)}
              >
                {expandedIds.has(program.id) ? (
                  <ChevronDown className="w-4 h-4 text-gray-500 shrink-0" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-gray-500 shrink-0" />
                )}
                <span className="text-xs font-medium text-gray-400 shrink-0">#{pIndex + 1}</span>
                <span className="text-sm font-medium text-gray-900 flex-1 truncate">
                  {program.name || 'Untitled Program'}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    onClick={e => { e.stopPropagation(); }}
                    className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600 transition-colors"
                    aria-label="Edit program"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={e => {
                      e.stopPropagation();
                      removeProgram(program.id);
                    }}
                    className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
                    aria-label="Remove program"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {/* Body */}
              {expandedIds.has(program.id) && (
                <div className="px-4 py-4 space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="md:col-span-2">
                      <label className="block text-sm font-medium text-gray-700 mb-1">Program Name</label>
                      <input
                        type="text"
                        value={program.name}
                        onChange={e => updateProgram(program.id, { name: e.target.value })}
                        placeholder="e.g., Antenatal Care"
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                      />
                    </div>

                    <div className="md:col-span-2">
                      <label className="block text-sm font-medium text-gray-700 mb-1">Objective</label>
                      <textarea
                        value={program.objective}
                        onChange={e => updateProgram(program.id, { objective: e.target.value })}
                        placeholder="What is the goal of this program?"
                        rows={2}
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500 resize-none"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Eligibility</label>
                      <input
                        type="text"
                        value={program.eligibility}
                        onChange={e => updateProgram(program.id, { eligibility: e.target.value })}
                        placeholder="Who is eligible to enroll?"
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Entry Point</label>
                      <input
                        type="text"
                        value={program.entryPoint}
                        onChange={e => updateProgram(program.id, { entryPoint: e.target.value })}
                        placeholder="How does a beneficiary enter the program?"
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Exit Criteria</label>
                      <input
                        type="text"
                        value={program.exitCriteria}
                        onChange={e => updateProgram(program.id, { exitCriteria: e.target.value })}
                        placeholder="When does a beneficiary exit the program?"
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Total Beneficiaries</label>
                      <input
                        type="number"
                        value={program.totalBeneficiaries || ''}
                        onChange={e =>
                          updateProgram(program.id, {
                            totalBeneficiaries: parseInt(e.target.value) || 0,
                          })
                        }
                        placeholder="0"
                        min="0"
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                      />
                    </div>

                    <div className="md:col-span-2">
                      <label className="block text-sm font-medium text-gray-700 mb-1">Success Indicators</label>
                      <textarea
                        value={program.successIndicators}
                        onChange={e =>
                          updateProgram(program.id, { successIndicators: e.target.value })
                        }
                        placeholder="What metrics indicate success?"
                        rows={2}
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500 resize-none"
                      />
                    </div>

                    <div className="md:col-span-2">
                      <label className="block text-sm font-medium text-gray-700 mb-1">Forms</label>
                      <div className="flex flex-wrap gap-1.5 mb-2">
                        {program.forms.map((form, fIndex) => (
                          <span
                            key={fIndex}
                            className="inline-flex items-center gap-1 px-2.5 py-1 bg-teal-50 text-teal-700 rounded-md text-xs font-medium"
                          >
                            {form}
                            <button
                              onClick={() => removeFormTag(program.id, fIndex)}
                              className="p-0.5 rounded hover:bg-teal-100 transition-colors"
                              aria-label={`Remove ${form}`}
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </span>
                        ))}
                      </div>
                      <FormTagInput onAdd={name => addFormTag(program.id, name)} />
                    </div>

                    <div className="md:col-span-2">
                      <label className="block text-sm font-medium text-gray-700 mb-1">Reports Needed</label>
                      <textarea
                        value={program.reportsNeeded}
                        onChange={e =>
                          updateProgram(program.id, { reportsNeeded: e.target.value })
                        }
                        placeholder="What reports are needed from this program?"
                        rows={2}
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500 resize-none"
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface FormTagInputProps {
  onAdd: (name: string) => void;
}

function FormTagInput({ onAdd }: FormTagInputProps) {
  const [value, setValue] = useState('');

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && value.trim()) {
      e.preventDefault();
      onAdd(value.trim());
      setValue('');
    }
  };

  return (
    <input
      type="text"
      value={value}
      onChange={e => setValue(e.target.value)}
      onKeyDown={handleKeyDown}
      placeholder="Type form name and press Enter to add..."
      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
    />
  );
}
