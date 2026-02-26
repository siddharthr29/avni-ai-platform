import { useState } from 'react';
import { Download, File, Folder, FolderOpen, CheckCircle, XCircle, AlertTriangle, ChevronRight, ChevronDown, X } from 'lucide-react';
import clsx from 'clsx';
import type { BundleFile } from '../types';

interface BundlePreviewProps {
  files?: BundleFile[];
  downloadUrl?: string;
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
          'w-full flex items-center gap-1.5 px-2 py-1 text-left text-sm hover:bg-gray-100 rounded transition-colors',
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
              <FolderOpen className="w-4 h-4 text-yellow-500 shrink-0" />
            ) : (
              <Folder className="w-4 h-4 text-yellow-500 shrink-0" />
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

export function BundlePreview({ files, downloadUrl }: BundlePreviewProps) {
  const [selectedFile, setSelectedFile] = useState<BundleFile | null>(null);
  const bundleFiles = files && files.length > 0 ? files : SAMPLE_BUNDLE_FILES;

  const handleDownload = () => {
    if (downloadUrl) {
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = 'avni-bundle.zip';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  return (
    <div className="mt-2 rounded-lg border border-gray-200 overflow-hidden">
      <div className="bg-gray-50 px-3 py-2 border-b border-gray-200 flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">Bundle Contents</span>
        <button
          onClick={handleDownload}
          disabled={!downloadUrl}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors font-medium focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
            downloadUrl
              ? 'bg-primary-600 hover:bg-primary-700 text-white'
              : 'bg-gray-200 text-gray-400 cursor-not-allowed'
          )}
        >
          <Download className="w-3.5 h-3.5" />
          Download ZIP
        </button>
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
            <div className="px-3 py-1.5 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
              <span className="text-xs text-gray-500 truncate">{selectedFile.path}</span>
              <button
                onClick={() => setSelectedFile(null)}
                className="p-0.5 rounded hover:bg-gray-200 transition-colors"
                aria-label="Close preview"
              >
                <X className="w-3.5 h-3.5 text-gray-400" />
              </button>
            </div>
            <pre className="flex-1 overflow-auto p-3 text-xs text-gray-700 bg-gray-50/50 font-mono">
              {selectedFile.content ?? 'No preview available'}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
