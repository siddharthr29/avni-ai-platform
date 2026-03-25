import { useState, useCallback, useMemo, useRef } from 'react';
import {
  Download, Save, RotateCcw, Plus, Trash2, ArrowUpDown,
  ChevronLeft, ChevronRight, Search, X,
} from 'lucide-react';
import clsx from 'clsx';

export interface SpreadsheetData {
  headers: string[];
  rows: string[][];
  fileName: string;
  mimeType: string;
  /** Track whether data has been modified */
  isDirty?: boolean;
}

interface SpreadsheetEditorProps {
  data: SpreadsheetData;
  onDataChange: (data: SpreadsheetData) => void;
  onSave?: (data: SpreadsheetData) => void;
  onDownload?: (data: SpreadsheetData, format: 'csv' | 'json') => void;
  onReferenceInChat?: (data: SpreadsheetData) => void;
  readOnly?: boolean;
}

const PAGE_SIZE = 50;

export async function parseCSVToSpreadsheet(csvText: string, fileName: string): Promise<SpreadsheetData> {
  const Papa = await import('papaparse');
  const result = Papa.default.parse(csvText, { skipEmptyLines: true });
  const allRows = result.data as string[][];
  if (allRows.length === 0) return { headers: [], rows: [], fileName, mimeType: 'text/csv' };
  return {
    headers: allRows[0],
    rows: allRows.slice(1),
    fileName,
    mimeType: 'text/csv',
  };
}

export async function spreadsheetToCSV(data: SpreadsheetData): Promise<string> {
  const Papa = await import('papaparse');
  return Papa.default.unparse({ fields: data.headers, data: data.rows });
}

export function spreadsheetToJSON(data: SpreadsheetData): string {
  const records = data.rows.map(row => {
    const obj: Record<string, string> = {};
    data.headers.forEach((h, i) => { obj[h] = row[i] ?? ''; });
    return obj;
  });
  return JSON.stringify(records, null, 2);
}

export function SpreadsheetEditor({
  data,
  onDataChange,
  onSave,
  onDownload,
  onReferenceInChat,
  readOnly = false,
}: SpreadsheetEditorProps) {
  const [editingCell, setEditingCell] = useState<{ row: number; col: number } | null>(null);
  const [editValue, setEditValue] = useState('');
  const [page, setPage] = useState(0);
  const [sortCol, setSortCol] = useState<number | null>(null);
  const [sortAsc, setSortAsc] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedRows, setSelectedRows] = useState<Set<number>>(new Set());
  const editRef = useRef<HTMLInputElement>(null);

  // Filter rows by search
  const filteredRows = useMemo(() => {
    if (!searchTerm) return data.rows;
    const q = searchTerm.toLowerCase();
    return data.rows.filter(row => row.some(cell => cell.toLowerCase().includes(q)));
  }, [data.rows, searchTerm]);

  // Sort rows
  const sortedRows = useMemo(() => {
    if (sortCol === null) return filteredRows;
    const sorted = [...filteredRows].sort((a, b) => {
      const va = a[sortCol] ?? '';
      const vb = b[sortCol] ?? '';
      const numA = Number(va);
      const numB = Number(vb);
      if (!isNaN(numA) && !isNaN(numB)) return sortAsc ? numA - numB : numB - numA;
      return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
    });
    return sorted;
  }, [filteredRows, sortCol, sortAsc]);

  // Paginate
  const totalPages = Math.max(1, Math.ceil(sortedRows.length / PAGE_SIZE));
  const pageRows = sortedRows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const startEditing = useCallback((rowIdx: number, colIdx: number) => {
    if (readOnly) return;
    const globalRow = page * PAGE_SIZE + rowIdx;
    setEditingCell({ row: globalRow, col: colIdx });
    setEditValue(data.rows[globalRow]?.[colIdx] ?? '');
    setTimeout(() => editRef.current?.focus(), 0);
  }, [readOnly, page, data.rows]);

  const commitEdit = useCallback(() => {
    if (!editingCell) return;
    const newRows = data.rows.map((row, ri) => {
      if (ri !== editingCell.row) return row;
      const newRow = [...row];
      newRow[editingCell.col] = editValue;
      return newRow;
    });
    onDataChange({ ...data, rows: newRows, isDirty: true });
    setEditingCell(null);
  }, [editingCell, editValue, data, onDataChange]);

  const handleCellKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') { commitEdit(); }
    if (e.key === 'Escape') { setEditingCell(null); }
    if (e.key === 'Tab') {
      e.preventDefault();
      commitEdit();
      if (editingCell) {
        const nextCol = editingCell.col + 1;
        if (nextCol < data.headers.length) {
          startEditing(editingCell.row - page * PAGE_SIZE, nextCol);
        }
      }
    }
  }, [commitEdit, editingCell, data.headers.length, startEditing, page]);

  const handleSort = useCallback((colIdx: number) => {
    if (sortCol === colIdx) {
      setSortAsc(prev => !prev);
    } else {
      setSortCol(colIdx);
      setSortAsc(true);
    }
  }, [sortCol]);

  const addRow = useCallback(() => {
    const newRow = data.headers.map(() => '');
    onDataChange({ ...data, rows: [...data.rows, newRow], isDirty: true });
    const lastPage = Math.ceil((data.rows.length + 1) / PAGE_SIZE) - 1;
    setPage(lastPage);
  }, [data, onDataChange]);

  const deleteSelectedRows = useCallback(() => {
    if (selectedRows.size === 0) return;
    const newRows = data.rows.filter((_, i) => !selectedRows.has(i));
    onDataChange({ ...data, rows: newRows, isDirty: true });
    setSelectedRows(new Set());
  }, [data, onDataChange, selectedRows]);

  const handleDownload = useCallback(async (format: 'csv' | 'json') => {
    if (onDownload) {
      onDownload(data, format);
      return;
    }
    const content = format === 'csv' ? await spreadsheetToCSV(data) : spreadsheetToJSON(data);
    const blob = new Blob([content], { type: format === 'csv' ? 'text/csv' : 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const baseName = data.fileName.replace(/\.[^.]+$/, '');
    a.href = url;
    a.download = `${baseName}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }, [data, onDownload]);

  const toggleRowSelection = useCallback((globalIdx: number) => {
    setSelectedRows(prev => {
      const next = new Set(prev);
      if (next.has(globalIdx)) next.delete(globalIdx); else next.add(globalIdx);
      return next;
    });
  }, []);

  return (
    <div className="flex flex-col h-full bg-white border border-gray-200 rounded-xl overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-200 bg-gray-50 flex-wrap">
        <div className="flex items-center gap-1.5 text-sm font-medium text-gray-700 mr-2">
          <span className="truncate max-w-[200px]">{data.fileName}</span>
          {data.isDirty && <span className="w-2 h-2 rounded-full bg-amber-400" title="Unsaved changes" />}
        </div>

        {/* Search */}
        <div className="relative flex-1 min-w-[140px] max-w-[260px]">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
          <input
            value={searchTerm}
            onChange={e => { setSearchTerm(e.target.value); setPage(0); }}
            placeholder="Search..."
            className="w-full pl-7 pr-7 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
          {searchTerm && (
            <button onClick={() => setSearchTerm('')} className="absolute right-2 top-1/2 -translate-y-1/2">
              <X className="w-3.5 h-3.5 text-gray-400" />
            </button>
          )}
        </div>

        <div className="flex-1" />

        {/* Actions */}
        {!readOnly && (
          <>
            <button onClick={addRow} className="flex items-center gap-1 text-xs text-gray-600 hover:text-primary-600 px-2 py-1.5 rounded-lg hover:bg-gray-100 transition-colors" title="Add row">
              <Plus className="w-3.5 h-3.5" /> Row
            </button>
            {selectedRows.size > 0 && (
              <button onClick={deleteSelectedRows} className="flex items-center gap-1 text-xs text-red-600 hover:text-red-700 px-2 py-1.5 rounded-lg hover:bg-red-50 transition-colors">
                <Trash2 className="w-3.5 h-3.5" /> Delete ({selectedRows.size})
              </button>
            )}
          </>
        )}

        {onSave && data.isDirty && (
          <button onClick={() => onSave(data)} className="flex items-center gap-1 text-xs text-white bg-primary-600 hover:bg-primary-700 px-3 py-1.5 rounded-lg transition-colors">
            <Save className="w-3.5 h-3.5" /> Save
          </button>
        )}

        <button onClick={() => handleDownload('csv')} className="flex items-center gap-1 text-xs text-gray-600 hover:text-primary-600 px-2 py-1.5 rounded-lg hover:bg-gray-100 transition-colors" title="Download CSV">
          <Download className="w-3.5 h-3.5" /> CSV
        </button>
        <button onClick={() => handleDownload('json')} className="flex items-center gap-1 text-xs text-gray-600 hover:text-primary-600 px-2 py-1.5 rounded-lg hover:bg-gray-100 transition-colors" title="Download JSON">
          <Download className="w-3.5 h-3.5" /> JSON
        </button>

        {onReferenceInChat && (
          <button onClick={() => onReferenceInChat(data)} className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-700 px-2 py-1.5 rounded-lg hover:bg-primary-50 transition-colors border border-primary-200" title="Reference in chat">
            <RotateCcw className="w-3.5 h-3.5" /> Use in Chat
          </button>
        )}
      </div>

      {/* Stats bar */}
      <div className="px-3 py-1 text-[11px] text-gray-400 border-b border-gray-100 bg-white flex items-center gap-3">
        <span>{data.rows.length} rows</span>
        <span>{data.headers.length} columns</span>
        {searchTerm && <span>{filteredRows.length} matching</span>}
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm border-collapse">
          <thead className="sticky top-0 z-10">
            <tr className="bg-gray-50 border-b border-gray-200">
              {!readOnly && (
                <th className="w-10 px-2 py-2 text-center">
                  <input
                    type="checkbox"
                    checked={selectedRows.size === data.rows.length && data.rows.length > 0}
                    onChange={e => {
                      if (e.target.checked) setSelectedRows(new Set(data.rows.map((_, i) => i)));
                      else setSelectedRows(new Set());
                    }}
                    className="rounded border-gray-300"
                  />
                </th>
              )}
              <th className="w-12 px-2 py-2 text-xs text-gray-400 font-normal text-center">#</th>
              {data.headers.map((header, colIdx) => (
                <th
                  key={colIdx}
                  className="px-3 py-2 text-left text-xs font-semibold text-gray-600 whitespace-nowrap cursor-pointer hover:bg-gray-100 select-none"
                  onClick={() => handleSort(colIdx)}
                >
                  <div className="flex items-center gap-1">
                    {header}
                    {sortCol === colIdx && (
                      <ArrowUpDown className={clsx('w-3 h-3', sortAsc ? 'text-primary-500' : 'text-primary-500 rotate-180')} />
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.length === 0 ? (
              <tr>
                <td colSpan={data.headers.length + (readOnly ? 1 : 2)} className="text-center py-8 text-sm text-gray-400">
                  {searchTerm ? 'No matching rows' : 'No data'}
                </td>
              </tr>
            ) : (
              pageRows.map((row, rowIdx) => {
                const globalIdx = page * PAGE_SIZE + rowIdx;
                return (
                  <tr
                    key={globalIdx}
                    className={clsx(
                      'border-b border-gray-50 transition-colors',
                      selectedRows.has(globalIdx) ? 'bg-primary-50/50' : rowIdx % 2 === 0 ? 'bg-white' : 'bg-gray-50/30',
                      !readOnly && 'hover:bg-primary-50/30'
                    )}
                  >
                    {!readOnly && (
                      <td className="w-10 px-2 py-1.5 text-center">
                        <input
                          type="checkbox"
                          checked={selectedRows.has(globalIdx)}
                          onChange={() => toggleRowSelection(globalIdx)}
                          className="rounded border-gray-300"
                        />
                      </td>
                    )}
                    <td className="w-12 px-2 py-1.5 text-xs text-gray-400 text-center">{globalIdx + 1}</td>
                    {row.map((cell, colIdx) => {
                      const isEditing = editingCell?.row === globalIdx && editingCell?.col === colIdx;
                      return (
                        <td
                          key={colIdx}
                          className={clsx(
                            'px-3 py-1.5 text-gray-700',
                            !readOnly && 'cursor-text',
                            isEditing && 'p-0'
                          )}
                          onDoubleClick={() => startEditing(rowIdx, colIdx)}
                        >
                          {isEditing ? (
                            <input
                              ref={editRef}
                              value={editValue}
                              onChange={e => setEditValue(e.target.value)}
                              onBlur={commitEdit}
                              onKeyDown={handleCellKeyDown}
                              className="w-full px-3 py-1.5 text-sm border-2 border-primary-500 rounded focus:outline-none bg-white"
                              autoFocus
                            />
                          ) : (
                            <span className="block truncate max-w-[300px]" title={cell}>{cell}</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-3 py-2 border-t border-gray-200 bg-gray-50">
          <span className="text-xs text-gray-500">
            Page {page + 1} of {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="p-1 rounded hover:bg-gray-200 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="p-1 rounded hover:bg-gray-200 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
