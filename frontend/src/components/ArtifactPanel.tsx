import { useState, useCallback } from 'react';
import {
  X, FileSpreadsheet, FileText, FileJson, Maximize2, Minimize2,
  MessageSquare, ChevronLeft, ChevronRight,
} from 'lucide-react';
import clsx from 'clsx';
import { SpreadsheetEditor, type SpreadsheetData, spreadsheetToCSV, spreadsheetToJSON } from './SpreadsheetEditor';

// ── Artifact Types ───────────────────────────────────────────────────────────

export interface Artifact {
  id: string;
  type: 'spreadsheet' | 'json' | 'text' | 'bundle';
  title: string;
  fileName: string;
  /** For spreadsheet type */
  spreadsheetData?: SpreadsheetData;
  /** For json/text type */
  textContent?: string;
  /** Source message ID */
  messageId?: string;
  createdAt: Date;
  isDirty?: boolean;
}

interface ArtifactPanelProps {
  artifacts: Artifact[];
  activeArtifactId: string | null;
  onSelectArtifact: (id: string) => void;
  onCloseArtifact: (id: string) => void;
  onClosePanel: () => void;
  onUpdateArtifact: (id: string, updates: Partial<Artifact>) => void;
  onReferenceInChat: (artifact: Artifact) => void;
  onSaveArtifact: (artifact: Artifact) => void;
}

function getArtifactIcon(type: Artifact['type']) {
  switch (type) {
    case 'spreadsheet': return <FileSpreadsheet className="w-4 h-4" />;
    case 'json': return <FileJson className="w-4 h-4" />;
    default: return <FileText className="w-4 h-4" />;
  }
}

export function ArtifactPanel({
  artifacts,
  activeArtifactId,
  onSelectArtifact,
  onCloseArtifact,
  onClosePanel,
  onUpdateArtifact,
  onReferenceInChat,
  onSaveArtifact,
}: ArtifactPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const activeArtifact = artifacts.find(a => a.id === activeArtifactId);

  const handleSpreadsheetChange = useCallback((data: SpreadsheetData) => {
    if (!activeArtifactId) return;
    onUpdateArtifact(activeArtifactId, { spreadsheetData: data, isDirty: data.isDirty });
  }, [activeArtifactId, onUpdateArtifact]);

  const handleSpreadsheetSave = useCallback((data: SpreadsheetData) => {
    if (!activeArtifact) return;
    onSaveArtifact({ ...activeArtifact, spreadsheetData: { ...data, isDirty: false } });
    onUpdateArtifact(activeArtifact.id, { isDirty: false, spreadsheetData: { ...data, isDirty: false } });
  }, [activeArtifact, onSaveArtifact, onUpdateArtifact]);

  const handleDownload = useCallback(async (data: SpreadsheetData, format: 'csv' | 'json') => {
    const content = format === 'csv' ? await spreadsheetToCSV(data) : spreadsheetToJSON(data);
    const blob = new Blob([content], { type: format === 'csv' ? 'text/csv' : 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const baseName = data.fileName.replace(/\.[^.]+$/, '');
    a.href = url;
    a.download = `${baseName}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  const handleReferenceInChat = useCallback(() => {
    if (!activeArtifact) return;
    onReferenceInChat(activeArtifact);
  }, [activeArtifact, onReferenceInChat]);

  const handleTextChange = useCallback((newText: string) => {
    if (!activeArtifactId) return;
    onUpdateArtifact(activeArtifactId, { textContent: newText, isDirty: true });
  }, [activeArtifactId, onUpdateArtifact]);

  // Navigate between artifacts
  const activeIdx = artifacts.findIndex(a => a.id === activeArtifactId);
  const canPrev = activeIdx > 0;
  const canNext = activeIdx < artifacts.length - 1;

  if (artifacts.length === 0) return null;

  return (
    <div className={clsx(
      'flex flex-col bg-white border-l border-gray-200 transition-all duration-300',
      isExpanded ? 'w-full absolute inset-0 z-50' : 'w-[45%] min-w-[380px] max-w-[700px]'
    )}>
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-200 bg-gray-50 shrink-0">
        {/* Artifact tabs */}
        <div className="flex items-center gap-1 flex-1 overflow-x-auto min-w-0">
          {artifacts.map(artifact => (
            <button
              key={artifact.id}
              onClick={() => onSelectArtifact(artifact.id)}
              className={clsx(
                'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs whitespace-nowrap transition-colors max-w-[160px]',
                artifact.id === activeArtifactId
                  ? 'bg-primary-100 text-primary-700 font-medium'
                  : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
              )}
            >
              {getArtifactIcon(artifact.type)}
              <span className="truncate">{artifact.title}</span>
              {artifact.isDirty && <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />}
              <button
                onClick={(e) => { e.stopPropagation(); onCloseArtifact(artifact.id); }}
                className="p-0.5 rounded hover:bg-gray-200 shrink-0"
              >
                <X className="w-3 h-3" />
              </button>
            </button>
          ))}
        </div>

        {/* Navigation */}
        {artifacts.length > 1 && (
          <div className="flex items-center gap-0.5 shrink-0">
            <button onClick={() => canPrev && onSelectArtifact(artifacts[activeIdx - 1].id)} disabled={!canPrev}
              className="p-1 rounded hover:bg-gray-200 disabled:opacity-30">
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <span className="text-[10px] text-gray-400">{activeIdx + 1}/{artifacts.length}</span>
            <button onClick={() => canNext && onSelectArtifact(artifacts[activeIdx + 1].id)} disabled={!canNext}
              className="p-1 rounded hover:bg-gray-200 disabled:opacity-30">
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0 border-l border-gray-200 pl-2 ml-1">
          <button onClick={handleReferenceInChat} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-primary-600 transition-colors" title="Reference in chat">
            <MessageSquare className="w-4 h-4" />
          </button>
          <button onClick={() => setIsExpanded(!isExpanded)} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors" title={isExpanded ? 'Minimize' : 'Expand'}>
            {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
          <button onClick={onClosePanel} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-red-500 transition-colors" title="Close panel">
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeArtifact?.type === 'spreadsheet' && activeArtifact.spreadsheetData ? (
          <SpreadsheetEditor
            data={activeArtifact.spreadsheetData}
            onDataChange={handleSpreadsheetChange}
            onSave={handleSpreadsheetSave}
            onDownload={handleDownload}
            onReferenceInChat={() => handleReferenceInChat()}
          />
        ) : activeArtifact?.type === 'json' && activeArtifact.textContent ? (
          <div className="h-full flex flex-col">
            <div className="flex-1 overflow-auto p-4">
              <textarea
                value={activeArtifact.textContent}
                onChange={e => handleTextChange(e.target.value)}
                className="w-full h-full font-mono text-xs text-gray-700 border border-gray-200 rounded-lg p-3 resize-none focus:outline-none focus:ring-1 focus:ring-primary-500"
                spellCheck={false}
              />
            </div>
          </div>
        ) : activeArtifact?.type === 'text' && activeArtifact.textContent ? (
          <div className="h-full overflow-auto p-4">
            <pre className="text-sm text-gray-700 whitespace-pre-wrap font-sans">{activeArtifact.textContent}</pre>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-sm text-gray-400">
            Select an artifact to view
          </div>
        )}
      </div>
    </div>
  );
}
