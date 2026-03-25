import { useState, useEffect } from 'react';
import { authFetch } from '../services/api';
import {
  CheckCircle,
  AlertTriangle,
  Upload,
  Eye,
  Edit3,
  FileJson,
  Download,
  MessageSquare,
  ChevronDown,
  ChevronRight,
  Search,
  X,
  Loader2,
  ArrowRight,
} from 'lucide-react';
import clsx from 'clsx';

interface BundleFile {
  name: string;
  content: any;
  type: string;
}

interface ValidationIssue {
  severity: string;
  category: string;
  message: string;
  file: string;
  fix_hint: string;
}

interface BundleReviewProps {
  bundleId: string;
  onUpload?: (bundleId: string) => void;
  onClose?: () => void;
}

function SummaryCard({ count, label, color }: { count: number; label: string; color: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 flex flex-col items-center">
      <span className={clsx('text-2xl font-bold', color)}>{count}</span>
      <span className="text-sm text-gray-600 mt-0.5">{label}</span>
    </div>
  );
}

export function BundleReview({ bundleId, onUpload, onClose }: BundleReviewProps) {
  const [files, setFiles] = useState<BundleFile[]>([]);
  const [validation, setValidation] = useState<{ valid: boolean; issues: ValidationIssue[] } | null>(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedErrors, setExpandedErrors] = useState(false);

  useEffect(() => {
    loadBundle();
  }, [bundleId]);

  async function loadBundle() {
    setLoading(true);
    try {
      const resp = await authFetch(`/api/bundle/review/${bundleId}`);
      if (resp.ok) {
        const data = await resp.json();
        setFiles(data.files || []);
      }
      const valResp = await authFetch(`/api/bundle/${bundleId}/validate`);
      if (valResp.ok) {
        setValidation(await valResp.json());
      }
    } catch (err) {
      console.error('Failed to load bundle:', err);
    }
    setLoading(false);
  }

  async function handleUpload() {
    setShowUploadDialog(false);
    onUpload?.(bundleId);
  }

  if (loading) {
    return (
      <div className="w-full bg-white border border-gray-200 rounded-lg shadow-sm">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-teal-600" />
          <span className="ml-3 text-gray-500">Loading bundle...</span>
        </div>
      </div>
    );
  }

  const errors = validation?.issues?.filter(i => i.severity === 'error') || [];
  const warnings = validation?.issues?.filter(i => i.severity === 'warning') || [];
  const totalChecks = (validation?.issues?.length || 0) + (validation?.valid ? 55 : 0);

  // Count entities by type
  const conceptCount = files.find(f => f.name === 'concepts.json')?.content?.length || 0;
  const formCount = files.filter(f => f.type === 'form').length || files.find(f => f.name === 'forms')?.content?.length || 0;
  const ruleCount = files.filter(f => f.type === 'rule').length || 0;
  const mappingCount = files.find(f => f.name === 'formMappings.json')?.content?.length || 0;

  const tabs = [
    { key: 'overview', label: 'Overview', icon: Eye },
    { key: 'files', label: 'Files', icon: FileJson },
    { key: 'validation', label: 'Validation', icon: AlertTriangle },
  ];

  const filteredFiles = searchTerm
    ? files.filter(f => f.name.toLowerCase().includes(searchTerm.toLowerCase()))
    : files;

  return (
    <div className="w-full bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 bg-white">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <FileJson className="w-5 h-5 text-teal-600" />
              Bundle Review
            </h2>
            <p className="text-sm text-gray-500 mt-0.5">
              {bundleId} - {files.length} files
            </p>
          </div>
          <div className="flex items-center gap-2">
            {validation?.valid ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-green-50 text-green-700 rounded-full text-xs font-medium border border-green-200">
                <CheckCircle className="w-3.5 h-3.5" /> Valid
              </span>
            ) : validation ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-red-50 text-red-700 rounded-full text-xs font-medium border border-red-200">
                <AlertTriangle className="w-3.5 h-3.5" /> {errors.length} errors
              </span>
            ) : null}
          </div>
        </div>
      </div>

      {/* Summary cards */}
      <div className="px-6 py-4 bg-gray-50 border-b border-gray-200">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <SummaryCard count={conceptCount} label="Concepts" color="text-teal-700" />
          <SummaryCard count={formCount} label="Forms" color="text-teal-700" />
          <SummaryCard count={ruleCount} label="Rules" color="text-teal-700" />
          <SummaryCard count={mappingCount} label="Mappings" color="text-teal-700" />
        </div>
      </div>

      {/* Validation status banner */}
      <div className="px-6 py-3 border-b border-gray-200">
        {validation?.valid ? (
          <div className="flex items-center gap-2 px-3 py-2 bg-green-50 border border-green-200 rounded-lg">
            <CheckCircle className="w-4 h-4 text-green-600" />
            <span className="text-sm font-medium text-green-700">All {totalChecks} checks passed</span>
          </div>
        ) : validation && errors.length > 0 ? (
          <div className="bg-red-50 border border-red-200 rounded-lg overflow-hidden">
            <button
              onClick={() => setExpandedErrors(!expandedErrors)}
              className="w-full flex items-center justify-between px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-red-600" />
                <span className="text-sm font-medium text-red-700">{errors.length} errors found</span>
              </div>
              {expandedErrors ? (
                <ChevronDown className="w-4 h-4 text-red-500" />
              ) : (
                <ChevronRight className="w-4 h-4 text-red-500" />
              )}
            </button>
            {expandedErrors && (
              <div className="px-3 pb-3 space-y-1.5">
                {errors.map((issue, i) => (
                  <div key={i} className="text-xs text-red-700 pl-6">
                    <span className="font-medium">{issue.category}:</span> {issue.message}
                    {issue.fix_hint && <span className="text-red-500 ml-1">(Fix: {issue.fix_hint})</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}
      </div>

      {/* Tab navigation */}
      <div className="border-b border-gray-200 bg-white">
        <div className="flex px-6 gap-0">
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={clsx(
                'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors focus:outline-none',
                activeTab === tab.key
                  ? 'border-teal-600 text-teal-700'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              )}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="px-6 py-4">
        {activeTab === 'overview' && (
          <div className="space-y-3">
            {files.map(f => (
              <div key={f.name} className="flex items-center justify-between p-3 rounded-lg bg-gray-50 border border-gray-200 hover:bg-gray-100 transition-colors">
                <div className="flex items-center gap-2">
                  <FileJson className="w-4 h-4 text-teal-600" />
                  <span className="font-medium text-sm text-gray-900">{f.name}</span>
                </div>
                <span className="text-xs text-gray-500 border border-gray-200 bg-white px-2 py-0.5 rounded">{f.type}</span>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'files' && (
          <div>
            {/* Search bar */}
            <div className="mb-4 relative">
              <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                placeholder="Filter files..."
                className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
              />
            </div>
            <div className="grid grid-cols-4 gap-4">
              <div className="col-span-1 space-y-1 max-h-96 overflow-y-auto">
                {filteredFiles.map(f => (
                  <button
                    key={f.name}
                    onClick={() => {
                      setSelectedFile(f.name);
                      setEditContent(JSON.stringify(f.content, null, 2));
                    }}
                    className={clsx(
                      'w-full text-left px-3 py-2 rounded-lg text-sm transition-colors',
                      selectedFile === f.name
                        ? 'bg-teal-50 text-teal-700 border border-teal-200 font-medium'
                        : 'hover:bg-gray-50 text-gray-700 border border-transparent'
                    )}
                  >
                    {f.name}
                  </button>
                ))}
              </div>
              <div className="col-span-3">
                {selectedFile ? (
                  <div className="relative border border-gray-200 rounded-lg overflow-hidden">
                    <div className="flex items-center justify-between px-3 py-2 bg-gray-50 border-b border-gray-200">
                      <span className="text-xs text-gray-500">{selectedFile}</span>
                      <button
                        className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-teal-700 bg-teal-50 hover:bg-teal-100 rounded-md transition-colors"
                        onClick={async () => {
                          try {
                            const parsed = JSON.parse(editContent);
                            await authFetch(`/api/bundle/review/edit`, {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({
                                bundle_id: bundleId,
                                file_name: selectedFile,
                                content: parsed,
                              }),
                            });
                            loadBundle();
                          } catch (err) {
                            alert('Invalid JSON');
                          }
                        }}
                      >
                        <Edit3 className="w-3 h-3" /> Save
                      </button>
                    </div>
                    <textarea
                      value={editContent}
                      onChange={e => setEditContent(e.target.value)}
                      className="w-full h-96 font-mono text-xs p-4 bg-white text-gray-900 focus:outline-none focus:ring-0 border-0 resize-none"
                      spellCheck={false}
                    />
                  </div>
                ) : (
                  <div className="flex items-center justify-center h-96 text-gray-400 border border-gray-200 rounded-lg bg-gray-50">
                    Select a file to view/edit
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'validation' && (
          <div className="space-y-3">
            {errors.length === 0 && warnings.length === 0 ? (
              <div className="flex items-center gap-2 px-4 py-3 bg-green-50 border border-green-200 rounded-lg">
                <CheckCircle className="w-5 h-5 text-green-600" />
                <div>
                  <p className="text-sm font-medium text-green-700">All checks passed</p>
                  <p className="text-xs text-green-600">Bundle is ready for upload.</p>
                </div>
              </div>
            ) : null}
            {errors.map((issue, i) => (
              <div key={`e-${i}`} className="px-4 py-3 bg-red-50 border border-red-200 rounded-lg">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-600 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-red-700">{issue.category}</p>
                    <p className="text-sm text-red-600">{issue.message}</p>
                    {issue.fix_hint && (
                      <p className="mt-1 text-xs text-red-500">Fix: {issue.fix_hint}</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {warnings.map((issue, i) => (
              <div key={`w-${i}`} className="px-4 py-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-yellow-600 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-yellow-700">{issue.category}</p>
                    <p className="text-sm text-yellow-600">{issue.message}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Action bar */}
      <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 space-y-3">
        {/* Top row: secondary actions */}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            {onClose && (
              <button
                onClick={onClose}
                className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 rounded-lg transition-colors"
              >
                <MessageSquare className="w-4 h-4" />
                Edit in Chat
              </button>
            )}
            <button
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 rounded-lg transition-colors"
            >
              <Download className="w-4 h-4" />
              Download ZIP
            </button>
            <button
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 rounded-lg transition-colors"
            >
              <ArrowRight className="w-4 h-4" />
              Compare with Avni
            </button>
          </div>
        </div>

        {/* Upload button - prominent */}
        <button
          onClick={() => setShowUploadDialog(true)}
          disabled={!validation?.valid}
          className={clsx(
            'w-full flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2',
            validation?.valid
              ? 'bg-teal-700 hover:bg-teal-800 text-white'
              : 'bg-gray-300 text-gray-500 cursor-not-allowed'
          )}
        >
          <Upload className="w-4 h-4" />
          Upload to Avni
        </button>
        <p className="text-center text-xs text-gray-500">
          Target: staging.avniproject.org | Org: {bundleId.split('-')[0] || 'Unknown'}
        </p>
      </div>

      {/* Upload confirmation dialog */}
      {showUploadDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full mx-4 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900">Upload Bundle to Avni?</h3>
            </div>
            <div className="px-6 py-4">
              <p className="text-sm text-gray-600">
                This will apply all metadata changes to your Avni organisation. Make sure you have reviewed all files.
              </p>
            </div>
            <div className="px-6 py-4 bg-gray-50 flex items-center justify-end gap-3">
              <button
                onClick={() => setShowUploadDialog(false)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleUpload}
                className="px-4 py-2 text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-lg transition-colors"
              >
                Confirm Upload
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
