import { useCallback } from 'react';
import clsx from 'clsx';
import type {
  PermissionMatrixData,
  PermissionEntry,
  FormDefinitionData,
  UserPersonaData,
} from '../../types/index.ts';

interface PermissionsProps {
  data: PermissionMatrixData;
  forms: FormDefinitionData[];
  users: UserPersonaData[];
  onChange: (data: PermissionMatrixData) => void;
}

const PERMISSION_LABELS: { key: keyof PermissionEntry; label: string }[] = [
  { key: 'view', label: 'View' },
  { key: 'register', label: 'Register' },
  { key: 'edit', label: 'Edit' },
  { key: 'void', label: 'Void' },
];

function getPermission(
  matrix: PermissionMatrixData,
  formId: string,
  userId: string
): PermissionEntry {
  return matrix[formId]?.[userId] ?? { view: false, register: false, edit: false, void: false };
}

export function Permissions({ data, forms, users, onChange }: PermissionsProps) {
  const togglePermission = useCallback(
    (formId: string, userId: string, key: keyof PermissionEntry) => {
      const current = getPermission(data, formId, userId);
      const updated: PermissionMatrixData = {
        ...data,
        [formId]: {
          ...data[formId],
          [userId]: {
            ...current,
            [key]: !current[key],
          },
        },
      };
      onChange(updated);
    },
    [data, onChange]
  );

  const toggleAllForForm = useCallback(
    (formId: string, checked: boolean) => {
      const formPerms: PermissionMatrixData[string] = {};
      for (const user of users) {
        formPerms[user.id] = {
          view: checked,
          register: checked,
          edit: checked,
          void: checked,
        };
      }
      onChange({ ...data, [formId]: formPerms });
    },
    [data, users, onChange]
  );

  const activeUsers = users.filter(u => u.type);
  const activeForms = forms.filter(f => f.name);

  if (activeForms.length === 0 || activeUsers.length === 0) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Permissions</h3>
          <p className="text-sm text-gray-600">Define which user groups can perform which actions on each form.</p>
        </div>
        <div className="text-center py-12 text-gray-400 border border-gray-200 rounded-lg bg-white">
          <p className="text-sm">
            {activeForms.length === 0 && activeUsers.length === 0
              ? 'Define forms and users first to configure permissions.'
              : activeForms.length === 0
                ? 'Define forms in the Forms tab first.'
                : 'Define users in the User Personas tab first.'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-full mx-auto">
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-gray-900">Permissions</h3>
        <p className="text-sm text-gray-600">
          Define which user groups can perform which actions on each form. Check the boxes to grant permissions.
        </p>
      </div>

      <div className="border border-gray-200 rounded-lg overflow-x-auto bg-white shadow-sm">
        <table className="w-full text-sm min-w-[600px]">
          <thead className="sticky top-0 z-10">
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-4 py-2.5 font-medium text-gray-700 w-[200px] sticky left-0 bg-gray-50 z-10">
                Form
              </th>
              {activeUsers.map(user => (
                <th
                  key={user.id}
                  className="text-center px-2 py-2.5 font-medium text-gray-700"
                  colSpan={4}
                >
                  <span className="text-xs">{user.type}</span>
                </th>
              ))}
            </tr>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="sticky left-0 bg-gray-50 z-10 px-4">
                <span>&nbsp;</span>
              </th>
              {activeUsers.map(user => (
                PERMISSION_LABELS.map(perm => (
                  <th
                    key={`${user.id}-${perm.key}`}
                    className="text-center px-1 py-1.5 font-normal text-gray-500 text-[10px] uppercase tracking-wider"
                  >
                    {perm.label}
                  </th>
                ))
              ))}
            </tr>
          </thead>
          <tbody>
            {activeForms.map((form, fIndex) => {
              const allChecked = activeUsers.every(user => {
                const p = getPermission(data, form.id, user.id);
                return p.view && p.register && p.edit && p.void;
              });

              return (
                <tr
                  key={form.id}
                  className={clsx(
                    'hover:bg-gray-50 transition-colors',
                    fIndex % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'
                  )}
                >
                  <td className="px-4 py-2 sticky left-0 bg-inherit z-10">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={allChecked}
                        onChange={e => toggleAllForForm(form.id, e.target.checked)}
                        className="w-3.5 h-3.5 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                        title="Toggle all permissions for this form"
                      />
                      <span className="text-sm text-gray-900 font-medium">{form.name}</span>
                    </div>
                  </td>
                  {activeUsers.map(user =>
                    PERMISSION_LABELS.map(perm => {
                      const checked = getPermission(data, form.id, user.id)[perm.key];
                      return (
                        <td key={`${user.id}-${perm.key}`} className="text-center px-1 py-2">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => togglePermission(form.id, user.id, perm.key)}
                            className="w-3.5 h-3.5 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                          />
                        </td>
                      );
                    })
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
