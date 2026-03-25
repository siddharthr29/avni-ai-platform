import { useCallback, useState } from 'react';
import { Plus, Trash2, ChevronDown, Pencil, Sparkles, HelpCircle } from 'lucide-react';
import clsx from 'clsx';
import type { FormDefinitionData, FormFieldData, FormFieldDataType } from '../../types/index.ts';
import { DATA_TYPE_DISPLAY_LABELS, DATA_TYPE_TOOLTIPS } from '../../types/index.ts';

interface FormsTabProps {
  data: FormDefinitionData[];
  onChange: (data: FormDefinitionData[]) => void;
}

const DATA_TYPES: FormFieldDataType[] = [
  'Text',
  'Numeric',
  'Date',
  'Coded',
  'Notes',
  'Time',
  'Image',
  'PhoneNumber',
  'Subject',
  'QuestionGroup',
];

const USER_SYSTEM_OPTIONS: FormFieldData['userOrSystem'][] = ['User Enter', 'System Generated'];
const SELECTION_OPTIONS: FormFieldData['selectionType'][] = ['Single', 'Multi'];

function createEmptyField(pageName: string): FormFieldData {
  return {
    id: crypto.randomUUID(),
    pageName,
    fieldName: '',
    dataType: 'Text',
    mandatory: false,
    userOrSystem: 'User Enter',
    options: '',
    selectionType: 'Single',
    unit: '',
    min: '',
    max: '',
    skipLogic: '',
  };
}

export function FormsTab({ data, onChange }: FormsTabProps) {
  const [selectedFormId, setSelectedFormId] = useState<string>(data[0]?.id ?? '');

  const selectedForm = data.find(f => f.id === selectedFormId);

  const addForm = useCallback(() => {
    const newId = crypto.randomUUID();
    const newForm: FormDefinitionData = {
      id: newId,
      name: '',
      fields: [createEmptyField('Page 1')],
    };
    onChange([...data, newForm]);
    setSelectedFormId(newId);
  }, [data, onChange]);

  const removeForm = useCallback(
    (formId: string) => {
      const newData = data.filter(f => f.id !== formId);
      onChange(newData);
      if (selectedFormId === formId) {
        setSelectedFormId(newData[0]?.id ?? '');
      }
    },
    [data, onChange, selectedFormId]
  );

  const updateFormName = useCallback(
    (formId: string, name: string) => {
      onChange(data.map(f => (f.id === formId ? { ...f, name } : f)));
    },
    [data, onChange]
  );

  const updateFields = useCallback(
    (formId: string, fields: FormFieldData[]) => {
      onChange(data.map(f => (f.id === formId ? { ...f, fields } : f)));
    },
    [data, onChange]
  );

  const addField = useCallback(
    (formId: string) => {
      const form = data.find(f => f.id === formId);
      if (!form) return;
      const lastPageName = form.fields.length > 0 ? form.fields[form.fields.length - 1].pageName : 'Page 1';
      updateFields(formId, [...form.fields, createEmptyField(lastPageName)]);
    },
    [data, updateFields]
  );

  const addPage = useCallback(
    (formId: string) => {
      const form = data.find(f => f.id === formId);
      if (!form) return;
      const pageNumbers = form.fields
        .map(f => {
          const match = f.pageName.match(/^Page (\d+)$/);
          return match ? parseInt(match[1]) : 0;
        })
        .filter(n => n > 0);
      const nextPage = pageNumbers.length > 0 ? Math.max(...pageNumbers) + 1 : 1;
      updateFields(formId, [...form.fields, createEmptyField(`Page ${nextPage}`)]);
    },
    [data, updateFields]
  );

  const removeField = useCallback(
    (formId: string, fieldId: string) => {
      const form = data.find(f => f.id === formId);
      if (!form) return;
      updateFields(
        formId,
        form.fields.filter(f => f.id !== fieldId)
      );
    },
    [data, updateFields]
  );

  const updateField = useCallback(
    (formId: string, fieldId: string, updates: Partial<FormFieldData>) => {
      const form = data.find(f => f.id === formId);
      if (!form) return;
      updateFields(
        formId,
        form.fields.map(f => (f.id === fieldId ? { ...f, ...updates } : f))
      );
    },
    [data, updateFields]
  );

  return (
    <div className="max-w-full mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Forms</h3>
          <p className="text-sm text-gray-500">Define form fields with data types, validations, and skip logic.</p>
        </div>
        <button
          onClick={addForm}
          className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500"
        >
          <Plus className="w-4 h-4" />
          Add Form
        </button>
      </div>

      {/* Form selector */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        {data.map(form => (
          <div key={form.id} className="flex items-center">
            <button
              onClick={() => setSelectedFormId(form.id)}
              className={clsx(
                'px-3 py-1.5 text-sm rounded-lg border transition-colors',
                selectedFormId === form.id
                  ? 'bg-teal-50 border-teal-300 text-teal-700 font-medium'
                  : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'
              )}
            >
              {form.name || 'Untitled Form'}
            </button>
            <button
              onClick={() => removeForm(form.id)}
              className="ml-1 p-0.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
              aria-label={`Remove ${form.name || 'form'}`}
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        ))}
      </div>

      {selectedForm ? (
        <div>
          {/* Form name input */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">Form Name</label>
            <input
              type="text"
              value={selectedForm.name}
              onChange={e => updateFormName(selectedForm.id, e.target.value)}
              placeholder="e.g., ANC Registration"
              className="w-full max-w-sm rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
            />
          </div>

          {/* AI Suggestion card */}
          <div className="mb-4 bg-teal-50 border border-teal-200 rounded-lg p-3">
            <div className="flex items-start gap-2">
              <Sparkles className="w-4 h-4 text-teal-600 mt-0.5 shrink-0" />
              <div className="flex-1">
                <p className="text-sm text-teal-800">
                  Similar orgs (CInI, Ashwini) also have fields for: <span className="font-medium">BMI, Blood Pressure, Hemoglobin</span>
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

          {/* Fields table */}
          <div className="border border-gray-200 rounded-lg overflow-x-auto">
            <table className="w-full text-sm min-w-[1200px]">
              <thead className="sticky top-0 z-10">
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[120px]">Page</th>
                  <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[160px]">Field Name</th>
                  <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[140px]">
                    <span className="flex items-center gap-1">
                      Field Type
                      <span className="relative group/hdr">
                        <HelpCircle className="w-3 h-3 text-gray-400 cursor-help" />
                        <span className="hidden group-hover/hdr:block absolute left-0 top-full mt-1 w-48 p-2 bg-gray-800 text-white text-xs rounded-lg shadow-lg z-20 font-normal pointer-events-none">
                          The kind of answer this field expects (e.g. Multiple Choice, Number, Free Text).
                        </span>
                      </span>
                    </span>
                  </th>
                  <th className="text-center px-3 py-2.5 font-medium text-gray-700 w-[60px]">Req</th>
                  <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[120px]">User/System</th>
                  <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[180px]">Options</th>
                  <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[80px]">Select</th>
                  <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[70px]">Unit</th>
                  <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[55px]">Min</th>
                  <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[55px]">Max</th>
                  <th className="text-left px-3 py-2.5 font-medium text-gray-700 w-[150px]">Skip Logic</th>
                  <th className="w-[80px]" />
                </tr>
              </thead>
              <tbody>
                {selectedForm.fields.length === 0 ? (
                  <tr>
                    <td colSpan={12} className="text-center py-8 text-gray-400 text-sm">
                      No fields yet. Click "Add Row" or "Add Page" below.
                    </td>
                  </tr>
                ) : (
                  selectedForm.fields.map((field, index) => {
                    const isCoded = field.dataType === 'Coded';
                    const isNumeric = field.dataType === 'Numeric';
                    const showPageName =
                      index === 0 ||
                      selectedForm.fields[index - 1].pageName !== field.pageName;

                    return (
                      <tr
                        key={field.id}
                        className={clsx(
                          'hover:bg-gray-50 transition-colors',
                          index % 2 === 0 ? 'bg-white' : 'bg-gray-50/50',
                          showPageName && index > 0 && 'border-t-2 border-gray-200'
                        )}
                      >
                        <td className="px-3 py-1.5">
                          {showPageName ? (
                            <input
                              type="text"
                              value={field.pageName}
                              onChange={e =>
                                updateField(selectedForm.id, field.id, {
                                  pageName: e.target.value,
                                })
                              }
                              className="w-full bg-transparent border-0 px-0 py-1 text-sm font-medium text-teal-700 placeholder-gray-400 focus:outline-none focus:ring-0"
                              placeholder="Page name"
                            />
                          ) : (
                            <input
                              type="text"
                              value={field.pageName}
                              onChange={e =>
                                updateField(selectedForm.id, field.id, {
                                  pageName: e.target.value,
                                })
                              }
                              className="w-full bg-transparent border-0 px-0 py-1 text-sm text-gray-400 placeholder-gray-300 focus:outline-none focus:ring-0"
                              placeholder="Same page"
                            />
                          )}
                        </td>
                        <td className="px-3 py-1.5">
                          <input
                            type="text"
                            value={field.fieldName}
                            onChange={e =>
                              updateField(selectedForm.id, field.id, {
                                fieldName: e.target.value,
                              })
                            }
                            placeholder="Field name (required)"
                            className="w-full bg-transparent border-0 px-0 py-1 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          <div className="relative group/dt">
                            <select
                              value={field.dataType}
                              onChange={e =>
                                updateField(selectedForm.id, field.id, {
                                  dataType: e.target.value as FormFieldDataType,
                                })
                              }
                              className="w-full bg-transparent border-0 px-0 py-1 text-sm text-gray-900 focus:outline-none focus:ring-0 appearance-none pr-8"
                            >
                              {DATA_TYPES.map(dt => (
                                <option key={dt} value={dt}>
                                  {DATA_TYPE_DISPLAY_LABELS[dt] || dt}
                                </option>
                              ))}
                            </select>
                            <ChevronDown className="w-3 h-3 text-gray-400 absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none" />
                            {DATA_TYPE_TOOLTIPS[field.dataType] && (
                              <div className="absolute right-0 top-1/2 -translate-y-1/2">
                                <HelpCircle className="w-3.5 h-3.5 text-gray-300 hover:text-gray-500 cursor-help" />
                                <div className="hidden group-hover/dt:block absolute right-0 bottom-full mb-1 w-56 p-2 bg-gray-800 text-white text-xs rounded-lg shadow-lg z-20 pointer-events-none">
                                  {DATA_TYPE_TOOLTIPS[field.dataType]}
                                  <div className="absolute bottom-0 right-2 translate-y-1/2 rotate-45 w-2 h-2 bg-gray-800" />
                                </div>
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-1.5 text-center">
                          <input
                            type="checkbox"
                            checked={field.mandatory}
                            onChange={e =>
                              updateField(selectedForm.id, field.id, {
                                mandatory: e.target.checked,
                              })
                            }
                            className="w-4 h-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          <select
                            value={field.userOrSystem}
                            onChange={e =>
                              updateField(selectedForm.id, field.id, {
                                userOrSystem: e.target.value as FormFieldData['userOrSystem'],
                              })
                            }
                            className="w-full bg-transparent border-0 px-0 py-1 text-sm text-gray-900 focus:outline-none focus:ring-0"
                          >
                            {USER_SYSTEM_OPTIONS.map(opt => (
                              <option key={opt} value={opt}>
                                {opt}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="px-3 py-1.5">
                          {isCoded ? (
                            <input
                              type="text"
                              value={field.options}
                              onChange={e =>
                                updateField(selectedForm.id, field.id, {
                                  options: e.target.value,
                                })
                              }
                              placeholder="Comma-separated options"
                              className="w-full bg-transparent border-0 px-0 py-1 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                            />
                          ) : (
                            <span className="text-gray-300 text-xs">--</span>
                          )}
                        </td>
                        <td className="px-3 py-1.5">
                          {isCoded ? (
                            <select
                              value={field.selectionType}
                              onChange={e =>
                                updateField(selectedForm.id, field.id, {
                                  selectionType: e.target.value as FormFieldData['selectionType'],
                                })
                              }
                              className="w-full bg-transparent border-0 px-0 py-1 text-sm text-gray-900 focus:outline-none focus:ring-0"
                            >
                              {SELECTION_OPTIONS.map(opt => (
                                <option key={opt} value={opt}>
                                  {opt}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <span className="text-gray-300 text-xs">--</span>
                          )}
                        </td>
                        <td className="px-3 py-1.5">
                          {isNumeric ? (
                            <input
                              type="text"
                              value={field.unit}
                              onChange={e =>
                                updateField(selectedForm.id, field.id, {
                                  unit: e.target.value,
                                })
                              }
                              placeholder="Unit"
                              className="w-full bg-transparent border-0 px-0 py-1 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                            />
                          ) : (
                            <span className="text-gray-300 text-xs">--</span>
                          )}
                        </td>
                        <td className="px-3 py-1.5">
                          {isNumeric ? (
                            <input
                              type="text"
                              value={field.min}
                              onChange={e =>
                                updateField(selectedForm.id, field.id, { min: e.target.value })
                              }
                              placeholder="Min"
                              className="w-full bg-transparent border-0 px-0 py-1 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                            />
                          ) : (
                            <span className="text-gray-300 text-xs">--</span>
                          )}
                        </td>
                        <td className="px-3 py-1.5">
                          {isNumeric ? (
                            <input
                              type="text"
                              value={field.max}
                              onChange={e =>
                                updateField(selectedForm.id, field.id, { max: e.target.value })
                              }
                              placeholder="Max"
                              className="w-full bg-transparent border-0 px-0 py-1 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                            />
                          ) : (
                            <span className="text-gray-300 text-xs">--</span>
                          )}
                        </td>
                        <td className="px-3 py-1.5">
                          <input
                            type="text"
                            value={field.skipLogic}
                            onChange={e =>
                              updateField(selectedForm.id, field.id, {
                                skipLogic: e.target.value,
                              })
                            }
                            placeholder="Condition..."
                            className="w-full bg-transparent border-0 px-0 py-1 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0"
                          />
                        </td>
                        <td className="px-2 py-1.5">
                          <div className="flex items-center gap-0.5">
                            <button
                              className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
                              aria-label="Edit field"
                            >
                              <Pencil className="w-3 h-3" />
                            </button>
                            <button
                              onClick={() => removeField(selectedForm.id, field.id)}
                              className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
                              aria-label="Remove field"
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
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Action buttons below table */}
          <div className="flex gap-2 mt-3">
            <button
              onClick={() => addField(selectedForm.id)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 rounded-lg transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Row
            </button>
            <button
              onClick={() => addPage(selectedForm.id)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 rounded-lg transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Page
            </button>
          </div>
        </div>
      ) : (
        <div className="text-center py-12 text-gray-400">
          <p className="text-sm">No forms defined yet. Click "Add Form" to create a form.</p>
        </div>
      )}
    </div>
  );
}
