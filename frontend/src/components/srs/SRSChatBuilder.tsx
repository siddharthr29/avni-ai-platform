import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { authFetch } from '../../services/api';
import {
  Send,
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
  ArrowLeft,
  RotateCcw,
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
import { createDefaultSRSData } from '../../data/srs-templates.ts';

// ── Types ────────────────────────────────────────────────────────────────────

interface SRSChatBuilderProps {
  onClose: () => void;
  onBundleGenerated: (bundleId: string) => void;
  initialSrs?: SRSData;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
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

const WELCOME_MESSAGE = `Welcome! I'll help you build your Avni implementation step by step.

Let's start with the basics — **what's your organization's name**, and **what sector do you work in?**

(Common sectors: Maternal & Child Health, Nutrition, Education, Livelihoods, WASH)`;

// ── Utility: deep merge SRS updates (ADDITIVE for arrays) ───────────────────

function mergeSrsUpdate(current: SRSData, update: Partial<Record<string, unknown>>): SRSData {
  const merged = { ...current } as Record<string, unknown>;

  for (const key of Object.keys(update)) {
    const updateVal = update[key];
    if (updateVal === null || updateVal === undefined) continue; // Skip nulls

    if (key === 'forms' && Array.isArray(updateVal)) {
      // Forms: merge by name (update existing, add new)
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
      // Programs: merge by name
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
      // String arrays: UNION (deduplicate by lowercase)
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
      // SubjectTypes: merge by name
      const existing = [...((current as any).subjectTypes || [])] as any[];
      for (const newSt of updateVal as any[]) {
        const idx = existing.findIndex((st: any) => st.name?.toLowerCase() === newSt.name?.toLowerCase());
        if (idx >= 0) existing[idx] = { ...existing[idx], ...newSt };
        else existing.push(newSt);
      }
      merged.subjectTypes = existing;
    } else if (key === 'addressLevelTypes' && Array.isArray(updateVal)) {
      // Address levels: replace entirely (order matters)
      merged.addressLevelTypes = updateVal;
    } else if (key === 'visitSchedules' && Array.isArray(updateVal)) {
      // Visit schedules: merge by schedule_encounter name
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
      // Frontend visit scheduling format: merge by scheduleForm
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
      // PEM: merge by program name
      const existing = [...((current as any).programEncounterMappings || [])] as any[];
      for (const newPem of updateVal as any[]) {
        const idx = existing.findIndex((p: any) => p.program?.toLowerCase() === newPem.program?.toLowerCase());
        if (idx >= 0) existing[idx] = { ...existing[idx], ...newPem };
        else existing.push(newPem);
      }
      merged.programEncounterMappings = existing;
    } else if (key === 'eligibilityRules' && Array.isArray(updateVal)) {
      // Eligibility: merge by program name
      const existing = [...((current as any).eligibilityRules || [])] as any[];
      for (const newRule of updateVal as any[]) {
        const idx = existing.findIndex((r: any) => r.program?.toLowerCase() === newRule.program?.toLowerCase());
        if (idx >= 0) existing[idx] = newRule;
        else existing.push(newRule);
      }
      merged.eligibilityRules = existing;
    } else if (key === 'users' && Array.isArray(updateVal)) {
      // Users: merge by type name
      const existing = [...(current.users || [])] as any[];
      for (const newUser of updateVal as any[]) {
        const idx = existing.findIndex((u: any) => u.type?.toLowerCase() === newUser.type?.toLowerCase());
        if (idx >= 0) existing[idx] = { ...existing[idx], ...newUser };
        else existing.push({ ...newUser, id: newUser.id || crypto.randomUUID() });
      }
      merged.users = existing;
    } else if (key === 'w3h' && Array.isArray(updateVal)) {
      // W3H entries: merge by what name
      const existing = [...(current.w3h || [])] as any[];
      for (const newEntry of updateVal as any[]) {
        const idx = existing.findIndex((e: any) => e.what?.toLowerCase() === newEntry.what?.toLowerCase());
        if (idx >= 0) existing[idx] = { ...existing[idx], ...newEntry };
        else existing.push({ ...newEntry, id: newEntry.id || crypto.randomUUID() });
      }
      merged.w3h = existing;
    } else if (key === 'dashboardCards' && Array.isArray(updateVal)) {
      // Dashboard cards: merge by cardName
      const existing = [...(current.dashboardCards || [])] as any[];
      for (const newCard of updateVal as any[]) {
        const idx = existing.findIndex((c: any) => c.cardName?.toLowerCase() === newCard.cardName?.toLowerCase());
        if (idx >= 0) existing[idx] = { ...existing[idx], ...newCard };
        else existing.push({ ...newCard, id: newCard.id || crypto.randomUUID() });
      }
      merged.dashboardCards = existing;
    } else if (Array.isArray(updateVal)) {
      // Unknown arrays: union by value
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

// ── Utility: get field count from form (handles grouped and flat formats) ────

function getFieldCount(form: any): number {
  if (form.groups && Array.isArray(form.groups)) {
    return form.groups.reduce((sum: number, g: any) => sum + (g.fields?.length || 0), 0);
  }
  return form.fields?.length || 0;
}

function getAllFields(form: any): any[] {
  if (form.groups && Array.isArray(form.groups)) {
    return form.groups.flatMap((g: any) => g.fields || []);
  }
  return form.fields || [];
}

// ── Utility: user-friendly error messages ────────────────────────────────────

function userFriendlyError(err: any): string {
  const msg = err?.message || String(err);
  if (msg.includes('401') || msg.includes('auth')) return 'Authentication error. Please log in again.';
  if (msg.includes('429') || msg.includes('rate')) return 'Too many requests. Please wait a moment.';
  if (msg.includes('500')) return 'Server error. Please try again in a moment.';
  if (msg.includes('timeout') || msg.includes('abort')) return 'Request timed out. Please try again.';
  return 'Something went wrong. Please try again.';
}

// ── localStorage persistence key ─────────────────────────────────────────────

const STORAGE_KEY = 'avni-srs-chat-builder';

// ── Simple markdown renderer ─────────────────────────────────────────────────

function renderMarkdown(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code class="px-1 py-0.5 bg-gray-100 rounded text-xs font-mono">$1</code>')
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/\n/g, '<br/>');
}

// ── Progress Bar Component ───────────────────────────────────────────────────

function PhaseProgressBar({ currentPhase }: { currentPhase: Phase }) {
  const currentIdx = PHASE_ORDER.indexOf(currentPhase);
  const totalPhases = PHASE_ORDER.length - 1; // exclude 'start'
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

function PreviewSection({
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
}: {
  programs: ProgramDetailData[];
  onChange: (p: ProgramDetailData[]) => void;
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
}: {
  users: UserPersonaData[];
  onChange: (u: UserPersonaData[]) => void;
}) {
  const addUser = () => {
    onChange([...users, { id: crypto.randomUUID(), type: '', description: '', count: 0 }]);
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
}: {
  forms: FormDefinitionData[];
  onChange: (f: FormDefinitionData[]) => void;
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

  // Get fields from form (handles both flat and grouped formats)
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
        // If form uses groups format, add to first group (or create Default)
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
  };

  const updateField = (formId: string, fieldId: string, updates: Partial<FormFieldData>) => {
    onChange(
      forms.map(f => {
        if (f.id !== formId) return f;
        // Handle grouped format
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
        // Handle grouped format
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
}: {
  scheduling: VisitScheduleData[];
  onChange: (s: VisitScheduleData[]) => void;
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
}: {
  cards: DashboardCardData[];
  onChange: (c: DashboardCardData[]) => void;
}) {
  const addCard = () => {
    onChange([...cards, { id: crypto.randomUUID(), cardName: '', logic: '', userType: '' }]);
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

// ── Main Component ───────────────────────────────────────────────────────────

export function SRSChatBuilder({ onClose, onBundleGenerated, initialSrs }: SRSChatBuilderProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: WELCOME_MESSAGE,
      timestamp: new Date(),
    },
  ]);
  const [srsData, setSrsData] = useState<SRSData>(initialSrs ?? createDefaultSRSData());
  const [phase, setPhase] = useState<Phase>('start');
  const [isStreaming, setIsStreaming] = useState(false);
  const [input, setInput] = useState('');
  const [bundleId, setBundleId] = useState<string | null>(null);
  const [bundleStatus, setBundleStatus] = useState<'idle' | 'generating' | 'polling' | 'done' | 'error'>('idle');
  const [bundleError, setBundleError] = useState<string | null>(null);
  const [editingSection, setEditingSection] = useState<PreviewSection | null>(null);
  const [highlightedSections, setHighlightedSections] = useState<Set<string>>(new Set());
  const [showPreviewMobile, setShowPreviewMobile] = useState(false);

  const sessionIdRef = useRef(crypto.randomUUID());
  const assistantContentRef = useRef('');
  const assistantIdRef = useRef('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Restore from localStorage on mount (Fix 4)
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.srsData && Object.keys(parsed.srsData).length > 0) setSrsData(parsed.srsData);
        if (parsed.messages && parsed.messages.length > 0) setMessages(parsed.messages);
        if (parsed.phase) setPhase(parsed.phase);
        if (parsed.sessionId) sessionIdRef.current = parsed.sessionId;
      }
    } catch (e) {
      console.warn('Failed to restore SRS state:', e);
    }
  }, []);

  // Save to localStorage on every change (Fix 4)
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        srsData,
        messages: messages.slice(-30), // Keep last 30 messages
        phase,
        sessionId: sessionIdRef.current,
        savedAt: Date.now(),
      }));
    } catch (e) {
      console.warn('Failed to save SRS state:', e);
    }
  }, [srsData, messages, phase]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // Highlight sections temporarily when updated
  const highlightSection = useCallback((sectionKey: string) => {
    setHighlightedSections(prev => new Set(prev).add(sectionKey));
    setTimeout(() => {
      setHighlightedSections(prev => {
        const next = new Set(prev);
        next.delete(sectionKey);
        return next;
      });
    }, 2000);
  }, []);

  // ── New SRS (clear and reset) ─────────────────────────────────────────────

  const handleNewSrs = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setSrsData(createDefaultSRSData());
    setMessages([{
      id: crypto.randomUUID(),
      role: 'assistant',
      content: WELCOME_MESSAGE,
      timestamp: new Date(),
    }]);
    setPhase('start');
    sessionIdRef.current = crypto.randomUUID();
    setBundleId(null);
    setBundleStatus('idle');
    setBundleError(null);
    setEditingSection(null);
  }, []);

  // ── Bundle validation (Fix 6) ───────────────────────────────────────────

  const canGenerateBundle = useCallback((): { ok: boolean; reason?: string } => {
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

  // ── Send message via SSE ──────────────────────────────────────────────────

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || isStreaming) return;

      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: content.trim(),
        timestamp: new Date(),
      };

      const assistantId = crypto.randomUUID();
      assistantIdRef.current = assistantId;
      assistantContentRef.current = '';

      const assistantMessage: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
      };

      setMessages(prev => [...prev, userMessage, assistantMessage]);
      setInput('');
      setIsStreaming(true);

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await authFetch('/api/srs/chat-builder', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: content.trim(),
            session_id: sessionIdRef.current,
            current_srs: srsData,
            conversation_phase: phase,
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`Request failed: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith('event:')) continue;

            if (trimmed.startsWith('data:')) {
              const jsonStr = trimmed.slice(5).trim();
              if (jsonStr === '[DONE]') break;

              try {
                const parsed = JSON.parse(jsonStr);

                if (parsed.type === 'done') {
                  break;
                }

                if (parsed.type === 'error') {
                  assistantContentRef.current = parsed.content ?? 'An error occurred.';
                  setMessages(prev =>
                    prev.map(m =>
                      m.id === assistantIdRef.current
                        ? { ...m, content: assistantContentRef.current }
                        : m
                    )
                  );
                  break;
                }

                if (parsed.type === 'text' && parsed.content) {
                  assistantContentRef.current += parsed.content;
                  setMessages(prev =>
                    prev.map(m =>
                      m.id === assistantIdRef.current
                        ? { ...m, content: assistantContentRef.current }
                        : m
                    )
                  );
                }

                if (parsed.type === 'srs_update' && parsed.data) {
                  setSrsData(prev => {
                    const updated = mergeSrsUpdate(prev, parsed.data);
                    // Determine which sections were updated and highlight them
                    for (const key of Object.keys(parsed.data)) {
                      const sectionMap: Record<string, string> = {
                        summary: 'organization',
                        programs: 'programs',
                        users: 'subjects',
                        forms: 'forms',
                        visitScheduling: 'scheduling',
                        dashboardCards: 'dashboard',
                        permissions: 'permissions',
                        w3h: 'programs',
                      };
                      if (sectionMap[key]) {
                        highlightSection(sectionMap[key]);
                      }
                    }
                    return updated;
                  });
                }

                if (parsed.type === 'phase' && parsed.phase) {
                  setPhase(parsed.phase as Phase);
                }
              } catch {
                // Not valid JSON, skip
              }
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          const errorMsg = userFriendlyError(err);
          assistantContentRef.current = `Sorry, I encountered an issue. ${errorMsg}`;
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantIdRef.current
                ? { ...m, content: assistantContentRef.current }
                : m
            )
          );
        }
      } finally {
        setIsStreaming(false);
      }
    },
    [isStreaming, srsData, phase, highlightSection]
  );

  // ── Generate Bundle ───────────────────────────────────────────────────────

  const generateBundle = useCallback(async () => {
    // Validate before generating (Fix 6)
    const validation = canGenerateBundle();
    if (!validation.ok) {
      setBundleStatus('error');
      setBundleError(validation.reason || 'Validation failed');
      return;
    }

    setBundleStatus('generating');
    setBundleError(null);

    try {
      // The chat builder's srsData may use either frontend or backend format
      // Map ALL fields to the backend's expected BackendSRSData shape (Fix 2)
      const backendSrs: any = {
        orgName: srsData.summary?.organizationName || (srsData as any).orgName || 'Organisation',
        subjectTypes: (srsData as any).subjectTypes || [{ name: 'Individual', type: 'Person' }],
        programs: (srsData.programs || []).map((p: any) =>
          typeof p === 'string' ? { name: p } : { name: p.name, colour: p.colour || p.color }
        ),
        encounterTypes: (srsData as any).encounterTypes || srsData.w3h?.map((w: any) => w.what) || [],
        forms: (srsData.forms || []).map((f: any) => ({
          name: f.name,
          formType: f.formType || 'Encounter',
          programName: f.programName || null,
          encounterTypeName: f.encounterTypeName || null,
          subjectTypeName: f.subjectTypeName || null,
          groups: f.groups || (f.fields
            ? Object.entries(
                (f.fields as any[]).reduce<Record<string, any[]>>((acc, field) => {
                  const page = field.pageName || 'Default';
                  if (!acc[page]) acc[page] = [];
                  acc[page].push(field);
                  return acc;
                }, {})
              ).map(([groupName, fields]) => ({
                name: groupName,
                fields: fields.map((field: any) => ({
                  name: field.fieldName || field.name,
                  dataType: field.dataType,
                  mandatory: field.mandatory,
                  options: field.options
                    ? (typeof field.options === 'string'
                        ? field.options.split(',').map((o: string) => o.trim()).filter(Boolean)
                        : field.options)
                    : [],
                  type: field.selectionType === 'Multi' ? 'MultiSelect' : 'SingleSelect',
                  unit: field.unit || undefined,
                  lowAbsolute: field.min ? Number(field.min) : undefined,
                  highAbsolute: field.max ? Number(field.max) : undefined,
                })),
              }))
            : []),
        })),
        groups: (srsData as any).groups || srsData.users?.map((u: any) => u.type).filter(Boolean) || ['Everyone'],
        addressLevelTypes: (srsData as any).addressLevelTypes || null,
        programEncounterMappings: (srsData as any).programEncounterMappings || null,
        generalEncounterTypes: (srsData as any).generalEncounterTypes || null,
        visitSchedules: (srsData as any).visitSchedules || null,
        eligibilityRules: (srsData as any).eligibilityRules || null,
      };

      const response = await authFetch('/api/bundle/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ srs_data: backendSrs }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Generation failed' }));
        throw new Error(err.detail || 'Bundle generation failed');
      }

      const data = await response.json();
      const newBundleId = data.bundle_id || data.id;

      if (!newBundleId) {
        // Bundle was generated immediately (no async)
        setBundleStatus('done');
        setBundleId(data.bundle_id || 'generated');
        onBundleGenerated(data.bundle_id || 'generated');
        return;
      }

      setBundleId(newBundleId);
      setBundleStatus('polling');

      // Poll for status
      pollRef.current = setInterval(async () => {
        try {
          const statusRes = await authFetch(`/api/bundle/${newBundleId}/status`);
          if (!statusRes.ok) return;
          const statusData = await statusRes.json();

          const status = statusData.status?.toLowerCase();
          if (status === 'completed' || status === 'done') {
            if (pollRef.current) clearInterval(pollRef.current);
            setBundleStatus('done');
            onBundleGenerated(newBundleId);
          } else if (status === 'failed' || status === 'error') {
            if (pollRef.current) clearInterval(pollRef.current);
            setBundleStatus('error');
            setBundleError(statusData.error || 'Bundle generation failed');
          }
        } catch {
          // Polling error, continue
        }
      }, 2000);
    } catch (err) {
      setBundleStatus('error');
      setBundleError(userFriendlyError(err));
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `Bundle generation failed: ${userFriendlyError(err)}`,
        timestamp: new Date(),
      }]);
    }
  }, [srsData, onBundleGenerated, canGenerateBundle]);

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

  // ── Keyboard Handling ─────────────────────────────────────────────────────

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(input);
      }
    },
    [input, sendMessage]
  );

  // ── Section edit toggling ─────────────────────────────────────────────────

  const toggleEdit = useCallback((section: PreviewSection) => {
    setEditingSection(prev => (prev === section ? null : section));
  }, []);

  // ── Computed counts ───────────────────────────────────────────────────────

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
  const bundleValidation = canGenerateBundle();

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="fixed inset-0 z-50 bg-white flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-white shadow-sm shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={onClose}
            className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="hidden sm:inline">Back to Chat</span>
          </button>
        </div>
        <h2 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
          <Package className="w-4 h-4 text-teal-600" />
          SRS Chat Builder
        </h2>
        <div className="flex items-center gap-2">
          {/* New SRS button */}
          <button
            onClick={handleNewSrs}
            className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-gray-600 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
            title="Start a new SRS from scratch"
          >
            <RotateCcw className="w-3 h-3" />
            <span className="hidden sm:inline">New SRS</span>
          </button>
          {/* Mobile preview toggle */}
          <button
            onClick={() => setShowPreviewMobile(prev => !prev)}
            className="sm:hidden px-2 py-1 text-xs font-medium text-teal-600 bg-teal-50 rounded-lg hover:bg-teal-100 transition-colors"
          >
            {showPreviewMobile ? 'Chat' : 'Preview'}
          </button>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-gray-600 transition-colors rounded-lg hover:bg-gray-100"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* ── Chat Panel (Left 60%) ─────────────────────────────────────── */}
        <div
          className={clsx(
            'flex flex-col border-r border-gray-200 min-w-0',
            showPreviewMobile ? 'hidden sm:flex' : 'flex',
            'w-full sm:w-[60%]'
          )}
        >
          {/* Messages */}
          <div
            ref={containerRef}
            className="flex-1 overflow-y-auto px-4 py-4 space-y-3 bg-gray-50"
          >
            {messages.map(msg => (
              <div
                key={msg.id}
                className={clsx('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}
              >
                <div
                  className={clsx(
                    'max-w-[85%] rounded-xl px-4 py-2.5 text-sm shadow-sm',
                    msg.role === 'user'
                      ? 'bg-teal-700 text-white rounded-br-sm'
                      : 'bg-white text-gray-900 border border-gray-200 rounded-bl-sm'
                  )}
                >
                  {msg.content ? (
                    <div
                      className="whitespace-pre-wrap [&_strong]:font-semibold [&_em]:italic [&_code]:px-1 [&_code]:py-0.5 [&_code]:bg-gray-100 [&_code]:rounded [&_code]:text-xs [&_code]:font-mono [&_li]:ml-4 [&_li]:list-disc"
                      dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
                    />
                  ) : (
                    <span className="text-gray-400 italic">Thinking...</span>
                  )}
                </div>
              </div>
            ))}

            {isStreaming && !assistantContentRef.current && (
              <div className="flex justify-start">
                <div className="bg-white border border-gray-200 rounded-xl px-4 py-2.5 text-sm text-gray-500 shadow-sm rounded-bl-sm">
                  <div className="flex gap-1.5 items-center">
                    <div className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-bounce [animation-delay:0ms]" />
                    <div className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-bounce [animation-delay:150ms]" />
                    <div className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-bounce [animation-delay:300ms]" />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="px-4 py-3 border-t border-gray-200 bg-white shrink-0">
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Describe your implementation needs..."
                rows={1}
                disabled={isStreaming}
                className={clsx(
                  'flex-1 resize-none rounded-xl border px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500 transition-colors',
                  isStreaming ? 'bg-gray-50 border-gray-200' : 'border-gray-300 bg-white'
                )}
                style={{ maxHeight: '120px' }}
                onInput={e => {
                  const el = e.currentTarget;
                  el.style.height = 'auto';
                  el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
                }}
              />
              <button
                onClick={() => sendMessage(input)}
                disabled={!input.trim() || isStreaming}
                className={clsx(
                  'p-2.5 rounded-xl transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500 shrink-0',
                  input.trim() && !isStreaming
                    ? 'bg-teal-700 hover:bg-teal-800 text-white'
                    : 'bg-gray-100 text-gray-300 cursor-not-allowed'
                )}
                aria-label="Send"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* ── SRS Preview Panel (Right 40%) ─────────────────────────────── */}
        <div
          className={clsx(
            'flex flex-col bg-gray-50/80 min-w-0 overflow-hidden',
            showPreviewMobile ? 'flex' : 'hidden sm:flex',
            'w-full sm:w-[40%]'
          )}
        >
          <div className="flex-1 overflow-y-auto px-3 py-4 space-y-2">
            {/* Organization */}
            <PreviewSection
              title="Organization"
              icon={Building2}
              isEmpty={!hasOrg}
              isHighlighted={highlightedSections.has('organization')}
              isEditing={editingSection === 'organization'}
              onToggleEdit={() => toggleEdit('organization')}
              editContent={
                <OrgEditor
                  summary={srsData.summary}
                  onChange={summary => setSrsData(prev => ({ ...prev, summary }))}
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
            </PreviewSection>

            {/* Subject Types / Users */}
            <PreviewSection
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
                  onChange={users => setSrsData(prev => ({ ...prev, users }))}
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
            </PreviewSection>

            {/* Programs */}
            <PreviewSection
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
                  onChange={programs => setSrsData(prev => ({ ...prev, programs }))}
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
            </PreviewSection>

            {/* Forms */}
            <PreviewSection
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
                  onChange={forms => setSrsData(prev => ({ ...prev, forms }))}
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
            </PreviewSection>

            {/* Visit Scheduling */}
            <PreviewSection
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
                  onChange={visitScheduling => setSrsData(prev => ({ ...prev, visitScheduling }))}
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
                          <td className="pr-2 py-0.5">{vs.scheduleForm || '—'}</td>
                          <td className="pr-2 py-0.5">{vs.frequency}</td>
                          <td className="py-0.5">{vs.overdueDate || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="pt-2 text-xs text-gray-400 italic">Not yet defined</p>
              )}
            </PreviewSection>

            {/* Dashboard Cards */}
            <PreviewSection
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
                  onChange={dashboardCards => setSrsData(prev => ({ ...prev, dashboardCards }))}
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
            </PreviewSection>

            {/* Permissions */}
            <PreviewSection
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
            </PreviewSection>

            {/* Progress Bar */}
            <div className="border border-gray-200 rounded-lg bg-white p-3">
              <PhaseProgressBar currentPhase={phase} />
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
                  onClick={generateBundle}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-teal-700 text-white text-sm font-medium rounded-xl hover:bg-teal-800 transition-colors"
                >
                  <Package className="w-4 h-4" />
                  Retry
                </button>
              </div>
            ) : (
              <div className="space-y-1.5">
                <button
                  onClick={generateBundle}
                  disabled={bundleStatus === 'generating' || bundleStatus === 'polling' || !bundleValidation.ok}
                  className={clsx(
                    'w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium rounded-xl transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500',
                    bundleStatus === 'generating' || bundleStatus === 'polling'
                      ? 'bg-teal-200 text-teal-700 cursor-wait'
                      : !bundleValidation.ok
                        ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                        : 'bg-teal-700 text-white hover:bg-teal-800'
                  )}
                >
                  {bundleStatus === 'generating' || bundleStatus === 'polling' ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      {bundleStatus === 'generating' ? 'Generating...' : 'Processing...'}
                    </>
                  ) : (
                    <>
                      <Package className="w-4 h-4" />
                      Generate Bundle
                    </>
                  )}
                </button>
                {!bundleValidation.ok && bundleValidation.reason && (
                  <p className="text-[11px] text-gray-400 text-center">{bundleValidation.reason}</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
