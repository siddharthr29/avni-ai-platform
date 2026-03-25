import { useState } from 'react';
import { Download, File, Folder, FolderOpen, CheckCircle, XCircle, AlertTriangle, ChevronRight, ChevronDown, X, Loader2, Hash, Search } from 'lucide-react';
import clsx from 'clsx';
import type { BundleFile } from '../types';
import { downloadBundle } from '../services/api';

interface BundlePreviewProps {
  files?: BundleFile[];
  downloadUrl?: string;
  bundleId?: string;
  onToast: (type: 'success' | 'error' | 'info', message: string) => void;
}

function StatusIcon({ status }: { status?: 'pass' | 'fail' | 'warning' }) {
  switch (status) {
    case 'pass':
      return <CheckCircle className="w-3.5 h-3.5 text-green-500" />;
    case 'fail':
      return <XCircle className="w-3.5 h-3.5 text-red-500" />;
    case 'warning':
      return <AlertTriangle className="w-3.5 h-3.5 text-yellow-500" />;
    default:
      return null;
  }
}

function FileTreeNode({
  file,
  depth,
  onSelectFile,
}: {
  file: BundleFile;
  depth: number;
  onSelectFile: (file: BundleFile) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(depth < 2);

  const isDir = file.type === 'directory';

  return (
    <div>
      <button
        className={clsx(
          'w-full flex items-center gap-1.5 px-2 py-1.5 text-left text-sm hover:bg-gray-50 rounded transition-colors',
          !isDir && 'cursor-pointer'
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => {
          if (isDir) {
            setIsExpanded(!isExpanded);
          } else {
            onSelectFile(file);
          }
        }}
      >
        {isDir ? (
          <>
            {isExpanded ? (
              <ChevronDown className="w-3.5 h-3.5 text-gray-400 shrink-0" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5 text-gray-400 shrink-0" />
            )}
            {isExpanded ? (
              <FolderOpen className="w-4 h-4 text-teal-500 shrink-0" />
            ) : (
              <Folder className="w-4 h-4 text-teal-500 shrink-0" />
            )}
          </>
        ) : (
          <>
            <span className="w-3.5 shrink-0" />
            <File className="w-4 h-4 text-gray-400 shrink-0" />
          </>
        )}
        <span className="truncate text-gray-700">{file.name}</span>
        <StatusIcon status={file.status} />
      </button>

      {isDir && isExpanded && file.children && (
        <div>
          {file.children.map((child, index) => (
            <FileTreeNode
              key={`${child.path}-${index}`}
              file={child}
              depth={depth + 1}
              onSelectFile={onSelectFile}
            />
          ))}
        </div>
      )}
    </div>
  );
}

const SAMPLE_BUNDLE_FILES: BundleFile[] = [
  {
    name: 'bundle',
    path: 'bundle',
    type: 'directory',
    status: 'pass',
    children: [
      {
        name: 'concepts.json',
        path: 'bundle/concepts.json',
        type: 'file',
        status: 'pass',
        content: '[\n  {\n    "name": "Height",\n    "dataType": "Numeric",\n    "uuid": "..."\n  }\n]',
      },
      {
        name: 'forms',
        path: 'bundle/forms',
        type: 'directory',
        status: 'pass',
        children: [
          {
            name: 'Registration.json',
            path: 'bundle/forms/Registration.json',
            type: 'file',
            status: 'pass',
            content: '{\n  "name": "Registration",\n  "formType": "IndividualProfile"\n}',
          },
        ],
      },
      {
        name: 'formMappings.json',
        path: 'bundle/formMappings.json',
        type: 'file',
        status: 'pass',
        content: '[\n  {\n    "formName": "Registration",\n    "subjectType": "Individual"\n  }\n]',
      },
    ],
  },
];

export function BundlePreview({ files, downloadUrl, bundleId, onToast }: BundlePreviewProps) {
  const [selectedFile, setSelectedFile] = useState<BundleFile | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const bundleFiles = files && files.length > 0 ? files : SAMPLE_BUNDLE_FILES;

  const handleDownload = async () => {
    if (bundleId) {
      setIsDownloading(true);
      try {
        const blob = await downloadBundle(bundleId);
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `avni-bundle-${bundleId}.zip`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        onToast('success', 'Bundle downloaded successfully');
      } catch (err) {
        onToast('error', `Download failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
      } finally {
        setIsDownloading(false);
      }
    } else if (downloadUrl) {
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = 'avni-bundle.zip';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      onToast('success', 'Bundle download started');
    }
  };

  const canDownload = !!(bundleId || downloadUrl);

  return (
    <div className="mt-2 rounded-lg border border-gray-200 overflow-hidden bg-white shadow-sm">
      <div className="bg-white px-3 py-2.5 border-b border-gray-200 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium text-gray-900">Bundle Contents</span>
          {bundleId && (
            <span className="flex items-center gap-1 text-xs text-gray-400 bg-gray-50 border border-gray-200 px-2 py-0.5 rounded-full">
              <Hash className="w-3 h-3" />
              {bundleId.slice(0, 8)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="relative hidden sm:block">
            <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              placeholder="Search files..."
              className="pl-8 pr-3 py-1.5 text-xs border border-gray-200 rounded-lg bg-gray-50 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500 w-40"
            />
          </div>
          <button
            onClick={handleDownload}
            disabled={!canDownload || isDownloading}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors font-medium focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2',
              canDownload && !isDownloading
                ? 'bg-teal-700 hover:bg-teal-800 text-white'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed'
            )}
          >
            {isDownloading ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Downloading...
              </>
            ) : (
              <>
                <Download className="w-3.5 h-3.5" />
                Download ZIP
              </>
            )}
          </button>
        </div>
      </div>

      <div className="flex max-h-64">
        {/* File tree */}
        <div className={clsx(
          'overflow-y-auto py-1',
          selectedFile ? 'w-1/2 border-r border-gray-200' : 'w-full'
        )}>
          {bundleFiles.map((file, index) => (
            <FileTreeNode
              key={`${file.path}-${index}`}
              file={file}
              depth={0}
              onSelectFile={setSelectedFile}
            />
          ))}
        </div>

        {/* File preview */}
        {selectedFile && (
          <div className="w-1/2 flex flex-col">
            <div className="px-3 py-1.5 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
              <span className="text-xs text-gray-500 dark:text-gray-400 truncate">{selectedFile.path}</span>
              <button
                onClick={() => setSelectedFile(null)}
                className="p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                aria-label="Close preview"
              >
                <X className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500" />
              </button>
            </div>
            <pre className="flex-1 overflow-auto p-3 text-xs text-gray-700 dark:text-gray-200 bg-gray-50 dark:bg-gray-900 font-mono">
              {selectedFile.content ?? 'No preview available'}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
