import { AlertCircle, FileSpreadsheet } from 'lucide-react';

export function ProgressIndicator({ progress }: { progress: { step: string; current: number; total: number } }) {
  const percentage = Math.round((progress.current / progress.total) * 100);
  return (
    <div className="my-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm text-gray-900">{progress.step}</span>
        <span className="text-xs text-gray-600">{percentage}%</span>
      </div>
      <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
        <div
          className="h-full bg-teal-600 rounded-full transition-all duration-300 ease-out"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <p className="text-xs text-gray-500 mt-1">
        {progress.current} of {progress.total}
      </p>
    </div>
  );
}

export function ExtractedDataTable({ records, warnings, onOpenAsArtifact }: {
  records: Record<string, unknown>[];
  warnings: string[];
  onOpenAsArtifact?: (records: Record<string, unknown>[]) => void;
}) {
  if (records.length === 0) {
    return <p className="text-sm text-gray-500 italic">No data extracted.</p>;
  }
  const columns = Object.keys(records[0]);
  return (
    <div className="mt-2">
      {warnings.length > 0 && (
        <div className="mb-2 space-y-1">
          {warnings.map((warning, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-yellow-700 bg-yellow-50 rounded px-2 py-1">
              <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              {warning}
            </div>
          ))}
        </div>
      )}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-100 border-b border-gray-200">
              {columns.map(col => (
                <th key={col} className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records.map((record, rowIndex) => (
              <tr key={rowIndex} className="border-b border-gray-100 last:border-b-0 even:bg-gray-50">
                {columns.map(col => (
                  <td key={col} className="px-3 py-2 text-gray-900 whitespace-nowrap">{String(record[col] ?? '')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {onOpenAsArtifact && records.length > 0 && (
        <button
          onClick={() => onOpenAsArtifact(records)}
          className="mt-2 flex items-center gap-1.5 text-xs text-teal-600 hover:text-teal-700 px-2 py-1 rounded-lg hover:bg-teal-50 transition-colors"
        >
          <FileSpreadsheet className="w-3.5 h-3.5" />
          Open in Editor (edit, save, download)
        </button>
      )}
    </div>
  );
}
