import { useCallback } from 'react';
import { Plus, Trash2, Pencil, Sparkles } from 'lucide-react';
import clsx from 'clsx';
import type { UserPersonaData } from '../../types/index.ts';

interface UserPersonaProps {
  data: UserPersonaData[];
  onChange: (data: UserPersonaData[]) => void;
}

export function UserPersona({ data, onChange }: UserPersonaProps) {
  const addRow = useCallback(() => {
    onChange([
      ...data,
      { id: crypto.randomUUID(), type: '', description: '', count: 0 },
    ]);
  }, [data, onChange]);

  const removeRow = useCallback(
    (id: string) => {
      onChange(data.filter(u => u.id !== id));
    },
    [data, onChange]
  );

  const updateRow = useCallback(
    (id: string, updates: Partial<UserPersonaData>) => {
      onChange(data.map(u => (u.id === id ? { ...u, ...updates } : u)));
    },
    [data, onChange]
  );

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">User Personas</h3>
          <p className="text-sm text-gray-600">Define the types of users who will use Avni.</p>
        </div>
        <button
          onClick={addRow}
          className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500"
        >
          <Plus className="w-4 h-4" />
          Add User
        </button>
      </div>

      <div className="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-4 py-2.5 font-medium text-gray-700 w-[180px]">User Type</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-700">Description</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-700 w-[100px]">Count</th>
              <th className="w-[80px]" />
            </tr>
          </thead>
          <tbody>
            {data.length === 0 ? (
              <tr>
                <td colSpan={4} className="text-center py-8 text-gray-400 text-sm">
                  No users defined. Click "Add User" to add user types.
                </td>
              </tr>
            ) : (
              data.map((user, index) => (
                <tr
                  key={user.id}
                  className={clsx(
                    'hover:bg-gray-50 transition-colors',
                    index % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'
                  )}
                >
                  <td className="px-4 py-1.5">
                    <input
                      type="text"
                      value={user.type}
                      onChange={e => updateRow(user.id, { type: e.target.value })}
                      placeholder="e.g., ANM"
                      className="w-full bg-transparent border-0 px-0 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                    />
                  </td>
                  <td className="px-4 py-1.5">
                    <input
                      type="text"
                      value={user.description}
                      onChange={e => updateRow(user.id, { description: e.target.value })}
                      placeholder="Describe the user's role..."
                      className="w-full bg-transparent border-0 px-0 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                    />
                  </td>
                  <td className="px-4 py-1.5">
                    <input
                      type="number"
                      value={user.count || ''}
                      onChange={e => updateRow(user.id, { count: parseInt(e.target.value) || 0 })}
                      placeholder="0"
                      min="0"
                      className="w-full bg-transparent border-0 px-0 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <div className="flex items-center gap-0.5">
                      <button
                        className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
                        aria-label="Edit user"
                      >
                        <Pencil className="w-3 h-3" />
                      </button>
                      <button
                        onClick={() => removeRow(user.id)}
                        className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
                        aria-label="Remove user"
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
