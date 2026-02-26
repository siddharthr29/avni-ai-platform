import { useState, type ReactNode } from 'react';
import { Copy, Check, AlertCircle } from 'lucide-react';
import clsx from 'clsx';
import type { Message } from '../types';
import { FieldMapping } from './FieldMapping';
import { BundlePreview } from './BundlePreview';

interface ChatMessageProps {
  message: Message;
}

function renderMarkdown(text: string): ReactNode[] {
  const lines = text.split('\n');
  const elements: ReactNode[] = [];
  let inCodeBlock = false;
  let codeContent = '';
  let codeLanguage = '';
  let listItems: string[] = [];
  let listType: 'ul' | 'ol' | null = null;

  const flushList = () => {
    if (listItems.length > 0 && listType) {
      const ListTag = listType === 'ol' ? 'ol' : 'ul';
      elements.push(
        <ListTag
          key={`list-${elements.length}`}
          className={clsx(
            'my-1 pl-5',
            listType === 'ol' ? 'list-decimal' : 'list-disc'
          )}
        >
          {listItems.map((item, i) => (
            <li key={i} className="text-sm text-gray-700 py-0.5">
              {renderInlineMarkdown(item)}
            </li>
          ))}
        </ListTag>
      );
      listItems = [];
      listType = null;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Code blocks
    if (line.trim().startsWith('```')) {
      if (inCodeBlock) {
        flushList();
        elements.push(
          <CodeBlock key={`code-${i}`} code={codeContent.trimEnd()} language={codeLanguage} />
        );
        codeContent = '';
        codeLanguage = '';
        inCodeBlock = false;
      } else {
        flushList();
        inCodeBlock = true;
        codeLanguage = line.trim().slice(3).trim();
      }
      continue;
    }

    if (inCodeBlock) {
      codeContent += (codeContent ? '\n' : '') + line;
      continue;
    }

    // Headers
    const headerMatch = line.match(/^(#{1,4})\s+(.+)/);
    if (headerMatch) {
      flushList();
      const level = headerMatch[1].length;
      const headerText = headerMatch[2];
      const className = clsx(
        'font-semibold text-gray-900',
        level === 1 && 'text-lg mt-3 mb-1',
        level === 2 && 'text-base mt-2 mb-1',
        level === 3 && 'text-sm mt-2 mb-0.5',
        level === 4 && 'text-sm mt-1'
      );
      elements.push(
        <p key={`h-${i}`} className={className}>{renderInlineMarkdown(headerText)}</p>
      );
      continue;
    }

    // Unordered list
    const ulMatch = line.match(/^[\s]*[-*]\s+(.+)/);
    if (ulMatch) {
      if (listType === 'ol') flushList();
      listType = 'ul';
      listItems.push(ulMatch[1]);
      continue;
    }

    // Ordered list
    const olMatch = line.match(/^[\s]*\d+\.\s+(.+)/);
    if (olMatch) {
      if (listType === 'ul') flushList();
      listType = 'ol';
      listItems.push(olMatch[1]);
      continue;
    }

    flushList();

    // Empty line
    if (line.trim() === '') {
      continue;
    }

    // Regular paragraph
    elements.push(
      <p key={`p-${i}`} className="text-sm text-gray-700 my-0.5">
        {renderInlineMarkdown(line)}
      </p>
    );
  }

  flushList();

  // If still in code block (unclosed), render what we have
  if (inCodeBlock && codeContent) {
    elements.push(
      <CodeBlock key="code-final" code={codeContent.trimEnd()} language={codeLanguage} />
    );
  }

  return elements;
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const regex = /(\*\*(.+?)\*\*)|(\*(.+?)\*)|(`(.+?)`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let keyCounter = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    if (match[1]) {
      parts.push(<strong key={`b-${keyCounter++}`} className="font-semibold">{match[2]}</strong>);
    } else if (match[3]) {
      parts.push(<em key={`i-${keyCounter++}`}>{match[4]}</em>);
    } else if (match[5]) {
      parts.push(
        <code key={`c-${keyCounter++}`} className="bg-gray-100 text-primary-700 px-1 py-0.5 rounded text-xs font-mono">
          {match[6]}
        </code>
      );
    }

    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length > 0 ? parts : [text];
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-2 rounded-lg overflow-hidden border border-gray-200">
      <div className="bg-gray-800 px-3 py-1.5 flex items-center justify-between">
        <span className="text-xs text-gray-400">{language || 'code'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5" />
              Copied
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              Copy
            </>
          )}
        </button>
      </div>
      <pre className="bg-gray-900 p-3 overflow-x-auto">
        <code className="text-xs text-gray-200 font-mono whitespace-pre">{code}</code>
      </pre>
    </div>
  );
}

function ProgressIndicator({ progress }: { progress: { step: string; current: number; total: number } }) {
  const percentage = Math.round((progress.current / progress.total) * 100);
  return (
    <div className="my-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm text-gray-700">{progress.step}</span>
        <span className="text-xs text-gray-500">{percentage}%</span>
      </div>
      <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
        <div
          className="h-full bg-primary-600 rounded-full transition-all duration-300 ease-out"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <p className="text-xs text-gray-400 mt-1">
        {progress.current} of {progress.total}
      </p>
    </div>
  );
}

function ExtractedDataTable({ records, warnings }: { records: Record<string, unknown>[]; warnings: string[] }) {
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
            <tr className="bg-gray-50 border-b border-gray-200">
              {columns.map(col => (
                <th key={col} className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records.map((record, rowIndex) => (
              <tr key={rowIndex} className="border-b border-gray-100 last:border-b-0">
                {columns.map(col => (
                  <td key={col} className="px-3 py-2 text-gray-700 whitespace-nowrap">
                    {String(record[col] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const metaType = message.metadata?.type;

  // Loading state (empty assistant message)
  if (!isUser && !message.content && !metaType) {
    return (
      <div className="flex justify-start mb-4 px-4">
        <div className="max-w-[80%] bg-gray-50 rounded-2xl rounded-tl-sm px-4 py-3">
          <div className="flex items-center gap-1.5">
            <span className="typing-dot w-2 h-2 bg-gray-400 rounded-full inline-block" />
            <span className="typing-dot w-2 h-2 bg-gray-400 rounded-full inline-block" />
            <span className="typing-dot w-2 h-2 bg-gray-400 rounded-full inline-block" />
          </div>
        </div>
      </div>
    );
  }

  if (isSystem) {
    return (
      <div className="flex justify-center mb-4 px-4">
        <div className="bg-gray-100 text-gray-500 text-xs px-3 py-1.5 rounded-full">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className={clsx('flex mb-4 px-4', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={clsx(
          'max-w-[80%] rounded-2xl px-4 py-3 transition-all',
          isUser
            ? 'bg-primary-50 text-gray-900 rounded-tr-sm'
            : 'bg-gray-50 text-gray-900 rounded-tl-sm'
        )}
      >
        {/* User attachments */}
        {isUser && message.attachments && message.attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {message.attachments.map((att, i) => (
              <div key={i} className="flex items-center gap-1.5 bg-white/60 rounded-lg px-2 py-1 text-xs text-gray-600">
                {att.type === 'image' ? (
                  <img
                    src={`data:${att.mimeType};base64,${att.data}`}
                    alt={att.name}
                    className="w-16 h-16 object-cover rounded"
                  />
                ) : (
                  <span className="truncate max-w-[120px]">{att.name}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Message content */}
        {message.content && (
          <div>{isUser ? (
            <p className="text-sm whitespace-pre-wrap">{message.content}</p>
          ) : (
            renderMarkdown(message.content)
          )}</div>
        )}

        {/* Metadata-based rendering */}
        {metaType === 'progress' && message.metadata?.progress && (
          <ProgressIndicator progress={message.metadata.progress} />
        )}

        {metaType === 'voice_mapped' && message.metadata?.fields && message.metadata?.confidence && (
          <FieldMapping
            fields={message.metadata.fields}
            confidence={message.metadata.confidence}
          />
        )}

        {metaType === 'image_extracted' && (
          <ExtractedDataTable
            records={message.metadata?.records ?? []}
            warnings={message.metadata?.warnings ?? []}
          />
        )}

        {metaType === 'bundle_ready' && (
          <BundlePreview
            files={message.metadata?.bundleFiles}
            downloadUrl={message.metadata?.downloadUrl}
          />
        )}

        {metaType === 'rule' && message.metadata?.code && (
          <div className="mt-2">
            <CodeBlock code={message.metadata.code} language="javascript" />
          </div>
        )}

        {metaType === 'error' && (
          <div className="mt-2 flex items-start gap-2 bg-red-50 text-red-700 rounded-lg px-3 py-2 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{message.content}</span>
          </div>
        )}

        {/* Timestamp */}
        <div className={clsx(
          'text-xs mt-1.5',
          isUser ? 'text-primary-400' : 'text-gray-400'
        )}>
          {new Date(message.timestamp).toLocaleTimeString('en-IN', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>
    </div>
  );
}
