import { useCallback } from 'react';
import { Plus, Trash2, Pencil, Sparkles } from 'lucide-react';
import clsx from 'clsx';
import type { W3HEntryData, UserPersonaData } from '../../types/index.ts';

interface W3HTabProps {
  data: W3HEntryData[];
  users: UserPersonaData[];
  onChange: (data: W3HEntryData[]) => void;
}

const HOW_OPTIONS: W3HEntryData['how'][] = ['Mobile', 'Web', 'Both'];

export function W3HTab({ data, users, onChange }: W3HTabProps) {
  const addRow = useCallback(() => {
    onChange([
      ...data,
      {
        id: crypto.randomUUID(),
        what: '',
        when: '',
        who: '',
        how: 'Mobile',
        formsToSchedule: '',
        notes: '',
      },
    ]);
  }, [data, onChange]);

  const removeRow = useCallback(
    (id: string) => {
      onChange(data.filter(e => e.id !== id));
    },
    [data, onChange]
  );

  const updateRow = useCallback(
    (id: string, updates: Partial<W3HEntryData>) => {
      onChange(data.map(e => (e.id === id ? { ...e, ...updates } : e)));
    },
    [data, onChange]
  );

  return (
    <div className="max-w-full mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">W3H - What, When, Who, How</h3>
          <p className="text-sm text-gray-600">Map activities to users, timing, and modality.</p>
        </div>
        <button
          onClick={addRow}
          className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500"
        >
          <Plus className="w-4 h-4" />
          Add Row
        </button>
      </div>

      <div className="border border-gray-200 rounded-lg overflow-x-auto bg-white shadow-sm">
        <table className="w-full text-sm min-w-[900px]">
          <thead className="sticky top-0 z-10">
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-3 py-2.5 font-medium text-gray-700">What (Activity)</th>
              <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[140px]">When</th>
              <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[130px]">Who</th>
              <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[100px]">How</th>
              <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[160px]">Forms to Schedule</th>
              <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[140px]">Notes</th>
              <th className="w-[80px]" />
            </tr>
          </thead>
          <tbody>
            {data.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-8 text-gray-400 text-sm">
                  No entries yet. Click "Add Row" to define activities.
                </td>
              </tr>
            ) : (
              data.map((entry, index) => (
                <tr
                  key={entry.id}
                  className={clsx(
                    'hover:bg-gray-50 transition-colors',
                    index % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'
                  )}
                >
                  <td className="px-3 py-1.5">
                    <input
                      type="text"
                      value={entry.what}
                      onChange={e => updateRow(entry.id, { what: e.target.value })}
                      placeholder="Activity description..."
                      className="w-full bg-transparent border-0 px-0 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                    />
                  </td>
                  <td className="px-3 py-1.5">
                    <input
                      type="text"
                      value={entry.when}
                      onChange={e => updateRow(entry.id, { when: e.target.value })}
                      placeholder="Timing..."
                      className="w-full bg-transparent border-0 px-0 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                    />
                  </td>
                  <td className="px-3 py-1.5">
                    <select
                      value={entry.who}
                      onChange={e => updateRow(entry.id, { who: e.target.value })}
                      className="w-full bg-transparent border-0 px-0 py-1.5 text-sm text-gray-900 focus:outline-none focus:ring-0"
                    >
                      <option value="">Select user...</option>
                      {users.map(u => (
                        <option key={u.id} value={u.type}>
                          {u.type}
                        </option>
                      ))}
                      {entry.who && !users.some(u => u.type === entry.who) && (
                        <option value={entry.who}>{entry.who}</option>
                      )}
                    </select>
                  </td>
                  <td className="px-3 py-1.5">
                    <select
                      value={entry.how}
                      onChange={e =>
                        updateRow(entry.id, { how: e.target.value as W3HEntryData['how'] })
                      }
                      className="w-full bg-transparent border-0 px-0 py-1.5 text-sm text-gray-900 focus:outline-none focus:ring-0"
                    >
                      {HOW_OPTIONS.map(opt => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-1.5">
                    <input
                      type="text"
                      value={entry.formsToSchedule}
                      onChange={e => updateRow(entry.id, { formsToSchedule: e.target.value })}
                      placeholder="Form name..."
                      className="w-full bg-transparent border-0 px-0 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                    />
                  </td>
                  <td className="px-3 py-1.5">
                    <input
                      type="text"
                      value={entry.notes}
                      onChange={e => updateRow(entry.id, { notes: e.target.value })}
                      placeholder="Notes..."
                      className="w-full bg-transparent border-0 px-0 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <div className="flex items-center gap-0.5">
                      <button
                        className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
                        aria-label="Edit row"
                      >
                        <Pencil className="w-3 h-3" />
                      </button>
                      <button
                        onClick={() => removeRow(entry.id)}
                        className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
                        aria-label="Remove row"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                      <button
                        className="p-1 rounded hover:bg-teal-50 text-gray-400 hover:text-teal-600 transition-colors"
                        aria-label="AI suggest"
                      >
                        <Sparkles className="w-3 h-3" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
