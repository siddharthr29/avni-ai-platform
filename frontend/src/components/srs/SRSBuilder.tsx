import { useState, useCallback, useRef } from 'react';
import { authFetch, processDocument } from '../../services/api';
import {
  ArrowLeft,
  MessageSquare,
  Download,
  Upload,
  Package,
  FileSpreadsheet,
  FileUp,
  FileText,
  Sparkles,
  AlertCircle,
  CheckCircle2,
  Loader2,
} from 'lucide-react';
import clsx from 'clsx';
import type { SRSData, SRSTabName, ProcessDocumentResult, BackendSRSForm, FormFieldDataType } from '../../types/index.ts';
import { SRS_TEMPLATES, createDefaultSRSData } from '../../data/srs-templates.ts';
import { ProgramSummary } from './ProgramSummary.tsx';
import { ProgramDetail } from './ProgramDetail.tsx';
import { UserPersona } from './UserPersona.tsx';
import { W3HTab } from './W3HTab.tsx';
import { FormsTab } from './FormsTab.tsx';
import { VisitScheduling } from './VisitScheduling.tsx';
import { DashboardCards } from './DashboardCards.tsx';
import { Permissions } from './Permissions.tsx';
import { SRSChat } from './SRSChat.tsx';

interface SRSBuilderProps {
  onClose: () => void;
  onGenerateBundle: (srsData: SRSData) => void;
  initialData?: SRSData;
  orgName?: string;
  sector?: string;
}

interface TabDef {
  key: SRSTabName;
  label: string;
  shortLabel: string;
}

const TABS: TabDef[] = [
  { key: 'programs', label: 'Programs', shortLabel: 'Programs' },
  { key: 'forms', label: 'Forms', shortLabel: 'Forms' },
  { key: 'w3h', label: 'W3H', shortLabel: 'W3H' },
  { key: 'visitScheduling', label: 'Visits', shortLabel: 'Visits' },
  { key: 'permissions', label: 'Permissions', shortLabel: 'Permissions' },
  { key: 'summary', label: 'Summary', shortLabel: 'Summary' },
  { key: 'users', label: 'User Personas', shortLabel: 'Users' },
  { key: 'dashboardCards', label: 'Dashboard', shortLabel: 'Dashboard' },
];

function getValidationErrors(srsData: SRSData): string[] {
  const errors: string[] = [];
  if (!srsData.summary.organizationName) errors.push('Organization name is required');
  if (srsData.programs.length === 0) errors.push('At least one program is required');
  if (srsData.programs.some(p => !p.name)) errors.push('All programs must have a name');
  if (srsData.forms.length === 0) errors.push('At least one form is required');
  if (srsData.forms.some(f => !f.name)) errors.push('All forms must have a name');
  if (srsData.forms.some(f => f.fields.length === 0)) errors.push('All forms must have at least one field');
  if (srsData.users.length === 0) errors.push('At least one user persona is required');
  return errors;
}

export function SRSBuilder({ onClose, onGenerateBundle, initialData, orgName, sector }: SRSBuilderProps) {
  const [srsData, setSrsData] = useState<SRSData>(initialData ?? createDefaultSRSData());
  const [activeTab, setActiveTab] = useState<SRSTabName>('programs');
  const [showChat, setShowChat] = useState(true);
  const [showTemplateSelector, setShowTemplateSelector] = useState(!initialData);
  const [isAutoFilling, setIsAutoFilling] = useState(false);
  const [xlsxError, setXlsxError] = useState<string | null>(null);
  const [isUploadingXlsx, setIsUploadingXlsx] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Document extractor state
  const [isProcessingDoc, setIsProcessingDoc] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  const [docExtractionSummary, setDocExtractionSummary] = useState<string | null>(null);
  const [autoFilledFields, setAutoFilledFields] = useState<Set<string>>(new Set());
  const docFileInputRef = useRef<HTMLInputElement>(null);

  const validationErrors = getValidationErrors(srsData);

  const handleSelectTemplate = useCallback((templateData: SRSData) => {
    setSrsData(JSON.parse(JSON.stringify(templateData)) as SRSData);
    setShowTemplateSelector(false);
  }, []);

  /**
   * Map backend SRSData (from /document/process) to frontend SRSData shape.
   * The backend uses a different schema (groups inside forms, programs as objects, etc.)
   */
  const mapBackendToFrontendSRS = useCallback((result: ProcessDocumentResult): { data: SRSData; summary: string } => {
    const backend = result.srs_data;
    const filled = new Set<string>();

    const updated: SRSData = { ...createDefaultSRSData() };

    // Map org name
    if (backend.orgName && backend.orgName !== 'Organisation') {
      updated.summary = { ...updated.summary, organizationName: backend.orgName };
      filled.add('summary.organizationName');
    }

    // Map programs
    if (backend.programs && backend.programs.length > 0) {
      updated.programs = backend.programs.map((p) => ({
        id: crypto.randomUUID(),
        name: typeof p === 'string' ? p : (p.name || ''),
        objective: '',
        eligibility: '',
        entryPoint: '',
        exitCriteria: '',
        totalBeneficiaries: 0,
        successIndicators: '',
        forms: [],
        reportsNeeded: '',
      }));
      filled.add('programs');
    }

    // Map forms (backend has groups→fields, frontend has flat fields with pageName)
    if (backend.forms && backend.forms.length > 0) {
      updated.forms = backend.forms.map((form: BackendSRSForm) => ({
        id: crypto.randomUUID(),
        name: form.name || '',
        fields: (form.groups || []).flatMap((group) =>
          (group.fields || []).map((field) => ({
            id: crypto.randomUUID(),
            pageName: group.name || 'Default',
            fieldName: field.name || '',
            dataType: (field.dataType || 'Text') as FormFieldDataType,
            mandatory: field.mandatory ?? false,
            userOrSystem: 'User Enter' as const,
            options: Array.isArray(field.options) ? field.options.join(', ') : '',
            selectionType: (field.type === 'MultiSelect' ? 'Multi' : 'Single') as 'Single' | 'Multi',
            unit: field.unit || '',
            min: field.lowAbsolute != null ? String(field.lowAbsolute) : '',
            max: field.highAbsolute != null ? String(field.highAbsolute) : '',
            skipLogic: '',
          }))
        ),
      }));
      filled.add('forms');
    }

    // Map user groups
    if (backend.groups && backend.groups.length > 0) {
      updated.users = backend.groups.map((g) => ({
        id: crypto.randomUUID(),
        type: typeof g === 'string' ? g : '',
        description: '',
        count: 0,
      }));
      filled.add('users');
    }

    // Count extracted items for summary
    const programCount = updated.programs.length;
    const formCount = updated.forms.length;
    const fieldCount = updated.forms.reduce((sum, f) => sum + f.fields.length, 0);
    const clarificationCount = result.clarifications?.length ?? 0;

    let summaryMsg = `Extracted ${programCount} program${programCount !== 1 ? 's' : ''}, ${formCount} form${formCount !== 1 ? 's' : ''}, ${fieldCount} field${fieldCount !== 1 ? 's' : ''}`;
    if (clarificationCount > 0) {
      summaryMsg += ` (${clarificationCount} clarification${clarificationCount !== 1 ? 's' : ''} needed)`;
    }

    return { data: updated, summary: summaryMsg };
  }, []);

  const handleDocumentUpload = useCallback(async (file: File) => {
    setIsProcessingDoc(true);
    setDocError(null);
    setDocExtractionSummary(null);
    try {
      const result = await processDocument(file, orgName || srsData.summary.organizationName);
      const { data, summary } = mapBackendToFrontendSRS(result);

      setSrsData(data);
      setDocExtractionSummary(summary);
      setAutoFilledFields(new Set(['programs', 'forms', 'users', 'summary.organizationName']));
      setShowTemplateSelector(false);

      // Clear auto-fill highlight after 10 seconds
      setTimeout(() => setAutoFilledFields(new Set()), 10000);
    } catch (err) {
      setDocError((err as Error).message);
    } finally {
      setIsProcessingDoc(false);
    }
  }, [orgName, srsData.summary.organizationName, mapBackendToFrontendSRS]);

  const handleDocFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleDocumentUpload(file);
    // Reset input so the same file can be re-selected
    if (e.target) e.target.value = '';
  }, [handleDocumentUpload]);

  const handleDocUploadClick = useCallback(() => {
    docFileInputRef.current?.click();
  }, []);

  const handleAutoFill = useCallback(async () => {
    setIsAutoFilling(true);
    try {
      const response = await authFetch('/api/bundle/ai-autofill', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tab: activeTab,
          current_data: srsData[activeTab as keyof SRSData],
          context: `Organization: ${srsData.summary.organizationName || orgName || 'Unknown'}. Sector: ${sector || 'General'}. Programs: ${srsData.programs.map(p => p.name).join(', ') || 'None defined yet'}.`,
        }),
      });
      if (response.ok) {
        const data = await response.json();
        if (data.suggestions) {
          setSrsData(prev => ({
            ...prev,
            [activeTab]: Array.isArray(prev[activeTab as keyof SRSData])
              ? data.suggestions
              : { ...prev[activeTab as keyof SRSData] as Record<string, unknown>, ...data.suggestions },
          }));
        }
      }
    } catch {
      // Auto-fill failed silently
    } finally {
      setIsAutoFilling(false);
    }
  }, [activeTab, srsData, orgName, sector]);

  const processFile = useCallback(async (file: File) => {
    setIsUploadingXlsx(true);
    setXlsxError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await authFetch('/api/bundle/parse-excel', {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Upload failed' }));
        throw new Error(err.detail || `Upload failed: ${response.status}`);
      }
      const data = await response.json();
      if (data.parsed_srs) {
        const parsed = data.parsed_srs;
        setSrsData(prev => {
          const updated = { ...prev };
          if (parsed.orgName) {
            updated.summary = { ...updated.summary, organizationName: parsed.orgName };
          }
          if (parsed.forms && Array.isArray(parsed.forms)) {
            updated.forms = parsed.forms.map((f: { name: string; groups?: { name: string; fields?: { name: string; dataType?: string; mandatory?: boolean; options?: string[]; type?: string; unit?: string; lowAbsolute?: number; highAbsolute?: number }[] }[] }, idx: number) => ({
              id: crypto.randomUUID(),
              name: f.name || `Form ${idx + 1}`,
              fields: (f.groups || []).flatMap((g: { name: string; fields?: { name: string; dataType?: string; mandatory?: boolean; options?: string[]; type?: string; unit?: string; lowAbsolute?: number; highAbsolute?: number }[] }) =>
                (g.fields || []).map((field: { name: string; dataType?: string; mandatory?: boolean; options?: string[]; type?: string; unit?: string; lowAbsolute?: number; highAbsolute?: number }) => ({
                  id: crypto.randomUUID(),
                  pageName: g.name || 'Default',
                  fieldName: field.name || '',
                  dataType: (field.dataType || 'Text') as import('../../types/index.ts').FormFieldDataType,
                  mandatory: field.mandatory ?? false,
                  userOrSystem: 'User Enter' as const,
                  options: Array.isArray(field.options) ? field.options.join(', ') : '',
                  selectionType: (field.type === 'MultiSelect' ? 'Multi' : 'Single') as 'Single' | 'Multi',
                  unit: field.unit || '',
                  min: field.lowAbsolute != null ? String(field.lowAbsolute) : '',
                  max: field.highAbsolute != null ? String(field.highAbsolute) : '',
                  skipLogic: '',
                }))
              ),
            }));
          }
          if (parsed.programs && Array.isArray(parsed.programs)) {
            updated.programs = parsed.programs.map((p: { name: string } | string) => ({
              id: crypto.randomUUID(),
              name: typeof p === 'string' ? p : p.name || '',
              objective: '',
              eligibility: '',
              entryPoint: '',
              exitCriteria: '',
              totalBeneficiaries: 0,
              successIndicators: '',
              forms: [],
              reportsNeeded: '',
            }));
          }
          if (parsed.groups && Array.isArray(parsed.groups)) {
            updated.users = parsed.groups.map((g: string) => ({
              id: crypto.randomUUID(),
              type: g,
              description: '',
              count: 0,
            }));
          }
          return updated;
        });
        setShowTemplateSelector(false);
      }
    } catch (err) {
      setXlsxError((err as Error).message);
    } finally {
      setIsUploadingXlsx(false);
    }
  }, []);

  const handleImportXlsx = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) processFile(file);
  }, [processFile]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const name = file.name.toLowerCase();
    if (name.endsWith('.xlsx') || name.endsWith('.xls') || name.endsWith('.csv')) {
      processFile(file);
    } else if (name.endsWith('.pdf') || name.endsWith('.txt') || name.endsWith('.md') || name.endsWith('.docx')) {
      handleDocumentUpload(file);
    } else {
      setXlsxError('Supported formats: PDF, Excel (.xlsx/.xls/.csv), Text (.txt/.md)');
    }
  }, [processFile, handleDocumentUpload]);

  const handleExportJSON = useCallback(() => {
    const blob = new Blob([JSON.stringify(srsData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `srs-${srsData.summary.organizationName || 'avni'}-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [srsData]);

  const handleImportJSON = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const imported = JSON.parse(reader.result as string) as SRSData;
          setSrsData(imported);
        } catch {
          // Invalid JSON - ignore silently
        }
      };
      reader.readAsText(file);
    };
    input.click();
  }, []);

  const handleGenerateBundle = useCallback(() => {
    onGenerateBundle(srsData);
  }, [srsData, onGenerateBundle]);

  // Hidden file inputs
  const hiddenFileInput = (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept=".xlsx,.xls,.csv"
        onChange={handleFileInputChange}
        className="hidden"
      />
      <input
        ref={docFileInputRef}
        type="file"
        accept=".pdf,.txt,.md,.xlsx,.xls"
        onChange={handleDocFileInputChange}
        className="hidden"
      />
    </>
  );

  // Template selector overlay
  if (showTemplateSelector) {
    return (
      <div className="fixed inset-0 z-50 bg-white flex flex-col">
        {hiddenFileInput}
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-white shadow-sm">
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Chat
            </button>
          </div>
          <h2 className="text-base font-semibold text-gray-900">SRS Builder</h2>
          <div className="text-sm text-gray-500">
            {orgName && sector && (
              <span className="px-3 py-1 bg-gray-50 border border-gray-200 rounded-full text-xs text-gray-600">
                Org: {orgName} | {sector}
              </span>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {/* Upload Specification Document — prominent section */}
          <div className="max-w-4xl mx-auto mb-8">
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={isProcessingDoc ? undefined : handleDocUploadClick}
              className={clsx(
                'border-2 rounded-xl p-8 text-center transition-all',
                isProcessingDoc
                  ? 'border-teal-400 bg-teal-50 cursor-wait'
                  : isDragOver
                    ? 'border-teal-500 bg-teal-50 cursor-pointer'
                    : 'border-dashed border-teal-300 bg-gradient-to-b from-teal-50/60 to-white hover:border-teal-400 hover:bg-teal-50/80 cursor-pointer'
              )}
            >
              {isProcessingDoc ? (
                <div className="flex flex-col items-center gap-3">
                  <Loader2 className="w-10 h-10 text-teal-600 animate-spin" />
                  <p className="text-sm font-medium text-teal-700">
                    Extracting requirements from your document...
                  </p>
                  <p className="text-xs text-teal-600">
                    This may take 30-60 seconds for complex documents
                  </p>
                </div>
              ) : (
                <>
                  <FileText className={clsx('w-10 h-10 mx-auto mb-3', isDragOver ? 'text-teal-600' : 'text-teal-500')} />
                  <p className="text-base font-semibold text-gray-800 mb-1">
                    Upload Specification Document
                  </p>
                  <p className="text-sm text-gray-500 mb-3">
                    Upload your project document and AI will auto-populate the SRS Builder
                  </p>
                  <div className="flex items-center justify-center gap-2">
                    <span className="px-2.5 py-1 bg-white border border-teal-200 rounded-md text-xs font-medium text-teal-700">.pdf</span>
                    <span className="px-2.5 py-1 bg-white border border-teal-200 rounded-md text-xs font-medium text-teal-700">.xlsx</span>
                    <span className="px-2.5 py-1 bg-white border border-gray-200 rounded-md text-xs text-gray-500">.txt</span>
                    <span className="px-2.5 py-1 bg-white border border-gray-200 rounded-md text-xs text-gray-500">.md</span>
                  </div>
                </>
              )}

              {docExtractionSummary && (
                <div className="mt-4 flex items-center justify-center gap-2 text-sm text-teal-700 bg-teal-100 rounded-lg px-4 py-2">
                  <CheckCircle2 className="w-4 h-4 text-teal-600 shrink-0" />
                  {docExtractionSummary}
                </div>
              )}

              {docError && (
                <p className="mt-3 text-xs text-red-600 flex items-center justify-center gap-1">
                  <AlertCircle className="w-3 h-3" />
                  {docError}
                </p>
              )}
              {xlsxError && (
                <p className="mt-3 text-xs text-red-600 flex items-center justify-center gap-1">
                  <AlertCircle className="w-3 h-3" />
                  {xlsxError}
                </p>
              )}
            </div>
          </div>

          {/* Excel-only drag-and-drop (smaller, secondary) */}
          <div className="max-w-4xl mx-auto mb-8">
            <p className="text-xs text-gray-400 text-center mb-2">Or import an Avni SRS Excel file directly</p>
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={handleImportXlsx}
              className={clsx(
                'border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-all',
                isDragOver
                  ? 'border-teal-500 bg-teal-50'
                  : 'border-gray-200 bg-gray-50/50 hover:border-gray-300 hover:bg-gray-50'
              )}
            >
              <div className="flex items-center justify-center gap-2">
                <FileSpreadsheet className={clsx('w-5 h-5', isDragOver ? 'text-teal-600' : 'text-gray-400')} />
                <span className="text-sm text-gray-500">
                  {isUploadingXlsx ? 'Parsing Excel file...' : 'Drag SRS Excel here or click to browse'}
                </span>
                <div className="flex items-center gap-1">
                  <span className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-[10px] text-gray-400">.xlsx</span>
                  <span className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-[10px] text-gray-400">.csv</span>
                </div>
              </div>
            </div>
          </div>

          {/* Canonical SRS Template Download */}
          <div className="max-w-4xl mx-auto mb-8">
            <div className="border border-blue-200 bg-blue-50/50 rounded-xl p-5">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center shrink-0">
                  <Download className="w-5 h-5 text-blue-600" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-gray-900 mb-1">
                    Download SRS Template (Recommended)
                  </h3>
                  <p className="text-xs text-gray-600 mb-3">
                    Our canonical template maps 1:1 to Avni's data model. Fill it in and upload for 100% correct bundles with rules, skip logic, and visit schedules — no AI guessing needed.
                  </p>
                  <div className="flex items-center gap-2">
                    <a
                      href="/api/bundle/srs-template?format=xlsx"
                      download
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700 transition-colors"
                    >
                      <Download className="w-3.5 h-3.5" />
                      Download XLSX
                    </a>
                    <a
                      href="/api/bundle/srs-template?format=csv"
                      download
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white text-gray-700 text-xs font-medium rounded-lg border border-gray-300 hover:bg-gray-50 transition-colors"
                    >
                      <Download className="w-3.5 h-3.5" />
                      Download CSV
                    </a>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Template cards */}
          <div className="max-w-4xl mx-auto">
            <h3 className="text-sm font-medium text-gray-700 mb-3">Or start from a template</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {SRS_TEMPLATES.map(template => (
                <button
                  key={template.name}
                  onClick={() => handleSelectTemplate(template.data)}
                  className="text-left p-5 border border-gray-200 rounded-xl bg-white hover:border-teal-300 hover:shadow-sm transition-all focus:outline-none focus:ring-2 focus:ring-teal-500"
                >
                  <div className="w-10 h-10 bg-teal-50 rounded-lg flex items-center justify-center mb-3">
                    <FileSpreadsheet className="w-5 h-5 text-teal-600" />
                  </div>
                  <h3 className="text-sm font-semibold text-gray-900 mb-1">{template.name}</h3>
                  <p className="text-xs text-gray-500 leading-relaxed">{template.description}</p>
                  {template.data.programs.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1">
                      {template.data.programs.slice(0, 3).map(p => (
                        <span
                          key={p.id}
                          className="inline-block px-2 py-0.5 bg-gray-100 text-gray-600 text-[10px] rounded-md"
                        >
                          {p.name}
                        </span>
                      ))}
                    </div>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 bg-white flex flex-col">
      {hiddenFileInput}

      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-white shadow-sm shrink-0">
        <button
          onClick={onClose}
          className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="hidden sm:inline">Back to Chat</span>
        </button>

        <h2 className="text-base font-semibold text-gray-900">SRS Builder</h2>

        <div className="flex items-center gap-2">
          {orgName && sector && (
            <span className="hidden md:inline-flex px-3 py-1 bg-gray-50 border border-gray-200 rounded-full text-xs text-gray-600">
              Org: {orgName} | {sector}
            </span>
          )}
          <button
            onClick={() => setShowChat(prev => !prev)}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500',
              showChat
                ? 'bg-teal-50 text-teal-700 border border-teal-200'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            )}
          >
            <MessageSquare className="w-4 h-4" />
            <span className="hidden sm:inline">AI Chat</span>
          </button>
        </div>
      </div>

      {/* Tab navigation */}
      <div className="border-b border-gray-200 bg-white shrink-0 overflow-x-auto">
        <div className="flex px-4 gap-0">
          {TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={clsx(
                'px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors focus:outline-none',
                activeTab === tab.key
                  ? 'border-teal-600 text-teal-700'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              )}
            >
              <span className="hidden md:inline">{tab.label}</span>
              <span className="md:hidden">{tab.shortLabel}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 flex min-h-0">
        {/* Editor Panel */}
        <div
          className={clsx(
            'flex-1 flex flex-col min-w-0',
            showChat ? 'lg:w-[60%]' : 'w-full'
          )}
        >
          {/* Document / Excel upload area (collapsible at top of editor) */}
          <div className="px-4 md:px-6 pt-4">
            {/* Document extraction summary toast */}
            {docExtractionSummary && (
              <div className="flex items-center gap-2 mb-3 px-3 py-2 bg-teal-50 border border-teal-200 rounded-lg text-sm text-teal-700">
                <CheckCircle2 className="w-4 h-4 text-teal-600 shrink-0" />
                <span className="flex-1">{docExtractionSummary}</span>
                <button
                  onClick={() => setDocExtractionSummary(null)}
                  className="text-teal-500 hover:text-teal-700 text-xs font-medium"
                >
                  Dismiss
                </button>
              </div>
            )}

            {/* Processing indicator */}
            {isProcessingDoc && (
              <div className="flex items-center gap-3 mb-3 px-4 py-3 bg-teal-50 border border-teal-200 rounded-lg">
                <Loader2 className="w-5 h-5 text-teal-600 animate-spin shrink-0" />
                <div>
                  <p className="text-sm font-medium text-teal-700">Extracting requirements from your document...</p>
                  <p className="text-xs text-teal-600 mt-0.5">This may take 30-60 seconds</p>
                </div>
              </div>
            )}

            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={isProcessingDoc ? undefined : handleDocUploadClick}
              className={clsx(
                'border-2 border-dashed rounded-lg p-4 text-center transition-all mb-4',
                isProcessingDoc
                  ? 'border-teal-300 bg-teal-50/50 cursor-wait'
                  : isDragOver
                    ? 'border-teal-500 bg-teal-100 cursor-pointer'
                    : 'border-gray-300 bg-gray-50 hover:border-teal-400 hover:bg-teal-50/50 cursor-pointer'
              )}
            >
              <div className="flex items-center justify-center gap-3">
                {isProcessingDoc ? (
                  <Loader2 className="w-5 h-5 text-teal-600 animate-spin" />
                ) : (
                  <FileText className={clsx('w-5 h-5', isDragOver ? 'text-teal-600' : 'text-gray-400')} />
                )}
                <span className="text-sm text-gray-600">
                  {isProcessingDoc
                    ? 'Extracting requirements...'
                    : isUploadingXlsx
                      ? 'Parsing...'
                      : 'Drop a spec document here or click to upload (PDF, Excel, text)'
                  }
                </span>
                <div className="flex items-center gap-1">
                  <span className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-[10px] text-gray-400">.pdf</span>
                  <span className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-[10px] text-gray-400">.xlsx</span>
                  <span className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-[10px] text-gray-400">.txt</span>
                </div>
              </div>
              {(xlsxError || docError) && (
                <p className="mt-2 text-xs text-red-600 flex items-center justify-center gap-1">
                  <AlertCircle className="w-3 h-3" />
                  {docError || xlsxError}
                </p>
              )}
            </div>
          </div>

          <div className="flex-1 px-4 md:px-6 pb-4 overflow-y-auto">
            {activeTab === 'summary' && (
              <ProgramSummary
                data={srsData.summary}
                onChange={summary => setSrsData(prev => ({ ...prev, summary }))}
              />
            )}
            {activeTab === 'programs' && (
              <ProgramDetail
                data={srsData.programs}
                onChange={programs => setSrsData(prev => ({ ...prev, programs }))}
              />
            )}
            {activeTab === 'users' && (
              <UserPersona
                data={srsData.users}
                onChange={users => setSrsData(prev => ({ ...prev, users }))}
              />
            )}
            {activeTab === 'w3h' && (
              <W3HTab
                data={srsData.w3h}
                users={srsData.users}
                onChange={w3h => setSrsData(prev => ({ ...prev, w3h }))}
              />
            )}
            {activeTab === 'forms' && (
              <FormsTab
                data={srsData.forms}
                onChange={forms => setSrsData(prev => ({ ...prev, forms }))}
              />
            )}
            {activeTab === 'visitScheduling' && (
              <VisitScheduling
                data={srsData.visitScheduling}
                forms={srsData.forms}
                users={srsData.users}
                onChange={visitScheduling => setSrsData(prev => ({ ...prev, visitScheduling }))}
              />
            )}
            {activeTab === 'dashboardCards' && (
              <DashboardCards
                data={srsData.dashboardCards}
                users={srsData.users}
                onChange={dashboardCards => setSrsData(prev => ({ ...prev, dashboardCards }))}
              />
            )}
            {activeTab === 'permissions' && (
              <Permissions
                data={srsData.permissions}
                forms={srsData.forms}
                users={srsData.users}
                onChange={permissions => setSrsData(prev => ({ ...prev, permissions }))}
              />
            )}
          </div>
        </div>

        {/* AI Chat Panel */}
        {showChat && (
          <div className="hidden lg:flex w-[40%] max-w-[480px] border-l border-gray-200 flex-col">
            <SRSChat
              currentTab={activeTab}
              srsData={srsData}
              onAutoFill={handleAutoFill}
              isAutoFilling={isAutoFilling}
              orgName={orgName || srsData.summary.organizationName}
              sector={sector}
            />
          </div>
        )}
      </div>

      {/* Bottom Action Bar - Generate Bundle */}
      <div className="border-t border-gray-200 bg-white px-4 py-3 shrink-0">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={handleDocUploadClick}
              disabled={isProcessingDoc}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-teal-700 bg-teal-50 border border-teal-200 hover:bg-teal-100 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500"
            >
              {isProcessingDoc ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
              {isProcessingDoc ? 'Extracting...' : 'Upload Spec'}
            </button>
            <button
              onClick={handleImportXlsx}
              disabled={isUploadingXlsx}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500"
            >
              <FileUp className="w-4 h-4" />
              {isUploadingXlsx ? 'Parsing...' : 'Upload XLSX'}
            </button>
            <button
              onClick={handleImportJSON}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500"
            >
              <Upload className="w-4 h-4" />
              Import JSON
            </button>
            <button
              onClick={handleExportJSON}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500"
            >
              <Download className="w-4 h-4" />
              Download SRS
            </button>
          </div>

          <div className="flex items-center gap-2">
            {/* AI Auto-Fill on mobile */}
            <button
              onClick={handleAutoFill}
              disabled={isAutoFilling}
              className="lg:hidden flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-teal-700 bg-teal-50 hover:bg-teal-100 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500"
            >
              <Sparkles className="w-4 h-4" />
              AI Auto-Fill
            </button>
            <button
              onClick={handleGenerateBundle}
              disabled={validationErrors.length > 0}
              className={clsx(
                'relative flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2',
                'w-full sm:w-auto',
                validationErrors.length > 0
                  ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                  : 'bg-teal-700 hover:bg-teal-800 text-white'
              )}
            >
              <Package className="w-4 h-4" />
              Generate Bundle
              {validationErrors.length > 0 && (
                <span className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                  {validationErrors.length}
                </span>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Fixed bottom bar on mobile for Generate Bundle */}
      <div className="sm:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 px-4 py-3 z-50">
        <button
          onClick={handleGenerateBundle}
          disabled={validationErrors.length > 0}
          className={clsx(
            'w-full flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium rounded-lg transition-colors',
            validationErrors.length > 0
              ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
              : 'bg-teal-700 hover:bg-teal-800 text-white'
          )}
        >
          <Package className="w-4 h-4" />
          Generate Bundle
          {validationErrors.length > 0 && (
            <span className="ml-1 px-1.5 py-0.5 bg-red-500 text-white text-[10px] font-bold rounded-full">
              {validationErrors.length} errors
            </span>
          )}
        </button>
      </div>
    </div>
  );
}
