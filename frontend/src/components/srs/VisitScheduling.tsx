import { useCallback } from 'react';
import { Plus, Trash2, Pencil, Sparkles } from 'lucide-react';
import clsx from 'clsx';
import type { VisitScheduleData, FormDefinitionData, UserPersonaData } from '../../types/index.ts';

interface VisitSchedulingProps {
  data: VisitScheduleData[];
  forms: FormDefinitionData[];
  users: UserPersonaData[];
  onChange: (data: VisitScheduleData[]) => void;
}

const FREQUENCY_OPTIONS: VisitScheduleData['frequency'][] = [
  'Daily',
  'Weekly',
  'Monthly',
  'Quarterly',
  'Yearly',
  'One-time',
];

export function VisitScheduling({ data, forms, users, onChange }: VisitSchedulingProps) {
  const addRow = useCallback(() => {
    onChange([
      ...data,
      {
        id: crypto.randomUUID(),
        onCompletionOf: '',
        scheduleForm: '',
        frequency: 'One-time',
        scheduleFor: '',
        conditionToSchedule: '',
        conditionNotToSchedule: '',
        scheduleDate: '',
        overdueDate: '',
        onCancellation: '',
        weekendHoliday: '',
        onEdit: '',
      },
    ]);
  }, [data, onChange]);

  const removeRow = useCallback(
    (id: string) => {
      onChange(data.filter(v => v.id !== id));
    },
    [data, onChange]
  );

  const updateRow = useCallback(
    (id: string, updates: Partial<VisitScheduleData>) => {
      onChange(data.map(v => (v.id === id ? { ...v, ...updates } : v)));
    },
    [data, onChange]
  );

  const formNames = forms.map(f => f.name).filter(Boolean);
  const userTypes = users.map(u => u.type).filter(Boolean);

  return (
    <div className="max-w-full mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Visit Scheduling</h3>
          <p className="text-sm text-gray-600">Define how visits are automatically scheduled based on form completions.</p>
        </div>
        <button
          onClick={addRow}
          className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500"
        >
          <Plus className="w-4 h-4" />
          Add Rule
        </button>
      </div>

      {data.length === 0 ? (
        <div className="text-center py-12 text-gray-400 border border-gray-200 rounded-lg bg-white">
          <p className="text-sm">No scheduling rules yet. Click "Add Rule" to define visit scheduling.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {data.map((rule, ruleIndex) => (
            <div key={rule.id} className="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm">
              <div className="flex items-center justify-between px-4 py-2.5 bg-gray-50 border-b border-gray-200">
                <span className="text-sm font-medium text-gray-700">Rule #{ruleIndex + 1}</span>
                <div className="flex items-center gap-1">
                  <button
                    className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600 transition-colors"
                    aria-label="Edit rule"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => removeRow(rule.id)}
                    className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
                    aria-label="Remove rule"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                  <button
                    className="p-1 rounded hover:bg-teal-50 text-gray-400 hover:text-teal-600 transition-colors"
                    aria-label="AI suggest"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-4">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">On Completion Of</label>
                  <select
                    value={rule.onCompletionOf}
                    onChange={e => updateRow(rule.id, { onCompletionOf: e.target.value })}
                    className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  >
                    <option value="">Select form...</option>
                    {formNames.map(name => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                    {rule.onCompletionOf && !formNames.includes(rule.onCompletionOf) && (
                      <option value={rule.onCompletionOf}>{rule.onCompletionOf}</option>
                    )}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Schedule Form</label>
                  <select
                    value={rule.scheduleForm}
                    onChange={e => updateRow(rule.id, { scheduleForm: e.target.value })}
                    className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  >
                    <option value="">Select form...</option>
                    {formNames.map(name => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                    {rule.scheduleForm && !formNames.includes(rule.scheduleForm) && (
                      <option value={rule.scheduleForm}>{rule.scheduleForm}</option>
                    )}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Frequency</label>
                  <select
                    value={rule.frequency}
                    onChange={e =>
                      updateRow(rule.id, {
                        frequency: e.target.value as VisitScheduleData['frequency'],
                      })
                    }
                    className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  >
                    {FREQUENCY_OPTIONS.map(opt => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Schedule For</label>
                  <select
                    value={rule.scheduleFor}
                    onChange={e => updateRow(rule.id, { scheduleFor: e.target.value })}
                    className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  >
                    <option value="">Select user type...</option>
                    {userTypes.map(type => (
                      <option key={type} value={type}>{type}</option>
                    ))}
                    {rule.scheduleFor && !userTypes.includes(rule.scheduleFor) && (
                      <option value={rule.scheduleFor}>{rule.scheduleFor}</option>
                    )}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Condition to Schedule</label>
                  <input
                    type="text"
                    value={rule.conditionToSchedule}
                    onChange={e => updateRow(rule.id, { conditionToSchedule: e.target.value })}
                    placeholder="When to schedule..."
                    className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Condition NOT to Schedule</label>
                  <input
                    type="text"
                    value={rule.conditionNotToSchedule}
                    onChange={e => updateRow(rule.id, { conditionNotToSchedule: e.target.value })}
                    placeholder="When not to schedule..."
                    className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Schedule Date</label>
                  <input
                    type="text"
                    value={rule.scheduleDate}
                    onChange={e => updateRow(rule.id, { scheduleDate: e.target.value })}
                    placeholder="e.g., 4 weeks from last visit"
                    className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Overdue Date</label>
                  <input
                    type="text"
                    value={rule.overdueDate}
                    onChange={e => updateRow(rule.id, { overdueDate: e.target.value })}
                    placeholder="e.g., 7 days after scheduled"
                    className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">On Cancellation</label>
                  <input
                    type="text"
                    value={rule.onCancellation}
                    onChange={e => updateRow(rule.id, { onCancellation: e.target.value })}
                    placeholder="Action on cancellation..."
                    className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Weekend/Holiday</label>
                  <input
                    type="text"
                    value={rule.weekendHoliday}
                    onChange={e => updateRow(rule.id, { weekendHoliday: e.target.value })}
                    placeholder="Handling for weekends..."
                    className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">On Edit</label>
                  <input
                    type="text"
                    value={rule.onEdit}
                    onChange={e => updateRow(rule.id, { onEdit: e.target.value })}
                    placeholder="Action on edit..."
                    className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
