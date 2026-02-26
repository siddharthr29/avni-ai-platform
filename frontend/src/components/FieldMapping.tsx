import { useState } from 'react';
import { Check, AlertTriangle, X, Pencil, Save } from 'lucide-react';
import clsx from 'clsx';

interface FieldMappingProps {
  fields: Record<string, unknown>;
  confidence: Record<string, number>;
}

function ConfidenceBadge({ value }: { value: number }) {
  const percentage = Math.round(value * 100);
  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
        value >= 0.9 && 'bg-green-100 text-green-800',
        value >= 0.7 && value < 0.9 && 'bg-yellow-100 text-yellow-800',
        value < 0.7 && 'bg-red-100 text-red-800'
      )}
    >
      {percentage}%
    </span>
  );
}

function StatusIcon({ confidence }: { confidence: number }) {
  if (confidence >= 0.9) {
    return <Check className="w-4 h-4 text-green-600" />;
  }
  if (confidence >= 0.7) {
    return <AlertTriangle className="w-4 h-4 text-yellow-600" />;
  }
  return <X className="w-4 h-4 text-red-600" />;
}

export function FieldMapping({ fields, confidence }: FieldMappingProps) {
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editedValues, setEditedValues] = useState<Record<string, string>>({});

  const fieldNames = Object.keys(fields);

  const handleEdit = (fieldName: string) => {
    setEditingField(fieldName);
    if (!(fieldName in editedValues)) {
      setEditedValues(prev => ({
        ...prev,
        [fieldName]: String(fields[fieldName] ?? ''),
      }));
    }
  };

  const handleSave = (fieldName: string) => {
    setEditingField(null);
    // In a real app, this would update the backend
    void fieldName;
  };

  const handleValueChange = (fieldName: string, value: string) => {
    setEditedValues(prev => ({
      ...prev,
      [fieldName]: value,
    }));
  };

  const getValue = (fieldName: string): string => {
    if (fieldName in editedValues) {
      return editedValues[fieldName];
    }
    return String(fields[fieldName] ?? '');
  };

  if (fieldNames.length === 0) {
    return (
      <div className="text-sm text-gray-500 italic p-3">
        No fields were mapped from the voice input.
      </div>
    );
  }

  return (
    <div className="mt-2 rounded-lg border border-gray-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            <th className="text-left px-3 py-2 font-medium text-gray-600">Field</th>
            <th className="text-left px-3 py-2 font-medium text-gray-600">Value</th>
            <th className="text-center px-3 py-2 font-medium text-gray-600">Confidence</th>
            <th className="text-center px-3 py-2 font-medium text-gray-600 w-16">Status</th>
            <th className="w-10" />
          </tr>
        </thead>
        <tbody>
          {fieldNames.map((fieldName, index) => {
            const conf = confidence[fieldName] ?? 0;
            const isEditing = editingField === fieldName;

            return (
              <tr
                key={fieldName}
                className={clsx(
                  'border-b border-gray-100 last:border-b-0',
                  index % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'
                )}
              >
                <td className="px-3 py-2 font-medium text-gray-800">{fieldName}</td>
                <td className="px-3 py-2">
                  {isEditing ? (
                    <input
                      type="text"
                      value={getValue(fieldName)}
                      onChange={e => handleValueChange(fieldName, e.target.value)}
                      className="w-full px-2 py-1 border border-primary-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                      autoFocus
                      onKeyDown={e => {
                        if (e.key === 'Enter') handleSave(fieldName);
                        if (e.key === 'Escape') setEditingField(null);
                      }}
                    />
                  ) : (
                    <span className="text-gray-700">{getValue(fieldName)}</span>
                  )}
                </td>
                <td className="px-3 py-2 text-center">
                  <ConfidenceBadge value={conf} />
                </td>
                <td className="px-3 py-2 text-center">
                  <StatusIcon confidence={conf} />
                </td>
                <td className="px-2 py-2">
                  {isEditing ? (
                    <button
                      onClick={() => handleSave(fieldName)}
                      className="p-1 rounded hover:bg-gray-200 transition-colors"
                      aria-label="Save"
                    >
                      <Save className="w-3.5 h-3.5 text-primary-600" />
                    </button>
                  ) : (
                    <button
                      onClick={() => handleEdit(fieldName)}
                      className="p-1 rounded hover:bg-gray-200 transition-colors"
                      aria-label="Edit"
                    >
                      <Pencil className="w-3.5 h-3.5 text-gray-400" />
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="border-t border-gray-200 px-3 py-2 bg-gray-50 flex justify-end">
        <button className="px-4 py-1.5 bg-primary-600 hover:bg-primary-700 text-white text-sm rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 font-medium">
          Save to Avni
        </button>
      </div>
    </div>
  );
}
