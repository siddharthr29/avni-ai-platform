import { useState, useEffect, useCallback, useMemo } from 'react';
import { authFetch } from '../../services/api';
import {
  X,
  ChevronDown,
  ChevronRight,
  Pencil,
  Check,
  Plus,
  Trash2,
  Loader2,
  Download,
  Package,
  Building2,
  Users,
  ClipboardList,
  FileText,
  CalendarClock,
  LayoutDashboard,
  Shield,
} from 'lucide-react';
import clsx from 'clsx';
import type {
  SRSData,
  ProgramSummaryData,
  ProgramDetailData,
  UserPersonaData,
  FormDefinitionData,
  FormFieldData,
  FormFieldDataType,
  VisitScheduleData,
  DashboardCardData,
} from '../../types/index.ts';

// ── Types ────────────────────────────────────────────────────────────────────

export interface SRSPreviewPanelProps {
  srsData: SRSData;
  phase: string;
  onSrsChange: (updated: SRSData) => void;
  onGenerateBundle: () => void;
  bundleStatus: 'idle' | 'generating' | 'done' | 'error';
  bundleId: string | null;
  onClose: () => void;
  onItemAdded?: () => void;
}

type Phase =
  | 'start'
  | 'organization'
  | 'subjects'
  | 'programs'
  | 'encounters'
  | 'forms'
  | 'scheduling'
  | 'dashboard'
  | 'review';

const PHASE_ORDER: Phase[] = [
  'start',
  'organization',
  'subjects',
  'programs',
  'encounters',
  'forms',
  'scheduling',
  'dashboard',
  'review',
];

const PHASE_LABELS: Record<Phase, string> = {
  start: 'Start',
  organization: 'Organization',
  subjects: 'Subjects',
  programs: 'Programs',
  encounters: 'Encounters',
  forms: 'Forms',
  scheduling: 'Scheduling',
  dashboard: 'Dashboard',
  review: 'Review',
};

type PreviewSection =
  | 'organization'
  | 'subjects'
  | 'programs'
  | 'forms'
  | 'scheduling'
  | 'dashboard'
  | 'permissions';

// ── Exported utilities (used by useChat) ──────────────────────────────────────

export function mergeSrsUpdate(current: SRSData, update: Partial<Record<string, unknown>>): SRSData {
  const merged = { ...current } as Record<string, unknown>;

  for (const key of Object.keys(update)) {
    const updateVal = update[key];
    if (updateVal === null || updateVal === undefined) continue;

    if (key === 'forms' && Array.isArray(updateVal)) {
      const existing = [...(current.forms || [])] as any[];
      for (const newForm of updateVal as any[]) {
        const idx = existing.findIndex((f: any) =>
          f.name?.toLowerCase() === newForm.name?.toLowerCase()
        );
        if (idx >= 0) {
          existing[idx] = { ...existing[idx], ...newForm };
        } else {
          existing.push({ ...newForm, id: newForm.id || crypto.randomUUID() });
        }
      }
      merged.forms = existing;
    } else if (key === 'programs' && Array.isArray(updateVal)) {
      const existing = [...(current.programs || [])] as any[];
      for (const newProg of updateVal as any[]) {
        const name = typeof newProg === 'string' ? newProg : newProg?.name;
        const idx = existing.findIndex((p: any) => {
          const pName = typeof p === 'string' ? p : p?.name;
          return pName?.toLowerCase() === name?.toLowerCase();
        });
        if (idx >= 0) {
          existing[idx] = typeof newProg === 'string' ? existing[idx] : { ...existing[idx], ...newProg };
        } else {
          const entry = typeof newProg === 'string'
            ? { id: crypto.randomUUID(), name: newProg }
            : { ...newProg, id: newProg.id || crypto.randomUUID() };
          existing.push(entry);
        }
      }
      merged.programs = existing;
    } else if (key === 'encounterTypes' || key === 'generalEncounterTypes' || key === 'groups') {
      const currentArr = ((current as any)[key] || []) as any[];
      const existingSet = new Set(currentArr.map((s: any) => (typeof s === 'string' ? s : s?.name || '').toLowerCase()));
      const combined = [...currentArr];
      for (const item of updateVal as any[]) {
        const itemName = typeof item === 'string' ? item : item?.name || '';
        if (!existingSet.has(itemName.toLowerCase())) {
          combined.push(item);
          existingSet.add(itemName.toLowerCase());
        }
      }
      merged[key] = combined;
    } else if (key === 'subjectTypes' && Array.isArray(updateVal)) {
      const existing = [...((current as any).subjectTypes || [])] as any[];
      for (const newSt of updateVal as any[]) {
        const idx = existing.findIndex((st: any) => st.name?.toLowerCase() === newSt.name?.toLowerCase());
        if (idx >= 0) existing[idx] = { ...existing[idx], ...newSt };
        else existing.push(newSt);
      }
      merged.subjectTypes = existing;
    } else if (key === 'addressLevelTypes' && Array.isArray(updateVal)) {
      merged.addressLevelTypes = updateVal;
    } else if (key === 'visitSchedules' && Array.isArray(updateVal)) {
      const existing = [...((current as any).visitSchedules || [])] as any[];
      for (const newVs of updateVal as any[]) {
        const idx = existing.findIndex((vs: any) =>
          vs.schedule_encounter?.toLowerCase() === newVs.schedule_encounter?.toLowerCase()
        );
        if (idx >= 0) existing[idx] = { ...existing[idx], ...newVs };
        else existing.push({ ...newVs, id: newVs.id || crypto.randomUUID() });
      }
      merged.visitSchedules = existing;
    } else if (key === 'visitScheduling' && Array.isArray(updateVal)) {
      const existing = [...(current.visitScheduling || [])] as any[];
      for (const newVs of updateVal as any[]) {
        const idx = existing.findIndex((vs: any) =>
          vs.scheduleForm?.toLowerCase() === newVs.scheduleForm?.toLowerCase()
        );
        if (idx >= 0) existing[idx] = { ...existing[idx], ...newVs };
        else existing.push({ ...newVs, id: newVs.id || crypto.randomUUID() });
      }
      merged.visitScheduling = existing;
    } else if (key === 'programEncounterMappings' && Array.isArray(updateVal)) {
      const existing = [...((current as any).programEncounterMappings || [])] as any[];
      for (const newPem of updateVal as any[]) {
        const idx = existing.findIndex((p: any) => p.program?.toLowerCase() === newPem.program?.toLowerCase());
        if (idx >= 0) existing[idx] = { ...existing[idx], ...newPem };
        else existing.push(newPem);
      }
      merged.programEncounterMappings = existing;
    } else if (key === 'eligibilityRules' && Array.isArray(updateVal)) {
      const existing = [...((current as any).eligibilityRules || [])] as any[];
      for (const newRule of updateVal as any[]) {
        const idx = existing.findIndex((r: any) => r.program?.toLowerCase() === newRule.program?.toLowerCase());
        if (idx >= 0) existing[idx] = newRule;
        else existing.push(newRule);
      }
      merged.eligibilityRules = existing;
    } else if (key === 'users' && Array.isArray(updateVal)) {
      const existing = [...(current.users || [])] as any[];
      for (const newUser of updateVal as any[]) {
        const idx = existing.findIndex((u: any) => u.type?.toLowerCase() === newUser.type?.toLowerCase());
        if (idx >= 0) existing[idx] = { ...existing[idx], ...newUser };
        else existing.push({ ...newUser, id: newUser.id || crypto.randomUUID() });
      }
      merged.users = existing;
    } else if (key === 'w3h' && Array.isArray(updateVal)) {
      const existing = [...(current.w3h || [])] as any[];
      for (const newEntry of updateVal as any[]) {
        const idx = existing.findIndex((e: any) => e.what?.toLowerCase() === newEntry.what?.toLowerCase());
        if (idx >= 0) existing[idx] = { ...existing[idx], ...newEntry };
        else existing.push({ ...newEntry, id: newEntry.id || crypto.randomUUID() });
      }
      merged.w3h = existing;
    } else if (key === 'dashboardCards' && Array.isArray(updateVal)) {
      const existing = [...(current.dashboardCards || [])] as any[];
      for (const newCard of updateVal as any[]) {
        const idx = existing.findIndex((c: any) => c.cardName?.toLowerCase() === newCard.cardName?.toLowerCase());
        if (idx >= 0) existing[idx] = { ...existing[idx], ...newCard };
        else existing.push({ ...newCard, id: newCard.id || crypto.randomUUID() });
      }
      merged.dashboardCards = existing;
    } else if (Array.isArray(updateVal)) {
      const currentArr = ((current as any)[key] || []) as any[];
      const existingSet = new Set(currentArr.map((v: any) => JSON.stringify(v)));
      const combined = [...currentArr];
      for (const item of updateVal) {
        if (!existingSet.has(JSON.stringify(item))) {
          combined.push(item);
        }
      }
      merged[key] = combined;
    } else if (typeof updateVal === 'object' && updateVal !== null) {
      const currentVal = (current as Record<string, unknown>)[key];
      merged[key] = { ...(currentVal as Record<string, unknown> || {}), ...updateVal as Record<string, unknown> };
    } else {
      merged[key] = updateVal;
    }
  }

  return merged as unknown as SRSData;
}

// ── Utility helpers ───────────────────────────────────────────────────────────

export function getFieldCount(form: any): number {
  if (form.groups && Array.isArray(form.groups)) {
    return form.groups.reduce((sum: number, g: any) => sum + (g.fields?.length || 0), 0);
  }
  return form.fields?.length || 0;
}

export function getAllFields(form: any): any[] {
  if (form.groups && Array.isArray(form.groups)) {
    return form.groups.flatMap((g: any) => g.fields || []);
  }
  return form.fields || [];
}

// ── Progress Bar Component ───────────────────────────────────────────────────

function PhaseProgressBar({ currentPhase }: { currentPhase: Phase }) {
  const currentIdx = PHASE_ORDER.indexOf(currentPhase);
  const totalPhases = PHASE_ORDER.length - 1;
  const completedPhases = Math.max(0, currentIdx);
  const percentage = Math.round((completedPhases / totalPhases) * 100);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>Progress</span>
        <span className="font-medium text-gray-700">{percentage}%</span>
      </div>
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-teal-500 rounded-full transition-all duration-700 ease-out"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <div className="flex flex-wrap gap-1">
        {PHASE_ORDER.slice(1).map((phase, i) => {
          const phaseIdx = i + 1;
          const isCompleted = phaseIdx < currentIdx;
          const isCurrent = phaseIdx === currentIdx;
          return (
            <span
              key={phase}
              className={clsx(
                'px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors',
                isCompleted && 'bg-teal-100 text-teal-700',
                isCurrent && 'bg-teal-600 text-white',
                !isCompleted && !isCurrent && 'bg-gray-100 text-gray-400'
              )}
            >
              {PHASE_LABELS[phase]}
            </span>
          );
        })}
      </div>
    </div>
  );
}

// ── Collapsible Section Component ────────────────────────────────────────────

function CollapsibleSection({
  title,
  icon: Icon,
  count,
  isEmpty,
  isHighlighted,
  isEditing,
  onToggleEdit,
  children,
  editContent,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  count?: number;
  isEmpty: boolean;
  isHighlighted: boolean;
  isEditing: boolean;
  onToggleEdit: () => void;
  children: React.ReactNode;
  editContent?: React.ReactNode;
}) {
  const [isExpanded, setIsExpanded] = useState(!isEmpty);

  useEffect(() => {
    if (isHighlighted && isEmpty === false) {
      setIsExpanded(true);
    }
  }, [isHighlighted, isEmpty]);

  return (
    <div
      className={clsx(
        'border rounded-lg transition-all duration-500',
        isHighlighted
          ? 'border-green-400 bg-green-50 ring-2 ring-green-200'
          : isEmpty
            ? 'border-gray-200 bg-gray-50/50'
            : 'border-gray-200 bg-white'
      )}
    >
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer select-none"
        onClick={() => setIsExpanded(prev => !prev)}
      >
        {isExpanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-gray-400 shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-gray-400 shrink-0" />
        )}
        <Icon className={clsx('w-4 h-4 shrink-0', isEmpty ? 'text-gray-300' : 'text-teal-600')} />
        <span className={clsx('text-sm font-medium flex-1', isEmpty ? 'text-gray-400' : 'text-gray-800')}>
          {title}
        </span>
        {count !== undefined && count > 0 && (
          <span className="px-1.5 py-0.5 bg-teal-100 text-teal-700 text-[10px] font-medium rounded">
            {count}
          </span>
        )}
        <button
          onClick={e => {
            e.stopPropagation();
            onToggleEdit();
          }}
          className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
          title="Edit"
        >
          {isEditing ? <Check className="w-3.5 h-3.5 text-teal-600" /> : <Pencil className="w-3.5 h-3.5" />}
        </button>
      </div>
      {isExpanded && (
        <div className="px-3 pb-3 border-t border-gray-100">
          {isEditing && editContent ? editContent : children}
        </div>
      )}
    </div>
  );
}

// ── Inline Editors ───────────────────────────────────────────────────────────

function OrgEditor({
  summary,
  onChange,
}: {
  summary: ProgramSummaryData;
  onChange: (s: ProgramSummaryData) => void;
}) {
  return (
    <div className="space-y-2 pt-2">
      {[
        { label: 'Name', key: 'organizationName' as const, type: 'text' },
        { label: 'Location', key: 'location' as const, type: 'text' },
        { label: 'Hierarchy', key: 'locationHierarchy' as const, type: 'text' },
        { label: 'Challenges', key: 'challenges' as const, type: 'text' },
      ].map(({ label, key, type }) => (
        <div key={key}>
          <label className="text-[10px] font-medium text-gray-500 uppercase tracking-wide">{label}</label>
          <input
            type={type}
            value={(summary[key] as string) || ''}
            onChange={e => onChange({ ...summary, [key]: e.target.value })}
            className="w-full mt-0.5 px-2 py-1 text-xs border border-gray-200 rounded focus:ring-1 focus:ring-teal-500 focus:border-teal-500 outline-none"
          />
        </div>
      ))}
    </div>
  );
}

function ProgramsEditor({
  programs,
  onChange,
  onItemAdded,
}: {
  programs: ProgramDetailData[];
  onChange: (p: ProgramDetailData[]) => void;
  onItemAdded?: () => void;
}) {
  const addProgram = () => {
    onChange([
      ...programs,
      {
        id: crypto.randomUUID(),
        name: '',
        objective: '',
        eligibility: '',
        entryPoint: '',
        exitCriteria: '',
        totalBeneficiaries: 0,
        successIndicators: '',
        forms: [],
        reportsNeeded: '',
      },
    ]);
    onItemAdded?.();
  };

  const removeProgram = (id: string) => {
    onChange(programs.filter(p => p.id !== id));
  };

  const updateProgram = (id: string, field: string, value: string) => {
    onChange(programs.map(p => (p.id === id ? { ...p, [field]: value } : p)));
  };

  return (
    <div className="space-y-2 pt-2">
      {programs.map(prog => (
        <div key={prog.id} className="flex items-center gap-1.5">
          <input
            value={prog.name}
            onChange={e => updateProgram(prog.id, 'name', e.target.value)}
            placeholder="Program name"
            className="flex-1 px-2 py-1 text-xs border border-gray-200 rounded focus:ring-1 focus:ring-teal-500 focus:border-teal-500 outline-none"
          />
          <button
            onClick={() => removeProgram(prog.id)}
            className="p-1 text-red-400 hover:text-red-600 transition-colors"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      ))}
      <button
        onClick={addProgram}
        className="flex items-center gap-1 text-xs text-teal-600 hover:text-teal-800 transition-colors"
      >
        <Plus className="w-3 h-3" /> Add program
      </button>
    </div>
  );
}

function UsersEditor({
  users,
  onChange,
  onItemAdded,
}: {
  users: UserPersonaData[];
  onChange: (u: UserPersonaData[]) => void;
  onItemAdded?: () => void;
}) {
  const addUser = () => {
    onChange([...users, { id: crypto.randomUUID(), type: '', description: '', count: 0 }]);
    onItemAdded?.();
  };

  const removeUser = (id: string) => {
    onChange(users.filter(u => u.id !== id));
  };

  const updateUser = (id: string, field: string, value: string | number) => {
    onChange(users.map(u => (u.id === id ? { ...u, [field]: value } : u)));
  };

  return (
    <div className="space-y-2 pt-2">
      {users.map(user => (
        <div key={user.id} className="flex items-center gap-1.5">
          <input
            value={user.type}
            onChange={e => updateUser(user.id, 'type', e.target.value)}
            placeholder="User type (e.g. ANM, ASHA)"
            className="flex-1 px-2 py-1 text-xs border border-gray-200 rounded focus:ring-1 focus:ring-teal-500 focus:border-teal-500 outline-none"
          />
          <button
            onClick={() => removeUser(user.id)}
            className="p-1 text-red-400 hover:text-red-600 transition-colors"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      ))}
      <button
        onClick={addUser}
        className="flex items-center gap-1 text-xs text-teal-600 hover:text-teal-800 transition-colors"
      >
        <Plus className="w-3 h-3" /> Add user type
      </button>
    </div>
  );
}

function FormsEditor({
  forms,
  onChange,
  onItemAdded,
}: {
  forms: FormDefinitionData[];
  onChange: (f: FormDefinitionData[]) => void;
  onItemAdded?: () => void;
}) {
  const [expandedForm, setExpandedForm] = useState<string | null>(null);

  const addForm = () => {
    const newForm: FormDefinitionData = {
      id: crypto.randomUUID(),
      name: '',
      fields: [],
    };
    onChange([...forms, newForm]);
    setExpandedForm(newForm.id);
  };

  const removeForm = (id: string) => {
    onChange(forms.filter(f => f.id !== id));
  };

  const updateFormName = (id: string, name: string) => {
    onChange(forms.map(f => (f.id === id ? { ...f, name } : f)));
  };

  const getFormFields = (form: FormDefinitionData): FormFieldData[] => {
    return getAllFields(form) as FormFieldData[];
  };

  const addField = (formId: string) => {
    const newField: FormFieldData = {
      id: crypto.randomUUID(),
      pageName: 'Default',
      fieldName: '',
      dataType: 'Text' as FormFieldDataType,
      mandatory: false,
      userOrSystem: 'User Enter' as const,
      options: '',
      selectionType: 'Single' as const,
      unit: '',
      min: '',
      max: '',
      skipLogic: '',
    };
    onChange(
      forms.map(f => {
        if (f.id !== formId) return f;
        if ((f as any).groups && Array.isArray((f as any).groups)) {
          const groups = [...(f as any).groups];
          if (groups.length === 0) {
            groups.push({ name: 'Default', fields: [newField] });
          } else {
            groups[0] = { ...groups[0], fields: [...(groups[0].fields || []), newField] };
          }
          return { ...f, groups } as any;
        }
        return { ...f, fields: [...f.fields, newField] };
      })
    );
    onItemAdded?.();
  };

  const updateField = (formId: string, fieldId: string, updates: Partial<FormFieldData>) => {
    onChange(
      forms.map(f => {
        if (f.id !== formId) return f;
        if ((f as any).groups && Array.isArray((f as any).groups)) {
          const groups = (f as any).groups.map((g: any) => ({
            ...g,
            fields: (g.fields || []).map((fld: any) => (fld.id === fieldId ? { ...fld, ...updates } : fld)),
          }));
          return { ...f, groups } as any;
        }
        return { ...f, fields: f.fields.map(fld => (fld.id === fieldId ? { ...fld, ...updates } : fld)) };
      })
    );
  };

  const removeField = (formId: string, fieldId: string) => {
    onChange(
      forms.map(f => {
        if (f.id !== formId) return f;
        if ((f as any).groups && Array.isArray((f as any).groups)) {
          const groups = (f as any).groups.map((g: any) => ({
            ...g,
            fields: (g.fields || []).filter((fld: any) => fld.id !== fieldId),
          }));
          return { ...f, groups } as any;
        }
        return { ...f, fields: f.fields.filter(fld => fld.id !== fieldId) };
      })
    );
  };

  const DATA_TYPES: FormFieldDataType[] = [
    'Text', 'Numeric', 'Date', 'Coded', 'Notes', 'Time', 'Image', 'PhoneNumber', 'Subject', 'QuestionGroup',
  ];

  return (
    <div className="space-y-2 pt-2">
      {forms.map(form => (
        <div key={form.id} className="border border-gray-100 rounded p-2 space-y-1.5">
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setExpandedForm(expandedForm === form.id ? null : form.id)}
              className="p-0.5 text-gray-400"
            >
              {expandedForm === form.id ? (
                <ChevronDown className="w-3 h-3" />
              ) : (
                <ChevronRight className="w-3 h-3" />
              )}
            </button>
            <input
              value={form.name}
              onChange={e => updateFormName(form.id, e.target.value)}
              placeholder="Form name"
              className="flex-1 px-2 py-1 text-xs border border-gray-200 rounded focus:ring-1 focus:ring-teal-500 focus:border-teal-500 outline-none"
            />
            <span className="text-[10px] text-gray-400">{getFieldCount(form)} fields</span>
            <button
              onClick={() => removeForm(form.id)}
              className="p-1 text-red-400 hover:text-red-600 transition-colors"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </div>

          {expandedForm === form.id && (
            <div className="ml-4 space-y-1.5 pt-1">
              {getFormFields(form).map(field => (
                <div key={field.id} className="flex items-center gap-1 flex-wrap">
                  <input
                    value={field.fieldName}
                    onChange={e => updateField(form.id, field.id, { fieldName: e.target.value })}
                    placeholder="Field name"
                    className="flex-1 min-w-[100px] px-1.5 py-0.5 text-[11px] border border-gray-200 rounded focus:ring-1 focus:ring-teal-500 outline-none"
                  />
                  <select
                    value={field.dataType}
                    onChange={e =>
                      updateField(form.id, field.id, { dataType: e.target.value as FormFieldDataType })
                    }
                    className="px-1 py-0.5 text-[11px] border border-gray-200 rounded focus:ring-1 focus:ring-teal-500 outline-none bg-white"
                  >
                    {DATA_TYPES.map(dt => (
                      <option key={dt} value={dt}>
                        {dt}
                      </option>
                    ))}
                  </select>
                  <label className="flex items-center gap-0.5 text-[10px] text-gray-500">
                    <input
                      type="checkbox"
                      checked={field.mandatory}
                      onChange={e => updateField(form.id, field.id, { mandatory: e.target.checked })}
                      className="rounded border-gray-300 text-teal-600 focus:ring-teal-500 w-3 h-3"
                    />
                    Req
                  </label>
                  <button
                    onClick={() => removeField(form.id, field.id)}
                    className="p-0.5 text-red-400 hover:text-red-600"
                  >
                    <Trash2 className="w-2.5 h-2.5" />
                  </button>
                </div>
              ))}
              <button
                onClick={() => addField(form.id)}
                className="flex items-center gap-1 text-[11px] text-teal-600 hover:text-teal-800"
              >
                <Plus className="w-3 h-3" /> Add field
              </button>
            </div>
          )}
        </div>
      ))}
      <button
        onClick={addForm}
        className="flex items-center gap-1 text-xs text-teal-600 hover:text-teal-800 transition-colors"
      >
        <Plus className="w-3 h-3" /> Add form
      </button>
    </div>
  );
}

function SchedulingEditor({
  scheduling,
  onChange,
  onItemAdded,
}: {
  scheduling: VisitScheduleData[];
  onChange: (s: VisitScheduleData[]) => void;
  onItemAdded?: () => void;
}) {
  const addSchedule = () => {
    onChange([
      ...scheduling,
      {
        id: crypto.randomUUID(),
        onCompletionOf: '',
        scheduleForm: '',
        frequency: 'Monthly',
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
    onItemAdded?.();
  };

  const removeSchedule = (id: string) => {
    onChange(scheduling.filter(s => s.id !== id));
  };

  const updateSchedule = (id: string, field: string, value: string) => {
    onChange(scheduling.map(s => (s.id === id ? { ...s, [field]: value } : s)));
  };

  return (
    <div className="space-y-2 pt-2">
      {scheduling.map(sched => (
        <div key={sched.id} className="flex items-center gap-1.5 flex-wrap">
          <input
            value={sched.scheduleForm}
            onChange={e => updateSchedule(sched.id, 'scheduleForm', e.target.value)}
            placeholder="Form to schedule"
            className="flex-1 min-w-[80px] px-2 py-1 text-xs border border-gray-200 rounded focus:ring-1 focus:ring-teal-500 outline-none"
          />
          <select
            value={sched.frequency}
            onChange={e => updateSchedule(sched.id, 'frequency', e.target.value)}
            className="px-1 py-1 text-xs border border-gray-200 rounded focus:ring-1 focus:ring-teal-500 outline-none bg-white"
          >
            {['Daily', 'Weekly', 'Monthly', 'Quarterly', 'Yearly', 'One-time'].map(f => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
          <button
            onClick={() => removeSchedule(sched.id)}
            className="p-1 text-red-400 hover:text-red-600"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      ))}
      <button
        onClick={addSchedule}
        className="flex items-center gap-1 text-xs text-teal-600 hover:text-teal-800"
      >
        <Plus className="w-3 h-3" /> Add schedule
      </button>
    </div>
  );
}

function DashboardEditor({
  cards,
  onChange,
  onItemAdded,
}: {
  cards: DashboardCardData[];
  onChange: (c: DashboardCardData[]) => void;
  onItemAdded?: () => void;
}) {
  const addCard = () => {
    onChange([...cards, { id: crypto.randomUUID(), cardName: '', logic: '', userType: '' }]);
    onItemAdded?.();
  };

  const removeCard = (id: string) => {
    onChange(cards.filter(c => c.id !== id));
  };

  const updateCard = (id: string, field: string, value: string) => {
    onChange(cards.map(c => (c.id === id ? { ...c, [field]: value } : c)));
  };

  return (
    <div className="space-y-2 pt-2">
      {cards.map(card => (
        <div key={card.id} className="flex items-center gap-1.5">
          <input
            value={card.cardName}
            onChange={e => updateCard(card.id, 'cardName', e.target.value)}
            placeholder="Card name"
            className="flex-1 px-2 py-1 text-xs border border-gray-200 rounded focus:ring-1 focus:ring-teal-500 outline-none"
          />
          <button
            onClick={() => removeCard(card.id)}
            className="p-1 text-red-400 hover:text-red-600"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      ))}
      <button
        onClick={addCard}
        className="flex items-center gap-1 text-xs text-teal-600 hover:text-teal-800"
      >
        <Plus className="w-3 h-3" /> Add card
      </button>
    </div>
  );
}

// ── Main Preview Panel Component ─────────────────────────────────────────────

export function SRSPreviewPanel({
  srsData,
  phase,
  onSrsChange,
  onGenerateBundle,
  bundleStatus,
  bundleId,
  onClose,
  onItemAdded,
}: SRSPreviewPanelProps) {
  const [editingSection, setEditingSection] = useState<PreviewSection | null>(null);
  const [highlightedSections, setHighlightedSections] = useState<Set<string>>(new Set());
  const [bundleError, setBundleError] = useState<string | null>(null);

  const toggleEdit = useCallback((section: PreviewSection) => {
    setEditingSection(prev => (prev === section ? null : section));
  }, []);

  // Reset error when status changes
  useEffect(() => {
    if (bundleStatus !== 'error') setBundleError(null);
  }, [bundleStatus]);

  // Expose highlight function via a custom event listener so useChat can trigger highlights
  useEffect(() => {
    const handler = (e: Event) => {
      const sectionKey = (e as CustomEvent).detail?.section;
      if (sectionKey) {
        setHighlightedSections(prev => new Set(prev).add(sectionKey));
        setTimeout(() => {
          setHighlightedSections(prev => {
            const next = new Set(prev);
            next.delete(sectionKey);
            return next;
          });
        }, 2000);
      }
    };
    window.addEventListener('srs-highlight-section', handler);
    return () => window.removeEventListener('srs-highlight-section', handler);
  }, []);

  const formFieldCount = useMemo(
    () => (srsData.forms || []).reduce((sum, f) => sum + getFieldCount(f), 0),
    [srsData.forms]
  );

  const hasOrg = Boolean(srsData.summary?.organizationName || (srsData as any).orgName);
  const hasPrograms = (srsData.programs || []).length > 0;
  const hasUsers = (srsData.users || []).length > 0;
  const hasForms = (srsData.forms || []).length > 0;
  const hasScheduling = (srsData.visitScheduling || []).length > 0;
  const hasDashboard = (srsData.dashboardCards || []).length > 0;

  const canGenerate = useMemo(() => {
    if (!srsData.summary?.organizationName && !(srsData as any).orgName) {
      return { ok: false, reason: 'Organization name is required' };
    }
    const forms = srsData.forms || [];
    if (forms.length === 0) {
      return { ok: false, reason: 'At least one form is required' };
    }
    const hasFields = forms.some((f: any) => getFieldCount(f) > 0);
    if (!hasFields) {
      return { ok: false, reason: 'At least one form needs fields' };
    }
    return { ok: true };
  }, [srsData]);

  const downloadBundle = useCallback(async () => {
    if (!bundleId) return;
    try {
      const response = await authFetch(`/api/bundle/${bundleId}/download`);
      if (!response.ok) throw new Error('Download failed');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `avni-bundle-${bundleId}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setBundleError('Failed to download bundle');
    }
  }, [bundleId]);

  return (
    <div className="flex flex-col border-l border-gray-200 bg-gray-50/80 w-full sm:w-[40%] min-w-0 overflow-hidden">
      {/* Panel header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-200 bg-white shrink-0">
        <div className="flex items-center gap-2">
          <Package className="w-4 h-4 text-teal-600" />
          <span className="text-sm font-semibold text-gray-900">SRS Preview</span>
        </div>
        <button
          onClick={onClose}
          className="p-1 text-gray-400 hover:text-gray-600 transition-colors rounded hover:bg-gray-100"
          aria-label="Close SRS panel"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Scrollable sections */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-2">
        {/* Organization */}
        <CollapsibleSection
          title="Organization"
          icon={Building2}
          isEmpty={!hasOrg}
          isHighlighted={highlightedSections.has('organization')}
          isEditing={editingSection === 'organization'}
          onToggleEdit={() => toggleEdit('organization')}
          editContent={
            <OrgEditor
              summary={srsData.summary}
              onChange={summary => onSrsChange({ ...srsData, summary })}
            />
          }
        >
          {hasOrg ? (
            <div className="pt-2 space-y-1">
              <div className="text-xs">
                <span className="text-gray-500">Name:</span>{' '}
                <span className="font-medium text-gray-800">{srsData.summary?.organizationName}</span>
              </div>
              {srsData.summary?.location && (
                <div className="text-xs">
                  <span className="text-gray-500">Location:</span>{' '}
                  <span className="text-gray-700">{srsData.summary?.location}</span>
                </div>
              )}
              {srsData.summary?.locationHierarchy && (
                <div className="text-xs">
                  <span className="text-gray-500">Hierarchy:</span>{' '}
                  <span className="text-gray-700">{srsData.summary?.locationHierarchy}</span>
                </div>
              )}
              {srsData.summary?.challenges && (
                <div className="text-xs">
                  <span className="text-gray-500">Challenges:</span>{' '}
                  <span className="text-gray-700">{srsData.summary?.challenges}</span>
                </div>
              )}
            </div>
          ) : (
            <p className="pt-2 text-xs text-gray-400 italic">Not yet defined</p>
          )}
        </CollapsibleSection>

        {/* Subject Types / Users */}
        <CollapsibleSection
          title="Subject Types / Users"
          icon={Users}
          count={(srsData.users || []).length}
          isEmpty={!hasUsers}
          isHighlighted={highlightedSections.has('subjects')}
          isEditing={editingSection === 'subjects'}
          onToggleEdit={() => toggleEdit('subjects')}
          editContent={
            <UsersEditor
              users={srsData.users || []}
              onChange={users => onSrsChange({ ...srsData, users })}
              onItemAdded={onItemAdded}
            />
          }
        >
          {hasUsers ? (
            <div className="pt-2 space-y-1">
              {(srsData.users || []).map(u => (
                <div key={u.id} className="flex items-center gap-2 text-xs">
                  <span className="px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded font-medium">
                    {u.type || 'Unnamed'}
                  </span>
                  {u.description && (
                    <span className="text-gray-500 truncate">{u.description}</span>
                  )}
                  {u.count > 0 && (
                    <span className="text-gray-400 ml-auto shrink-0">x{u.count}</span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="pt-2 text-xs text-gray-400 italic">Not yet defined</p>
          )}
        </CollapsibleSection>

        {/* Programs */}
        <CollapsibleSection
          title="Programs"
          icon={ClipboardList}
          count={(srsData.programs || []).length}
          isEmpty={!hasPrograms}
          isHighlighted={highlightedSections.has('programs')}
          isEditing={editingSection === 'programs'}
          onToggleEdit={() => toggleEdit('programs')}
          editContent={
            <ProgramsEditor
              programs={srsData.programs || []}
              onChange={programs => onSrsChange({ ...srsData, programs })}
              onItemAdded={onItemAdded}
            />
          }
        >
          {hasPrograms ? (
            <div className="pt-2 space-y-1.5">
              {(srsData.programs || []).map(p => (
                <div key={p.id} className="text-xs">
                  <div className="font-medium text-gray-800">{p.name || 'Unnamed'}</div>
                  {p.forms && p.forms.length > 0 && (
                    <div className="ml-3 mt-0.5 text-gray-500">
                      {p.forms.map((f, i) => (
                        <span key={i}>
                          {i > 0 && ', '}
                          {f}
                        </span>
                      ))}
                    </div>
                  )}
                  {p.objective && (
                    <div className="ml-3 mt-0.5 text-gray-400 truncate">{p.objective}</div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="pt-2 text-xs text-gray-400 italic">Not yet defined</p>
          )}
        </CollapsibleSection>

        {/* Forms */}
        <CollapsibleSection
          title="Forms"
          icon={FileText}
          count={(srsData.forms || []).length}
          isEmpty={!hasForms}
          isHighlighted={highlightedSections.has('forms')}
          isEditing={editingSection === 'forms'}
          onToggleEdit={() => toggleEdit('forms')}
          editContent={
            <FormsEditor
              forms={srsData.forms || []}
              onChange={forms => onSrsChange({ ...srsData, forms })}
              onItemAdded={onItemAdded}
            />
          }
        >
          {hasForms ? (
            <div className="pt-2 space-y-1">
              {(srsData.forms || []).map(f => (
                <div key={f.id} className="flex items-center justify-between text-xs">
                  <span className="font-medium text-gray-800">{f.name || 'Unnamed'}</span>
                  <span className="text-gray-400">{getFieldCount(f)} fields</span>
                </div>
              ))}
              <div className="text-[10px] text-gray-400 pt-1">
                Total: {(srsData.forms || []).length} forms, {formFieldCount} fields
              </div>
            </div>
          ) : (
            <p className="pt-2 text-xs text-gray-400 italic">Not yet defined</p>
          )}
        </CollapsibleSection>

        {/* Visit Scheduling */}
        <CollapsibleSection
          title="Visit Scheduling"
          icon={CalendarClock}
          count={(srsData.visitScheduling || []).length}
          isEmpty={!hasScheduling}
          isHighlighted={highlightedSections.has('scheduling')}
          isEditing={editingSection === 'scheduling'}
          onToggleEdit={() => toggleEdit('scheduling')}
          editContent={
            <SchedulingEditor
              scheduling={srsData.visitScheduling || []}
              onChange={visitScheduling => onSrsChange({ ...srsData, visitScheduling })}
              onItemAdded={onItemAdded}
            />
          }
        >
          {hasScheduling ? (
            <div className="pt-2">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-gray-400">
                    <th className="text-left font-medium pr-2">Form</th>
                    <th className="text-left font-medium pr-2">Frequency</th>
                    <th className="text-left font-medium">Overdue</th>
                  </tr>
                </thead>
                <tbody>
                  {(srsData.visitScheduling || []).map(vs => (
                    <tr key={vs.id} className="text-gray-700">
                      <td className="pr-2 py-0.5">{vs.scheduleForm || '-'}</td>
                      <td className="pr-2 py-0.5">{vs.frequency}</td>
                      <td className="py-0.5">{vs.overdueDate || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="pt-2 text-xs text-gray-400 italic">Not yet defined</p>
          )}
        </CollapsibleSection>

        {/* Dashboard Cards */}
        <CollapsibleSection
          title="Dashboard Cards"
          icon={LayoutDashboard}
          count={(srsData.dashboardCards || []).length}
          isEmpty={!hasDashboard}
          isHighlighted={highlightedSections.has('dashboard')}
          isEditing={editingSection === 'dashboard'}
          onToggleEdit={() => toggleEdit('dashboard')}
          editContent={
            <DashboardEditor
              cards={srsData.dashboardCards || []}
              onChange={dashboardCards => onSrsChange({ ...srsData, dashboardCards })}
              onItemAdded={onItemAdded}
            />
          }
        >
          {hasDashboard ? (
            <div className="pt-2 space-y-1">
              {(srsData.dashboardCards || []).map(c => (
                <div key={c.id} className="flex items-center justify-between text-xs">
                  <span className="text-gray-800">{c.cardName || 'Unnamed'}</span>
                  {c.userType && (
                    <span className="text-gray-400">{c.userType}</span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="pt-2 text-xs text-gray-400 italic">Not yet defined</p>
          )}
        </CollapsibleSection>

        {/* Permissions */}
        <CollapsibleSection
          title="Groups / Permissions"
          icon={Shield}
          isEmpty={Object.keys(srsData.permissions || {}).length === 0}
          isHighlighted={highlightedSections.has('permissions')}
          isEditing={editingSection === 'permissions'}
          onToggleEdit={() => toggleEdit('permissions')}
        >
          {Object.keys(srsData.permissions || {}).length > 0 ? (
            <div className="pt-2 text-xs text-gray-700">
              {Object.keys(srsData.permissions || {}).length} permission entries configured
            </div>
          ) : (
            <p className="pt-2 text-xs text-gray-400 italic">
              Will be auto-generated from user types and forms
            </p>
          )}
        </CollapsibleSection>

        {/* Progress Bar */}
        <div className="border border-gray-200 rounded-lg bg-white p-3">
          <PhaseProgressBar currentPhase={(phase || 'start') as Phase} />
        </div>
      </div>

      {/* Generate Bundle Button */}
      <div className="px-3 py-3 border-t border-gray-200 bg-white shrink-0">
        {bundleStatus === 'done' ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 rounded-lg px-3 py-2">
              <Check className="w-4 h-4 shrink-0" />
              Bundle generated successfully!
            </div>
            <button
              onClick={downloadBundle}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-teal-700 text-white text-sm font-medium rounded-xl hover:bg-teal-800 transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500"
            >
              <Download className="w-4 h-4" />
              Download Bundle
            </button>
          </div>
        ) : bundleStatus === 'error' ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 rounded-lg px-3 py-2">
              <X className="w-4 h-4 shrink-0" />
              {bundleError || 'Something went wrong. Please try again.'}
            </div>
            <button
              onClick={onGenerateBundle}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-teal-700 text-white text-sm font-medium rounded-xl hover:bg-teal-800 transition-colors"
            >
              <Package className="w-4 h-4" />
              Retry
            </button>
          </div>
        ) : (
          <div className="space-y-1.5">
            <button
              onClick={onGenerateBundle}
              disabled={bundleStatus === 'generating' || !canGenerate.ok}
              className={clsx(
                'w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium rounded-xl transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500',
                bundleStatus === 'generating'
                  ? 'bg-teal-200 text-teal-700 cursor-wait'
                  : !canGenerate.ok
                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    : 'bg-teal-700 text-white hover:bg-teal-800'
              )}
            >
              {bundleStatus === 'generating' ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Package className="w-4 h-4" />
                  Generate Bundle
                </>
              )}
            </button>
            {!canGenerate.ok && canGenerate.reason && (
              <p className="text-[11px] text-gray-400 text-center">{canGenerate.reason}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
