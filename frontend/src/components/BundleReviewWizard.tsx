import { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/api';
import {
  CheckCircle,
  AlertTriangle,
  XCircle,
  ChevronLeft,
  ChevronRight,
  Download,
  RefreshCw,
  Loader2,
  Users,
  ClipboardList,
  FileText,
  Shield,
  Plus,
  Trash2,
  Edit3,
  X,
} from 'lucide-react';
import clsx from 'clsx';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SubjectTypeSummary {
  name: string;
  type: string;
  uuid: string;
  forms_count: number;
}

interface ProgramSummary {
  name: string;
  uuid: string;
  encounter_types: string[];
}

interface FormMappingSummary {
  form_name: string;
  form_type: string;
  subject_type: string | null;
  program: string | null;
  encounter_type: string | null;
  field_count: number;
  coded_fields_missing_options: string[];
}

interface CodedFieldNeedingOptions {
  concept_name: string;
  form_name: string;
  current_options: string[];
}

interface ReviewSummary {
  bundle_id: string;
  subject_types: SubjectTypeSummary[];
  programs: ProgramSummary[];
  form_mappings: FormMappingSummary[];
  warnings: string[];
  errors: string[];
  coded_fields_needing_options: CodedFieldNeedingOptions[];
  changes_applied?: string[];
}

interface Fix {
  type: string;
  form_name?: string;
  subject_type?: string;
  new_form_type?: string;
  program?: string;
  encounter_type?: string;
  concept_name?: string;
  options?: string[];
  name?: string;
}

interface BundleReviewWizardProps {
  bundleId: string;
  onClose: () => void;
  onDownload?: (bundleId: string) => void;
  onToast: (type: 'success' | 'error' | 'info', message: string) => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STEPS = [
  { key: 'subjects', label: 'Subject Types & Programs', icon: Users },
  { key: 'mappings', label: 'Form Mappings', icon: ClipboardList },
  { key: 'missing', label: 'Missing Data', icon: FileText },
  { key: 'validation', label: 'Validation Summary', icon: Shield },
] as const;

const FORM_TYPES = [
  'IndividualProfile',
  'ProgramEnrolment',
  'ProgramExit',
  'ProgramEncounter',
  'ProgramEncounterCancellation',
  'Encounter',
  'IndividualEncounterCancellation',
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function BundleReviewWizard({
  bundleId,
  onClose,
  onDownload,
  onToast,
}: BundleReviewWizardProps) {
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [pendingFixes, setPendingFixes] = useState<Fix[]>([]);
  const [newBundleId, setNewBundleId] = useState<string | null>(null);

  // Inline edit state
  const [codedOptionsInputs, setCodedOptionsInputs] = useState<Record<string, string>>({});
  const [addProgramName, setAddProgramName] = useState('');
  const [addProgramSubjectType, setAddProgramSubjectType] = useState('');

  // ---------------------------------------------------------------------------
  // Data loading
  // ---------------------------------------------------------------------------

  const loadSummary = useCallback(async (bid: string) => {
    setLoading(true);
    try {
      const resp = await authFetch(`/api/bundle/review/${bid}/summary`, {
        method: 'POST',
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Failed to load summary' }));
        throw new Error(err.detail || `Status ${resp.status}`);
      }
      const data: ReviewSummary = await resp.json();
      setSummary(data);
    } catch (err) {
      onToast('error', `Failed to load review: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  }, [onToast]);

  useEffect(() => {
    loadSummary(bundleId);
  }, [bundleId, loadSummary]);

  // ---------------------------------------------------------------------------
  // Fix helpers
  // ---------------------------------------------------------------------------

  function addFix(fix: Fix) {
    setPendingFixes(prev => [...prev, fix]);
  }

  function removeFix(index: number) {
    setPendingFixes(prev => prev.filter((_, i) => i !== index));
  }

  async function applyFixes() {
    if (pendingFixes.length === 0) return;
    setApplying(true);
    try {
      const resp = await authFetch(`/api/bundle/review/${newBundleId || bundleId}/fix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fixes: pendingFixes }),
      });
      if (!resp.ok) {
        throw new Error(`Fix failed: ${resp.status}`);
      }
      const data: ReviewSummary = await resp.json();
      setSummary(data);
      setPendingFixes([]);
      onToast('success', `Applied ${data.changes_applied?.length || 0} fix(es) successfully`);
    } catch (err) {
      onToast('error', `Fix failed: ${err instanceof Error ? err.message : 'Unknown'}`);
    } finally {
      setApplying(false);
    }
  }

  async function handleRegenerate() {
    setRegenerating(true);
    try {
      // Apply any pending fixes first
      if (pendingFixes.length > 0) {
        await applyFixes();
      }

      const resp = await authFetch(`/api/bundle/review/${newBundleId || bundleId}/regenerate`, {
        method: 'POST',
      });
      if (!resp.ok) {
        throw new Error(`Regeneration failed: ${resp.status}`);
      }
      const data = await resp.json();
      setNewBundleId(data.new_bundle_id);
      onToast('success', 'Bundle regenerated with fixes applied');
      // Reload summary from new bundle
      await loadSummary(data.new_bundle_id);
    } catch (err) {
      onToast('error', `Regeneration failed: ${err instanceof Error ? err.message : 'Unknown'}`);
    } finally {
      setRegenerating(false);
    }
  }

  async function handleDownload() {
    const bid = newBundleId || bundleId;
    if (onDownload) {
      onDownload(bid);
    } else {
      // Direct download
      try {
        const resp = await authFetch(`/api/bundle/${bid}/download`);
        if (!resp.ok) throw new Error('Download failed');
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `avni-bundle-${bid.slice(0, 8)}.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        onToast('success', 'Bundle downloaded');
      } catch (err) {
        onToast('error', `Download failed: ${err instanceof Error ? err.message : 'Unknown'}`);
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const errorCount = summary?.errors.length || 0;
  const warningCount = summary?.warnings.length || 0;
  const allClear = errorCount === 0 && warningCount === 0;
  const activeBundleId = newBundleId || bundleId;

  if (loading) {
    return (
      <div className="w-full bg-white border border-gray-200 rounded-lg shadow-sm">
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-teal-600" />
          <span className="ml-3 text-gray-500">Analyzing bundle...</span>
        </div>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="w-full bg-white border border-gray-200 rounded-lg shadow-sm p-6">
        <div className="flex items-center gap-2 text-red-600">
          <XCircle className="w-5 h-5" />
          <span>Failed to load bundle review. Please try again.</span>
        </div>
        <button
          onClick={onClose}
          className="mt-4 px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
        >
          Close
        </button>
      </div>
    );
  }

  return (
    <div className="w-full bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 bg-white">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Bundle Review Wizard</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              Review and fix issues before downloading &middot; {activeBundleId.slice(0, 8)}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {errorCount > 0 && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-red-50 text-red-700 rounded-full text-xs font-medium border border-red-200">
                <XCircle className="w-3.5 h-3.5" /> {errorCount} error{errorCount !== 1 ? 's' : ''}
              </span>
            )}
            {warningCount > 0 && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-yellow-50 text-yellow-700 rounded-full text-xs font-medium border border-yellow-200">
                <AlertTriangle className="w-3.5 h-3.5" /> {warningCount} warning{warningCount !== 1 ? 's' : ''}
              </span>
            )}
            {allClear && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-green-50 text-green-700 rounded-full text-xs font-medium border border-green-200">
                <CheckCircle className="w-3.5 h-3.5" /> All clear
              </span>
            )}
            <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors" aria-label="Close">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Step navigation */}
      <div className="px-6 py-3 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center gap-1">
          {STEPS.map((s, i) => (
            <button
              key={s.key}
              onClick={() => setStep(i)}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg transition-colors',
                step === i
                  ? 'bg-teal-100 text-teal-800 border border-teal-200'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
              )}
            >
              <s.icon className="w-4 h-4" />
              <span className="hidden sm:inline">{s.label}</span>
              <span className="sm:hidden">{i + 1}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Pending fixes banner */}
      {pendingFixes.length > 0 && (
        <div className="px-6 py-2 bg-teal-50 border-b border-teal-200 flex items-center justify-between">
          <span className="text-sm text-teal-800">
            {pendingFixes.length} pending fix{pendingFixes.length !== 1 ? 'es' : ''} to apply
          </span>
          <button
            onClick={applyFixes}
            disabled={applying}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-lg transition-colors disabled:opacity-50"
          >
            {applying ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
            Apply Fixes
          </button>
        </div>
      )}

      {/* Step content */}
      <div className="px-6 py-5 min-h-[320px] max-h-[500px] overflow-y-auto">
        {/* Step 1: Subject Types & Programs */}
        {step === 0 && (
          <div className="space-y-6">
            {/* Subject Types */}
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Subject Types</h3>
              <div className="border border-gray-200 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>
                      <th className="text-left px-4 py-2.5 font-medium">Name</th>
                      <th className="text-left px-4 py-2.5 font-medium">Type</th>
                      <th className="text-center px-4 py-2.5 font-medium">Forms</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {summary.subject_types.map(st => (
                      <tr key={st.uuid} className="hover:bg-gray-50">
                        <td className="px-4 py-2.5 font-medium text-gray-900">{st.name}</td>
                        <td className="px-4 py-2.5">
                          <span className="px-2 py-0.5 text-xs bg-teal-50 text-teal-700 border border-teal-200 rounded-full">
                            {st.type}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-center text-gray-600">{st.forms_count}</td>
                      </tr>
                    ))}
                    {summary.subject_types.length === 0 && (
                      <tr><td colSpan={3} className="px-4 py-6 text-center text-gray-400">No subject types found</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Programs */}
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Programs</h3>
              <div className="border border-gray-200 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>
                      <th className="text-left px-4 py-2.5 font-medium">Program Name</th>
                      <th className="text-left px-4 py-2.5 font-medium">Encounter Types</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {summary.programs.map(prog => (
                      <tr key={prog.uuid} className="hover:bg-gray-50">
                        <td className="px-4 py-2.5 font-medium text-gray-900">{prog.name}</td>
                        <td className="px-4 py-2.5">
                          {prog.encounter_types.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {prog.encounter_types.map(et => (
                                <span key={et} className="px-2 py-0.5 text-xs bg-gray-100 text-gray-700 rounded-full">
                                  {et}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-yellow-600 text-xs flex items-center gap-1">
                              <AlertTriangle className="w-3 h-3" /> No encounters linked
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                    {summary.programs.length === 0 && (
                      <tr><td colSpan={2} className="px-4 py-6 text-center text-gray-400">No programs defined</td></tr>
                    )}
                  </tbody>
                </table>
              </div>

              {/* Add program form */}
              <div className="mt-3 flex items-center gap-2">
                <input
                  type="text"
                  value={addProgramName}
                  onChange={e => setAddProgramName(e.target.value)}
                  placeholder="New program name..."
                  className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                />
                <select
                  value={addProgramSubjectType}
                  onChange={e => setAddProgramSubjectType(e.target.value)}
                  className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-teal-500"
                >
                  <option value="">Subject type...</option>
                  {summary.subject_types.map(st => (
                    <option key={st.uuid} value={st.name}>{st.name}</option>
                  ))}
                </select>
                <button
                  onClick={() => {
                    if (addProgramName.trim()) {
                      addFix({
                        type: 'add_program',
                        name: addProgramName.trim(),
                        subject_type: addProgramSubjectType || undefined,
                      });
                      setAddProgramName('');
                      setAddProgramSubjectType('');
                    }
                  }}
                  className="flex items-center gap-1 px-3 py-2 text-sm font-medium text-teal-700 bg-teal-50 hover:bg-teal-100 border border-teal-200 rounded-lg transition-colors"
                >
                  <Plus className="w-4 h-4" /> Add
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Step 2: Form Mappings */}
        {step === 1 && (
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Form Mappings</h3>
            <div className="border border-gray-200 rounded-lg overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="text-left px-3 py-2.5 font-medium whitespace-nowrap">Form Name</th>
                    <th className="text-left px-3 py-2.5 font-medium whitespace-nowrap">Form Type</th>
                    <th className="text-left px-3 py-2.5 font-medium whitespace-nowrap">Subject Type</th>
                    <th className="text-left px-3 py-2.5 font-medium whitespace-nowrap">Program</th>
                    <th className="text-left px-3 py-2.5 font-medium whitespace-nowrap">Encounter Type</th>
                    <th className="text-center px-3 py-2.5 font-medium">Fields</th>
                    <th className="text-center px-3 py-2.5 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {summary.form_mappings.map((fm, idx) => {
                    const hasIssue = !fm.subject_type ||
                      (fm.form_type.startsWith('Program') && !fm.program) ||
                      fm.coded_fields_missing_options.length > 0;
                    return (
                      <tr
                        key={`${fm.form_name}-${idx}`}
                        className={clsx(
                          'hover:bg-gray-50',
                          hasIssue && 'bg-red-50/50'
                        )}
                      >
                        <td className="px-3 py-2.5 font-medium text-gray-900 whitespace-nowrap">
                          {fm.form_name}
                          {fm.coded_fields_missing_options.length > 0 && (
                            <span className="ml-1.5 text-xs text-yellow-600" title={`Missing options: ${fm.coded_fields_missing_options.join(', ')}`}>
                              ({fm.coded_fields_missing_options.length} coded missing)
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2.5">
                          <FormTypeSelector
                            value={fm.form_type}
                            onChange={(newType) => addFix({
                              type: 'set_form_type',
                              form_name: fm.form_name,
                              new_form_type: newType,
                            })}
                          />
                        </td>
                        <td className="px-3 py-2.5">
                          {fm.subject_type ? (
                            <SubjectTypeSelector
                              value={fm.subject_type}
                              subjectTypes={summary.subject_types.map(st => st.name)}
                              onChange={(st) => addFix({
                                type: 'set_subject_type',
                                form_name: fm.form_name,
                                subject_type: st,
                              })}
                            />
                          ) : (
                            <span className="text-red-500 text-xs flex items-center gap-1">
                              <XCircle className="w-3 h-3" /> Missing
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-gray-600 text-xs">
                          {fm.program || (
                            fm.form_type.startsWith('Program') ? (
                              <span className="text-red-500 flex items-center gap-1">
                                <XCircle className="w-3 h-3" /> Required
                              </span>
                            ) : (
                              <span className="text-gray-400">-</span>
                            )
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-gray-600 text-xs">
                          {fm.encounter_type || <span className="text-gray-400">-</span>}
                        </td>
                        <td className="px-3 py-2.5 text-center text-gray-600">{fm.field_count}</td>
                        <td className="px-3 py-2.5 text-center">
                          {hasIssue && (
                            <AlertTriangle className="w-4 h-4 text-yellow-500 mx-auto" title="Has issues" />
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Step 3: Missing Data (Coded fields) */}
        {step === 2 && (
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-3">
              Coded Fields Missing Answer Options
            </h3>
            {summary.coded_fields_needing_options.length === 0 ? (
              <div className="flex items-center gap-2 px-4 py-6 bg-green-50 border border-green-200 rounded-lg">
                <CheckCircle className="w-5 h-5 text-green-600" />
                <span className="text-sm text-green-700">All coded fields have answer options defined.</span>
              </div>
            ) : (
              <div className="space-y-3">
                {summary.coded_fields_needing_options.map((cf, idx) => (
                  <div
                    key={`${cf.concept_name}-${idx}`}
                    className="p-4 border border-yellow-200 rounded-lg bg-yellow-50/50"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <AlertTriangle className="w-4 h-4 text-yellow-600 shrink-0" />
                          <span className="font-medium text-gray-900 text-sm">{cf.concept_name}</span>
                        </div>
                        <p className="text-xs text-gray-500 mt-1 ml-6">
                          Form: {cf.form_name}
                          {cf.current_options.length > 0 && (
                            <> &middot; Current: {cf.current_options.join(', ')}</>
                          )}
                        </p>
                      </div>
                    </div>
                    <div className="mt-3 ml-6 flex items-center gap-2">
                      <input
                        type="text"
                        value={codedOptionsInputs[cf.concept_name] || ''}
                        onChange={e => setCodedOptionsInputs(prev => ({
                          ...prev,
                          [cf.concept_name]: e.target.value,
                        }))}
                        placeholder="Enter options separated by commas (e.g. Male, Female, Other)"
                        className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                      />
                      <button
                        onClick={() => {
                          const raw = codedOptionsInputs[cf.concept_name];
                          if (raw?.trim()) {
                            const opts = raw.split(',').map(s => s.trim()).filter(Boolean);
                            addFix({
                              type: 'add_coded_options',
                              concept_name: cf.concept_name,
                              options: opts,
                            });
                            setCodedOptionsInputs(prev => {
                              const next = { ...prev };
                              delete next[cf.concept_name];
                              return next;
                            });
                          }
                        }}
                        className="flex items-center gap-1 px-3 py-2 text-sm font-medium text-teal-700 bg-teal-50 hover:bg-teal-100 border border-teal-200 rounded-lg transition-colors whitespace-nowrap"
                      >
                        <Plus className="w-4 h-4" /> Add Options
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 4: Validation Summary */}
        {step === 3 && (
          <div className="space-y-4">
            {/* Summary counts */}
            <div className="grid grid-cols-3 gap-3">
              <div className="px-4 py-3 rounded-lg border border-gray-200 bg-white text-center">
                <div className="text-2xl font-bold text-gray-900">{summary.subject_types.length}</div>
                <div className="text-xs text-gray-500 mt-0.5">Subject Types</div>
              </div>
              <div className="px-4 py-3 rounded-lg border border-gray-200 bg-white text-center">
                <div className="text-2xl font-bold text-gray-900">{summary.programs.length}</div>
                <div className="text-xs text-gray-500 mt-0.5">Programs</div>
              </div>
              <div className="px-4 py-3 rounded-lg border border-gray-200 bg-white text-center">
                <div className="text-2xl font-bold text-gray-900">{summary.form_mappings.length}</div>
                <div className="text-xs text-gray-500 mt-0.5">Form Mappings</div>
              </div>
            </div>

            {/* Validation checks */}
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-gray-900">Validation Checks</h3>

              <ValidationCheck
                passed={summary.subject_types.length > 0}
                label="At least one subject type defined"
              />
              <ValidationCheck
                passed={summary.form_mappings.every(fm => fm.subject_type !== null)}
                label="All forms have a subject type assigned"
              />
              <ValidationCheck
                passed={summary.form_mappings.filter(fm => fm.form_type.startsWith('Program')).every(fm => fm.program)}
                label="All program forms have a program assigned"
              />
              <ValidationCheck
                passed={summary.coded_fields_needing_options.length === 0}
                label="All coded fields have answer options"
              />
              <ValidationCheck
                passed={summary.programs.every(p => p.encounter_types.length > 0)}
                label="All programs have encounter types linked"
              />
              <ValidationCheck
                passed={summary.errors.length === 0}
                label="No critical errors detected"
              />
            </div>

            {/* Errors */}
            {summary.errors.length > 0 && (
              <div className="space-y-1.5">
                <h4 className="text-xs font-semibold text-red-700 uppercase tracking-wide">Errors</h4>
                {summary.errors.map((err, i) => (
                  <div key={i} className="flex items-start gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg">
                    <XCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                    <span className="text-sm text-red-700">{err}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Warnings */}
            {summary.warnings.length > 0 && (
              <div className="space-y-1.5">
                <h4 className="text-xs font-semibold text-yellow-700 uppercase tracking-wide">Warnings</h4>
                {summary.warnings.map((warn, i) => (
                  <div key={i} className="flex items-start gap-2 px-3 py-2 bg-yellow-50 border border-yellow-200 rounded-lg">
                    <AlertTriangle className="w-4 h-4 text-yellow-500 shrink-0 mt-0.5" />
                    <span className="text-sm text-yellow-700">{warn}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Applied changes */}
            {summary.changes_applied && summary.changes_applied.length > 0 && (
              <div className="space-y-1.5">
                <h4 className="text-xs font-semibold text-green-700 uppercase tracking-wide">Fixes Applied</h4>
                {summary.changes_applied.map((change, i) => (
                  <div key={i} className="flex items-start gap-2 px-3 py-2 bg-green-50 border border-green-200 rounded-lg">
                    <CheckCircle className="w-4 h-4 text-green-500 shrink-0 mt-0.5" />
                    <span className="text-sm text-green-700">{change}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Pending fixes list */}
      {pendingFixes.length > 0 && (
        <div className="px-6 py-3 border-t border-gray-200 bg-gray-50">
          <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-2">
            Pending Fixes ({pendingFixes.length})
          </h4>
          <div className="space-y-1 max-h-24 overflow-y-auto">
            {pendingFixes.map((fix, i) => (
              <div key={i} className="flex items-center justify-between text-xs text-gray-700 bg-white border border-gray-200 rounded-md px-3 py-1.5">
                <span>
                  <span className="font-medium text-teal-700">{fix.type}</span>
                  {fix.form_name && <> on "{fix.form_name}"</>}
                  {fix.concept_name && <> for "{fix.concept_name}"</>}
                  {fix.name && <> "{fix.name}"</>}
                  {fix.options && <> ({fix.options.join(', ')})</>}
                  {fix.subject_type && <> &rarr; {fix.subject_type}</>}
                  {fix.new_form_type && <> &rarr; {fix.new_form_type}</>}
                </span>
                <button onClick={() => removeFix(i)} className="p-0.5 text-gray-400 hover:text-red-500 transition-colors">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Footer actions */}
      <div className="px-6 py-4 border-t border-gray-200 bg-white flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setStep(Math.max(0, step - 1))}
            disabled={step === 0}
            className="flex items-center gap-1 px-3 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <ChevronLeft className="w-4 h-4" /> Back
          </button>
          <button
            onClick={() => setStep(Math.min(STEPS.length - 1, step + 1))}
            disabled={step === STEPS.length - 1}
            className="flex items-center gap-1 px-3 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleDownload}
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 rounded-lg transition-colors"
          >
            <Download className="w-4 h-4" />
            Download As-Is
          </button>
          <button
            onClick={handleRegenerate}
            disabled={regenerating || (pendingFixes.length === 0 && !summary.changes_applied?.length)}
            className={clsx(
              'flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2',
              regenerating || (pendingFixes.length === 0 && !summary.changes_applied?.length)
                ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                : 'bg-teal-700 hover:bg-teal-800 text-white'
            )}
          >
            {regenerating ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Regenerating...</>
            ) : (
              <><RefreshCw className="w-4 h-4" /> Regenerate Bundle</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ValidationCheck({ passed, label }: { passed: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white border border-gray-200">
      {passed ? (
        <CheckCircle className="w-4 h-4 text-green-500 shrink-0" />
      ) : (
        <XCircle className="w-4 h-4 text-red-500 shrink-0" />
      )}
      <span className={clsx('text-sm', passed ? 'text-gray-700' : 'text-red-700')}>{label}</span>
    </div>
  );
}

function FormTypeSelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (newType: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="px-2 py-1 text-xs border border-gray-200 rounded-md bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-teal-500 cursor-pointer"
    >
      {FORM_TYPES.map(ft => (
        <option key={ft} value={ft}>{ft}</option>
      ))}
    </select>
  );
}

function SubjectTypeSelector({
  value,
  subjectTypes,
  onChange,
}: {
  value: string;
  subjectTypes: string[];
  onChange: (st: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="px-2 py-1 text-xs border border-gray-200 rounded-md bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-teal-500 cursor-pointer"
    >
      {subjectTypes.map(st => (
        <option key={st} value={st}>{st}</option>
      ))}
    </select>
  );
}
