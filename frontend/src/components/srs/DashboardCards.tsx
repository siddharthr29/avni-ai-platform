import { useCallback } from 'react';
import { Plus, Trash2, Pencil, Sparkles } from 'lucide-react';
import clsx from 'clsx';
import type { DashboardCardData, UserPersonaData } from '../../types/index.ts';

interface DashboardCardsProps {
  data: DashboardCardData[];
  users: UserPersonaData[];
  onChange: (data: DashboardCardData[]) => void;
}

export function DashboardCards({ data, users, onChange }: DashboardCardsProps) {
  const addRow = useCallback(() => {
    onChange([
      ...data,
      { id: crypto.randomUUID(), cardName: '', logic: '', userType: '' },
    ]);
  }, [data, onChange]);

  const removeRow = useCallback(
    (id: string) => {
      onChange(data.filter(c => c.id !== id));
    },
    [data, onChange]
  );

  const updateRow = useCallback(
    (id: string, updates: Partial<DashboardCardData>) => {
      onChange(data.map(c => (c.id === id ? { ...c, ...updates } : c)));
    },
    [data, onChange]
  );

  const userTypes = users.map(u => u.type).filter(Boolean);

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Offline Dashboard Cards</h3>
          <p className="text-sm text-gray-600">Define dashboard cards that users see on their mobile home screen.</p>
        </div>
        <button
          onClick={addRow}
          className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500"
        >
          <Plus className="w-4 h-4" />
          Add Card
        </button>
      </div>

      <div className="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-4 py-2.5 font-medium text-gray-700 w-[200px]">Card Name</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-700">Logic / Eligibility</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-700 w-[150px]">User Type</th>
              <th className="w-[80px]" />
            </tr>
          </thead>
          <tbody>
            {data.length === 0 ? (
              <tr>
                <td colSpan={4} className="text-center py-8 text-gray-400 text-sm">
                  No dashboard cards yet. Click "Add Card" to define cards.
                </td>
              </tr>
            ) : (
              data.map((card, index) => (
                <tr
                  key={card.id}
                  className={clsx(
                    'hover:bg-gray-50 transition-colors',
                    index % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'
                  )}
                >
                  <td className="px-4 py-1.5">
                    <input
                      type="text"
                      value={card.cardName}
                      onChange={e => updateRow(card.id, { cardName: e.target.value })}
                      placeholder="Card name..."
                      className="w-full bg-transparent border-0 px-0 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                    />
                  </td>
                  <td className="px-4 py-1.5">
                    <input
                      type="text"
                      value={card.logic}
                      onChange={e => updateRow(card.id, { logic: e.target.value })}
                      placeholder="Describe the logic or eligibility criteria..."
                      className="w-full bg-transparent border-0 px-0 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                    />
                  </td>
                  <td className="px-4 py-1.5">
                    <select
                      value={card.userType}
                      onChange={e => updateRow(card.id, { userType: e.target.value })}
                      className="w-full bg-transparent border-0 px-0 py-1.5 text-sm text-gray-900 focus:outline-none focus:ring-0"
                    >
                      <option value="">Select...</option>
                      {userTypes.map(type => (
                        <option key={type} value={type}>{type}</option>
                      ))}
                      {card.userType && !userTypes.includes(card.userType) && (
                        <option value={card.userType}>{card.userType}</option>
                      )}
                    </select>
                  </td>
                  <td className="px-2 py-1.5">
                    <div className="flex items-center gap-0.5">
                      <button
                        className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
                        aria-label="Edit card"
                      >
                        <Pencil className="w-3 h-3" />
                      </button>
                      <button
                        onClick={() => removeRow(card.id)}
                        className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
                        aria-label="Remove card"
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
