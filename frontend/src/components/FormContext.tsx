import { useState, useRef, useCallback } from 'react';
import { ChevronDown, ChevronRight, FileJson, Upload, X, Check } from 'lucide-react';
import clsx from 'clsx';
import type { FormContext as FormContextType } from '../types';

interface FormContextPanelProps {
  formContext: FormContextType | null;
  onFormContextChange: (ctx: FormContextType | null) => void;
}

function countFields(json: Record<string, unknown>): number {
  let count = 0;
  const formElements = json.formElementGroups as Array<{ formElements?: unknown[] }> | undefined;
  if (Array.isArray(formElements)) {
    for (const group of formElements) {
      if (Array.isArray(group.formElements)) {
        count += group.formElements.length;
      }
    }
  }
  if (count === 0) {
    count = Object.keys(json).length;
  }
  return count;
}

function extractFormName(json: Record<string, unknown>): string {
  if (typeof json.name === 'string') return json.name;
  if (typeof json.formName === 'string') return json.formName;
  return 'Uploaded Form';
}

export function FormContextPanel({ formContext, onFormContextChange }: FormContextPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [pasteMode, setPasteMode] = useState(false);
  const [pasteText, setPasteText] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const parseAndSetForm = useCallback((text: string) => {
    try {
      const json = JSON.parse(text) as Record<string, unknown>;
      const name = extractFormName(json);
      const fieldCount = countFields(json);
      onFormContextChange({ name, json, fieldCount });
      setParseError(null);
      setPasteMode(false);
      setPasteText('');
    } catch {
      setParseError('Invalid JSON. Please check the format and try again.');
    }
  }, [onFormContextChange]);

  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      parseAndSetForm(text);
    };
    reader.readAsText(file);
    e.target.value = '';
  }, [parseAndSetForm]);

  const handlePasteSubmit = () => {
    if (pasteText.trim()) {
      parseAndSetForm(pasteText.trim());
    }
  };

  const handleClear = () => {
    onFormContextChange(null);
    setParseError(null);
    setPasteMode(false);
    setPasteText('');
  };

  return (
    <div className="border-b border-gray-200 bg-gray-50/50">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 transition-colors"
      >
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-400" />
        )}
        <FileJson className="w-4 h-4 text-primary-500" />
        <span className="font-medium">Form Context</span>
        {formContext && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-green-600">
            <Check className="w-3.5 h-3.5" />
            {formContext.name} ({formContext.fieldCount} fields)
          </span>
        )}
      </button>

      {isExpanded && (
        <div className="px-4 pb-3">
          {formContext ? (
            <div className="flex items-center gap-2 bg-white rounded-lg border border-gray-200 px-3 py-2">
              <FileJson className="w-4 h-4 text-primary-500 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{formContext.name}</p>
                <p className="text-xs text-gray-500">{formContext.fieldCount} fields loaded</p>
              </div>
              <button
                onClick={handleClear}
                className="p-1 rounded hover:bg-gray-100 transition-colors"
                aria-label="Remove form context"
              >
                <X className="w-4 h-4 text-gray-400" />
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex gap-2">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  <Upload className="w-3.5 h-3.5" />
                  Upload Form JSON
                </button>
                <button
                  onClick={() => setPasteMode(!pasteMode)}
                  className={clsx(
                    'flex items-center gap-1.5 px-3 py-1.5 text-sm border rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500',
                    pasteMode
                      ? 'bg-primary-50 border-primary-300 text-primary-700'
                      : 'bg-white border-gray-300 hover:bg-gray-50'
                  )}
                >
                  <FileJson className="w-3.5 h-3.5" />
                  Paste JSON
                </button>
              </div>

              {pasteMode && (
                <div className="space-y-2">
                  <textarea
                    value={pasteText}
                    onChange={e => {
                      setPasteText(e.target.value);
                      setParseError(null);
                    }}
                    placeholder='Paste your form JSON here... e.g. {"name": "Registration", "formElementGroups": [...]}'
                    rows={4}
                    className="w-full text-xs font-mono border border-gray-300 rounded-lg px-3 py-2 resize-y focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  />
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handlePasteSubmit}
                      disabled={!pasteText.trim()}
                      className="px-3 py-1.5 text-sm bg-primary-600 hover:bg-primary-700 text-white rounded-lg transition-colors font-medium focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Load Form
                    </button>
                    <button
                      onClick={() => {
                        setPasteMode(false);
                        setPasteText('');
                        setParseError(null);
                      }}
                      className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {parseError && (
                <p className="text-xs text-red-600">{parseError}</p>
              )}
            </div>
          )}

          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            className="hidden"
            onChange={handleFileUpload}
          />
        </div>
      )}
    </div>
  );
}
