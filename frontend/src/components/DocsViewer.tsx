import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Search,
  X,
  BookOpen,
  ChevronDown,
  Copy,
  Check,
  Hash,
  Menu,
  Link as LinkIcon,
  Info,
  AlertTriangle,
  Lightbulb,
  AlertCircle,
  FileText,
  Settings,
  Code,
  Database,
  Rocket,
  Users,
  Shield,
  Wrench,
  Layers,
  Zap,
} from 'lucide-react';
import clsx from 'clsx';
import { useDebounce } from '../hooks/useDebounce';

// ─── Types ──────────────────────────────────────────────────────────────────

interface DocsViewerProps {
  onClose: () => void;
}

interface DocSection {
  id: string;
  title: string;
  level: number;
  content: string;
  subsections: DocSection[];
}

interface TOCHeading {
  id: string;
  text: string;
  level: number;
}

// ─── Utility Functions ──────────────────────────────────────────────────────

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .trim();
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function highlightMatch(text: string, query: string): string {
  if (!query) return escapeHtml(text);
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return escapeHtml(text).replace(
    new RegExp(`(${escaped})`, 'gi'),
    '<mark class="bg-amber-100 text-amber-900 rounded px-0.5 font-medium">$1</mark>'
  );
}

function highlightHtml(html: string, query: string): string {
  if (!query) return html;
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return html.replace(/(>[^<]*)/g, (segment) =>
    segment.replace(
      new RegExp(`(${escaped})`, 'gi'),
      '<mark class="bg-amber-100 text-amber-900 rounded px-0.5 font-medium">$1</mark>'
    )
  );
}

// ─── Section Icon Picker ────────────────────────────────────────────────────

const SECTION_ICONS: Record<string, typeof BookOpen> = {
  overview: BookOpen,
  introduction: BookOpen,
  'getting started': Rocket,
  setup: Settings,
  install: Settings,
  configuration: Settings,
  config: Settings,
  api: Code,
  code: Code,
  development: Code,
  database: Database,
  data: Database,
  users: Users,
  authentication: Shield,
  auth: Shield,
  security: Shield,
  tools: Wrench,
  architecture: Layers,
  performance: Zap,
  deployment: Rocket,
  document: FileText,
};

function getSectionIcon(title: string): typeof BookOpen {
  const lower = title.toLowerCase();
  for (const [key, icon] of Object.entries(SECTION_ICONS)) {
    if (lower.includes(key)) return icon;
  }
  return FileText;
}

// ─── Markdown Parser ────────────────────────────────────────────────────────

function parseMarkdownSections(markdown: string): DocSection[] {
  const lines = markdown.split('\n');
  const sections: DocSection[] = [];
  let currentSection: DocSection | null = null;
  let currentSubsection: DocSection | null = null;
  let contentBuffer: string[] = [];

  const flushContent = () => {
    const content = contentBuffer.join('\n').trim();
    if (currentSubsection) {
      currentSubsection.content = content;
    } else if (currentSection) {
      currentSection.content = content;
    }
    contentBuffer = [];
  };

  for (const line of lines) {
    const h2Match = line.match(/^## (\d+\.\s+)?(.+)/);
    const h3Match = line.match(/^### (\d+\.\d+\s+)?(.+)/);

    if (h2Match) {
      flushContent();
      if (currentSubsection && currentSection) {
        currentSection.subsections.push(currentSubsection);
        currentSubsection = null;
      }
      if (currentSection) {
        sections.push(currentSection);
      }
      const title = (h2Match[1] || '') + h2Match[2];
      currentSection = {
        id: slugify(title),
        title: title.replace(/^\d+\.\s+/, ''),
        level: 2,
        content: '',
        subsections: [],
      };
      currentSubsection = null;
    } else if (h3Match && currentSection) {
      flushContent();
      if (currentSubsection) {
        currentSection.subsections.push(currentSubsection);
      }
      const title = (h3Match[1] || '') + h3Match[2];
      currentSubsection = {
        id: slugify(title),
        title: title.replace(/^\d+\.\d+\s+/, ''),
        level: 3,
        content: '',
        subsections: [],
      };
    } else {
      contentBuffer.push(line);
    }
  }

  flushContent();
  if (currentSubsection && currentSection) {
    currentSection.subsections.push(currentSubsection);
  }
  if (currentSection) {
    sections.push(currentSection);
  }

  return sections;
}

// ─── Inline Markdown Renderer ───────────────────────────────────────────────

function renderInline(text: string): string {
  const segments: { type: 'text' | 'bold' | 'italic' | 'code' | 'link'; content: string; href?: string }[] = [];
  const regex = /(\*\*(.+?)\*\*)|(\*(.+?)\*)|(`([^`]+)`)|(\[([^\]]+)\]\(([^)]+)\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: 'text', content: text.slice(lastIndex, match.index) });
    }
    if (match[1]) segments.push({ type: 'bold', content: match[2] });
    else if (match[3]) segments.push({ type: 'italic', content: match[4] });
    else if (match[5]) segments.push({ type: 'code', content: match[6] });
    else if (match[7]) segments.push({ type: 'link', content: match[8], href: match[9] });
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    segments.push({ type: 'text', content: text.slice(lastIndex) });
  }

  return segments
    .map((s) => {
      const safe = escapeHtml(s.content);
      switch (s.type) {
        case 'bold':
          return `<strong class="font-semibold text-gray-900">${safe}</strong>`;
        case 'italic':
          return `<em class="text-gray-600">${safe}</em>`;
        case 'code':
          return `<code class="bg-slate-100 text-indigo-700 px-1.5 py-0.5 rounded text-[13px] font-mono border border-slate-200">${safe}</code>`;
        case 'link':
          return `<a href="${escapeHtml(s.href ?? '')}" class="text-indigo-600 hover:text-indigo-800 underline decoration-indigo-300 underline-offset-2 transition-colors" target="_blank" rel="noopener">${safe}</a>`;
        default:
          return safe;
      }
    })
    .join('');
}

// ─── Code Block ─────────────────────────────────────────────────────────────

// ─── Mermaid Diagram Renderer with Zoom + Fullscreen ────────────────────────

function MermaidDiagram({ chart }: { chart: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [zoom, setZoom] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);
  const idRef = useRef(`mermaid-${Math.random().toString(36).slice(2, 9)}`);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: 'default',
          securityLevel: 'loose',
          fontFamily: 'Inter, system-ui, sans-serif',
          themeVariables: {
            primaryColor: '#f0fdfa',
            primaryBorderColor: '#0d9488',
            primaryTextColor: '#111827',
            lineColor: '#6b7280',
            secondaryColor: '#f3f4f6',
            tertiaryColor: '#fef3c7',
          },
        });
        const { svg: rendered } = await mermaid.render(idRef.current, chart.trim());
        if (!cancelled) setSvg(rendered);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to render diagram');
      }
    })();
    return () => { cancelled = true; };
  }, [chart]);

  // Close fullscreen on Escape
  useEffect(() => {
    if (!fullscreen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFullscreen(false);
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [fullscreen]);

  // Reset zoom when toggling fullscreen
  useEffect(() => {
    if (fullscreen) setZoom(1);
  }, [fullscreen]);

  if (error) {
    return (
      <div className="my-4 p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
        <p className="font-medium mb-1">Diagram render error</p>
        <p className="text-xs">{error}</p>
        <pre className="mt-2 text-xs bg-red-100 p-2 rounded overflow-x-auto">{chart}</pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="my-4 p-8 bg-gray-50 border border-gray-200 rounded-lg flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-teal-600 border-t-transparent rounded-full animate-spin" />
        <span className="ml-3 text-sm text-gray-500">Rendering diagram...</span>
      </div>
    );
  }

  const zoomIn = () => setZoom(z => Math.min(z + 0.25, 3));
  const zoomOut = () => setZoom(z => Math.max(z - 0.25, 0.25));
  const resetZoom = () => setZoom(1);

  const toolbar = (
    <div className="flex items-center gap-1 bg-white border border-gray-200 rounded-lg shadow-sm px-1 py-0.5">
      <button onClick={zoomOut} className="p-1.5 rounded hover:bg-gray-100 text-gray-600 text-xs font-bold" title="Zoom out">−</button>
      <button onClick={resetZoom} className="px-2 py-1 rounded hover:bg-gray-100 text-xs text-gray-600 font-medium min-w-[3rem] text-center" title="Reset zoom">
        {Math.round(zoom * 100)}%
      </button>
      <button onClick={zoomIn} className="p-1.5 rounded hover:bg-gray-100 text-gray-600 text-xs font-bold" title="Zoom in">+</button>
      <div className="w-px h-5 bg-gray-200 mx-1" />
      <button
        onClick={() => setFullscreen(f => !f)}
        className="p-1.5 rounded hover:bg-gray-100 text-gray-600"
        title={fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
      >
        {fullscreen ? (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
        ) : (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5" /></svg>
        )}
      </button>
    </div>
  );

  const diagramContent = (
    <div
      className="overflow-auto"
      style={{ maxHeight: fullscreen ? 'calc(100vh - 80px)' : '600px' }}
    >
      <div
        ref={containerRef}
        className="flex justify-center transition-transform duration-200 origin-top-left [&_svg]:max-w-none"
        style={{ transform: `scale(${zoom})`, transformOrigin: 'center top' }}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </div>
  );

  // Fullscreen overlay
  if (fullscreen) {
    return (
      <>
        {/* Inline placeholder so content doesn't jump */}
        <div className="my-6 h-20 bg-gray-50 border border-gray-200 rounded-xl flex items-center justify-center text-sm text-gray-400">
          Viewing diagram in fullscreen
        </div>
        {/* Fullscreen modal */}
        <div className="fixed inset-0 z-[100] bg-white flex flex-col">
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 shrink-0">
            <span className="text-sm font-medium text-gray-700">Diagram</span>
            {toolbar}
          </div>
          <div className="flex-1 overflow-hidden p-4">
            {diagramContent}
          </div>
        </div>
      </>
    );
  }

  return (
    <div className="my-6 bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100 bg-gray-50">
        <span className="text-xs text-gray-500 font-medium">Diagram</span>
        {toolbar}
      </div>
      <div className="p-4">
        {diagramContent}
      </div>
    </div>
  );
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Basic keyword highlighting for common languages
  const highlightCode = (src: string, lang: string): string => {
    let escaped = escapeHtml(src);
    const keywords =
      lang === 'python' || lang === 'py'
        ? ['import', 'from', 'def', 'class', 'return', 'if', 'else', 'elif', 'for', 'while', 'try', 'except', 'with', 'as', 'in', 'not', 'and', 'or', 'True', 'False', 'None', 'async', 'await', 'yield']
        : lang === 'javascript' || lang === 'js' || lang === 'typescript' || lang === 'ts' || lang === 'tsx' || lang === 'jsx'
          ? ['import', 'from', 'export', 'default', 'const', 'let', 'var', 'function', 'return', 'if', 'else', 'for', 'while', 'class', 'new', 'this', 'true', 'false', 'null', 'undefined', 'async', 'await', 'throw', 'try', 'catch', 'typeof', 'interface', 'type', 'extends', 'implements']
          : lang === 'bash' || lang === 'sh' || lang === 'shell'
            ? ['sudo', 'cd', 'ls', 'mkdir', 'rm', 'cp', 'mv', 'echo', 'export', 'source', 'curl', 'wget', 'pip', 'npm', 'docker', 'git']
            : lang === 'sql'
              ? ['SELECT', 'FROM', 'WHERE', 'INSERT', 'INTO', 'UPDATE', 'DELETE', 'CREATE', 'TABLE', 'ALTER', 'DROP', 'INDEX', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'ON', 'AND', 'OR', 'NOT', 'NULL', 'VALUES', 'SET', 'ORDER', 'BY', 'GROUP', 'HAVING', 'LIMIT', 'AS']
              : [];

    if (keywords.length > 0) {
      // Highlight strings first
      escaped = escaped.replace(
        /(&quot;[^&]*?&quot;|&#039;[^&]*?&#039;|'[^']*?'|"[^"]*?")/g,
        '<span class="text-emerald-400">$1</span>'
      );
      // Highlight comments
      escaped = escaped.replace(
        /(#[^\n]*|\/\/[^\n]*)/g,
        '<span class="text-gray-500 italic">$1</span>'
      );
      // Highlight keywords (word boundary)
      for (const kw of keywords) {
        const re = new RegExp(`\\b(${kw})\\b`, 'g');
        escaped = escaped.replace(re, '<span class="text-purple-400 font-medium">$1</span>');
      }
      // Highlight numbers
      escaped = escaped.replace(
        /\b(\d+\.?\d*)\b/g,
        '<span class="text-amber-400">$1</span>'
      );
    }
    return escaped;
  };

  return (
    <div className="my-4 rounded-xl overflow-hidden border border-slate-700/50 shadow-sm">
      <div className="bg-slate-800 px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5">
            <span className="w-3 h-3 rounded-full bg-red-500/60" />
            <span className="w-3 h-3 rounded-full bg-yellow-500/60" />
            <span className="w-3 h-3 rounded-full bg-green-500/60" />
          </div>
          <span className="text-xs text-slate-400 font-mono ml-2">{language || 'text'}</span>
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors px-2 py-1 rounded hover:bg-slate-700"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-400" /> Copied
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" /> Copy
            </>
          )}
        </button>
      </div>
      <pre className="bg-slate-900 p-4 overflow-x-auto">
        <code
          className="text-[13px] text-slate-200 font-mono leading-relaxed whitespace-pre"
          dangerouslySetInnerHTML={{ __html: highlightCode(code, language) }}
        />
      </pre>
    </div>
  );
}

// ─── Callout / Admonition Box ───────────────────────────────────────────────

type CalloutType = 'note' | 'warning' | 'tip' | 'important';

const CALLOUT_STYLES: Record<CalloutType, { bg: string; border: string; icon: typeof Info; iconColor: string; titleColor: string }> = {
  note: { bg: 'bg-blue-50', border: 'border-blue-400', icon: Info, iconColor: 'text-blue-500', titleColor: 'text-blue-800' },
  warning: { bg: 'bg-amber-50', border: 'border-amber-400', icon: AlertTriangle, iconColor: 'text-amber-500', titleColor: 'text-amber-800' },
  tip: { bg: 'bg-emerald-50', border: 'border-emerald-400', icon: Lightbulb, iconColor: 'text-emerald-500', titleColor: 'text-emerald-800' },
  important: { bg: 'bg-red-50', border: 'border-red-400', icon: AlertCircle, iconColor: 'text-red-500', titleColor: 'text-red-800' },
};

function CalloutBox({ type, content, searchQuery }: { type: CalloutType; content: string; searchQuery: string }) {
  const style = CALLOUT_STYLES[type];
  const Icon = style.icon;
  return (
    <div className={clsx('my-4 rounded-lg border-l-4 p-4', style.bg, style.border)}>
      <div className="flex items-start gap-3">
        <Icon className={clsx('w-5 h-5 mt-0.5 shrink-0', style.iconColor)} />
        <div className="flex-1 min-w-0">
          <p className={clsx('text-sm font-semibold mb-1 capitalize', style.titleColor)}>{type}</p>
          <div className="text-sm text-gray-700 leading-relaxed">
            <span dangerouslySetInnerHTML={{ __html: highlightHtml(renderInline(content), searchQuery) }} />
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Heading with Anchor Link ───────────────────────────────────────────────

function HeadingWithAnchor({
  level,
  id,
  children,
  className,
}: {
  level: 2 | 3 | 4;
  id: string;
  children: React.ReactNode;
  className?: string;
}) {
  const [showCopied, setShowCopied] = useState(false);

  const handleCopyLink = (e: React.MouseEvent) => {
    e.preventDefault();
    const url = `${window.location.origin}${window.location.pathname}#${id}`;
    navigator.clipboard.writeText(url);
    setShowCopied(true);
    setTimeout(() => setShowCopied(false), 1500);
  };

  const Tag = level === 2 ? 'h2' : level === 3 ? 'h3' : 'h4';

  return (
    <Tag id={id} className={clsx('group relative scroll-mt-20', className)}>
      <span>{children}</span>
      <a
        href={`#${id}`}
        onClick={handleCopyLink}
        className="inline-flex items-center ml-2 opacity-0 group-hover:opacity-100 transition-opacity"
        aria-label="Copy link to section"
      >
        {showCopied ? (
          <Check className="w-4 h-4 text-emerald-500" />
        ) : (
          <LinkIcon className="w-4 h-4 text-gray-400 hover:text-indigo-500" />
        )}
      </a>
    </Tag>
  );
}

// ─── Markdown Content Renderer ──────────────────────────────────────────────

function MarkdownContent({ content, searchQuery }: { content: string; searchQuery: string }) {
  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeContent = '';
  let codeLang = '';
  let inTable = false;
  let tableRows: string[][] = [];
  let tableAligns: string[] = [];

  const flushTable = () => {
    if (tableRows.length > 0) {
      elements.push(
        <div key={`table-${elements.length}`} className="overflow-x-auto my-5 rounded-lg border border-gray-200 shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50/80 border-b border-gray-200">
                {tableRows[0].map((cell, i) => (
                  <th
                    key={i}
                    className="text-left px-4 py-3 font-semibold text-gray-700 whitespace-nowrap text-xs uppercase tracking-wide"
                  >
                    <span dangerouslySetInnerHTML={{ __html: highlightMatch(cell.trim(), searchQuery) }} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {tableRows.slice(1).map((row, ri) => (
                <tr
                  key={ri}
                  className={clsx(
                    'hover:bg-indigo-50/30 transition-colors',
                    ri % 2 === 1 && 'bg-gray-50/40'
                  )}
                >
                  {row.map((cell, ci) => (
                    <td
                      key={ci}
                      className={clsx(
                        'px-4 py-3 text-gray-600',
                        tableAligns[ci] === 'right' && 'text-right',
                        tableAligns[ci] === 'center' && 'text-center'
                      )}
                    >
                      <span dangerouslySetInnerHTML={{ __html: highlightHtml(renderInline(cell.trim()), searchQuery) }} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      tableRows = [];
      tableAligns = [];
      inTable = false;
    }
  };

  // Detect callout blockquotes: collect consecutive ">" lines then check
  const detectCallout = (text: string): { type: CalloutType; content: string } | null => {
    const calloutMatch = text.match(/^\s*\*\*(Note|Warning|Tip|Important):\*\*\s*(.*)/i);
    if (calloutMatch) {
      return {
        type: calloutMatch[1].toLowerCase() as CalloutType,
        content: calloutMatch[2],
      };
    }
    return null;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Code blocks
    if (line.trim().startsWith('```')) {
      if (inCodeBlock) {
        if (codeLang === 'mermaid') {
          elements.push(<MermaidDiagram key={`mermaid-${i}`} chart={codeContent.trimEnd()} />);
        } else {
          elements.push(<CodeBlock key={`code-${i}`} code={codeContent.trimEnd()} language={codeLang} />);
        }
        codeContent = '';
        codeLang = '';
        inCodeBlock = false;
      } else {
        flushTable();
        inCodeBlock = true;
        codeLang = line.trim().slice(3).trim();
      }
      continue;
    }
    if (inCodeBlock) {
      codeContent += (codeContent ? '\n' : '') + line;
      continue;
    }

    // Table rows
    const tableMatch = line.match(/^\|(.+)\|$/);
    if (tableMatch) {
      const cells = tableMatch[1].split('|');
      if (cells.every((c) => /^[\s:-]+$/.test(c))) {
        tableAligns = cells.map((c) => {
          if (c.trim().startsWith(':') && c.trim().endsWith(':')) return 'center';
          if (c.trim().endsWith(':')) return 'right';
          return 'left';
        });
        continue;
      }
      if (!inTable) inTable = true;
      tableRows.push(cells);
      continue;
    } else if (inTable) {
      flushTable();
    }

    // H4
    const h4Match = line.match(/^####\s+(.+)/);
    if (h4Match) {
      const h4Id = slugify(h4Match[1]);
      elements.push(
        <HeadingWithAnchor key={`h4-${i}`} level={4} id={h4Id} className="text-sm font-semibold text-gray-800 mt-6 mb-2">
          <span dangerouslySetInnerHTML={{ __html: highlightMatch(h4Match[1], searchQuery) }} />
        </HeadingWithAnchor>
      );
      continue;
    }

    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      elements.push(<hr key={`hr-${i}`} className="my-8 border-gray-200" />);
      continue;
    }

    // Blockquote (with callout detection)
    if (line.startsWith('>')) {
      // Collect all consecutive blockquote lines
      const bqLines: string[] = [];
      let j = i;
      while (j < lines.length && lines[j].startsWith('>')) {
        bqLines.push(lines[j].replace(/^>\s?/, ''));
        j++;
      }
      i = j - 1; // advance past consumed lines

      const fullText = bqLines.join(' ');
      const callout = detectCallout(fullText);

      if (callout) {
        elements.push(
          <CalloutBox key={`callout-${i}`} type={callout.type} content={callout.content} searchQuery={searchQuery} />
        );
      } else {
        elements.push(
          <blockquote
            key={`bq-${i}`}
            className="border-l-4 border-indigo-300 pl-4 py-2 my-4 text-sm text-gray-600 italic bg-indigo-50/30 rounded-r-lg"
          >
            <span dangerouslySetInnerHTML={{ __html: highlightHtml(renderInline(fullText), searchQuery) }} />
          </blockquote>
        );
      }
      continue;
    }

    // Unordered list
    const ulMatch = line.match(/^(\s*)[-*]\s+(.+)/);
    if (ulMatch) {
      const indent = Math.floor(ulMatch[1].length / 2);
      elements.push(
        <div key={`ul-${i}`} className="flex items-start gap-2.5 my-0.5" style={{ paddingLeft: `${indent * 20 + 8}px` }}>
          <span className="text-indigo-400 mt-[7px] shrink-0 text-[8px]">{indent === 0 ? '\u25CF' : '\u25CB'}</span>
          <span
            className="text-[15px] text-gray-700 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: highlightHtml(renderInline(ulMatch[2]), searchQuery) }}
          />
        </div>
      );
      continue;
    }

    // Ordered list
    const olMatch = line.match(/^(\s*)(\d+)\.\s+(.+)/);
    if (olMatch) {
      const indent = Math.floor(olMatch[1].length / 2);
      elements.push(
        <div key={`ol-${i}`} className="flex items-start gap-2.5 my-0.5" style={{ paddingLeft: `${indent * 20 + 8}px` }}>
          <span className="text-indigo-600 font-semibold text-sm mt-0.5 shrink-0 w-5 text-right">{olMatch[2]}.</span>
          <span
            className="text-[15px] text-gray-700 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: highlightHtml(renderInline(olMatch[3]), searchQuery) }}
          />
        </div>
      );
      continue;
    }

    // Empty lines
    if (line.trim() === '') continue;

    // Regular paragraph
    elements.push(
      <p key={`p-${i}`} className="text-[15px] text-gray-700 my-2 leading-[1.8]">
        <span dangerouslySetInnerHTML={{ __html: highlightHtml(renderInline(line), searchQuery) }} />
      </p>
    );
  }

  flushTable();
  if (inCodeBlock && codeContent) {
    if (codeLang === 'mermaid') {
      elements.push(<MermaidDiagram key="mermaid-final" chart={codeContent.trimEnd()} />);
    } else {
      elements.push(<CodeBlock key="code-final" code={codeContent.trimEnd()} language={codeLang} />);
    }
  }

  return <>{elements}</>;
}

// ─── Scroll-Spy Table of Contents ───────────────────────────────────────────

function ScrollSpyTOC({
  headings,
  activeId,
}: {
  headings: TOCHeading[];
  activeId: string;
}) {
  if (headings.length === 0) return null;

  const scrollToHeading = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <nav className="space-y-0.5">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3 px-2">On this page</p>
      {headings.map((h) => (
        <button
          key={h.id}
          onClick={() => scrollToHeading(h.id)}
          className={clsx(
            'block w-full text-left text-[13px] py-1 px-2 rounded transition-all duration-150 leading-snug',
            h.level === 3 && 'pl-5',
            activeId === h.id
              ? 'text-indigo-700 font-medium bg-indigo-50 border-l-2 border-indigo-500 -ml-px'
              : 'text-gray-500 hover:text-gray-800 hover:bg-gray-50'
          )}
        >
          {h.text}
        </button>
      ))}
    </nav>
  );
}

// ─── Breadcrumb ─────────────────────────────────────────────────────────────

function Breadcrumb({ items }: { items: string[] }) {
  return (
    <div className="flex items-center gap-1.5 text-xs text-gray-400 mb-6">
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight className="w-3 h-3 text-gray-300" />}
          <span className={i === items.length - 1 ? 'text-gray-700 font-medium' : 'hover:text-gray-600 cursor-default'}>
            {item}
          </span>
        </span>
      ))}
    </div>
  );
}

// ─── Mobile Nav Drawer Overlay ──────────────────────────────────────────────

function NavDrawerOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 lg:hidden" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" />
    </div>
  );
}

// ─── Main DocsViewer ────────────────────────────────────────────────────────

export function DocsViewer({ onClose }: DocsViewerProps) {
  const [markdown, setMarkdown] = useState('');
  const [loading, setLoading] = useState(true);
  const [sections, setSections] = useState<DocSection[]>([]);
  const [activeSection, setActiveSection] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedNav, setExpandedNav] = useState<Set<string>>(new Set());
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [activeTOCId, setActiveTOCId] = useState('');
  const contentRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const debouncedQuery = useDebounce(searchQuery, 250);

  // Fetch markdown
  useEffect(() => {
    fetch('/docs/platform.md')
      .then((r) => r.text())
      .then((text) => {
        setMarkdown(text);
        const parsed = parseMarkdownSections(text);
        setSections(parsed);
        setLoading(false);
        if (parsed.length > 0) {
          setExpandedNav(new Set([parsed[0].id]));
        }
      })
      .catch(() => setLoading(false));
  }, []);

  // Extract TOC headings for current section
  const tocHeadings = useMemo((): TOCHeading[] => {
    const section = sections[activeSection];
    if (!section) return [];
    const headings: TOCHeading[] = [];
    // The section title itself
    headings.push({ id: `section-${section.id}`, text: section.title, level: 2 });
    // Subsections
    for (const sub of section.subsections) {
      headings.push({ id: `sub-${sub.id}`, text: sub.title, level: 3 });
    }
    return headings;
  }, [sections, activeSection]);

  // Scroll-spy: IntersectionObserver
  useEffect(() => {
    if (tocHeadings.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        // Find the topmost visible heading
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length > 0) {
          // Pick the one closest to the top
          const top = visible.reduce((a, b) =>
            a.boundingClientRect.top < b.boundingClientRect.top ? a : b
          );
          setActiveTOCId(top.target.id);
        }
      },
      {
        root: contentRef.current,
        rootMargin: '-80px 0px -60% 0px',
        threshold: 0,
      }
    );

    // Observe all heading elements
    for (const h of tocHeadings) {
      const el = document.getElementById(h.id);
      if (el) observer.observe(el);
    }

    return () => observer.disconnect();
  }, [tocHeadings]);

  // Search results
  const searchResults = useMemo(() => {
    if (!debouncedQuery.trim()) return null;
    const q = debouncedQuery.toLowerCase();
    const results: { sectionIndex: number; section: DocSection; matches: string[] }[] = [];

    sections.forEach((section, idx) => {
      const allContent = [section.title, section.content, ...section.subsections.map((s) => s.title + '\n' + s.content)].join('\n');
      if (allContent.toLowerCase().includes(q)) {
        const matchLines = allContent
          .split('\n')
          .filter((line) => line.toLowerCase().includes(q))
          .slice(0, 3)
          .map((line) => line.trim().slice(0, 120));
        results.push({ sectionIndex: idx, section, matches: matchLines });
      }
    });
    return results;
  }, [sections, debouncedQuery]);

  const goToSection = useCallback(
    (index: number) => {
      setActiveSection(index);
      setSearchQuery('');
      setMobileNavOpen(false);
      contentRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
      if (sections[index]) {
        setExpandedNav((prev) => new Set(prev).add(sections[index].id));
      }
    },
    [sections]
  );

  const toggleNavExpand = useCallback((sectionId: string) => {
    setExpandedNav((prev) => {
      const next = new Set(prev);
      if (next.has(sectionId)) next.delete(sectionId);
      else next.add(sectionId);
      return next;
    });
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (searchQuery) setSearchQuery('');
        else if (mobileNavOpen) setMobileNavOpen(false);
        else onClose();
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
      if (e.altKey && e.key === 'ArrowLeft' && activeSection > 0) {
        goToSection(activeSection - 1);
      }
      if (e.altKey && e.key === 'ArrowRight' && activeSection < sections.length - 1) {
        goToSection(activeSection + 1);
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [searchQuery, onClose, activeSection, sections.length, goToSection, mobileNavOpen]);

  const currentSection = sections[activeSection];

  // Build breadcrumb
  const breadcrumbItems = useMemo(() => {
    const items = ['Documentation'];
    if (currentSection) {
      items.push(currentSection.title);
    }
    return items;
  }, [currentSection]);

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center h-full bg-white">
        <div className="text-center">
          <div className="w-10 h-10 border-2 border-indigo-600 border-t-transparent rounded-full spinner mx-auto mb-4" />
          <p className="text-sm text-gray-500 font-medium">Loading documentation...</p>
        </div>
      </div>
    );
  }

  // ─── Sidebar Content (shared between desktop and mobile drawer) ─────────

  const sidebarContent = (
    <>
      {/* Sidebar Header */}
      <div className="p-4 border-b border-gray-200/80 shrink-0">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center">
              <BookOpen className="w-4 h-4 text-white" />
            </div>
            <div>
              <span className="font-semibold text-gray-900 text-sm block leading-tight">Avni AI Docs</span>
              <span className="text-[11px] text-gray-400">Platform Guide</span>
            </div>
          </div>
          {/* Close button on mobile */}
          <button
            onClick={() => setMobileNavOpen(false)}
            className="lg:hidden p-1.5 rounded-md hover:bg-gray-100"
          >
            <X className="w-4 h-4 text-gray-500" />
          </button>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search..."
            className="w-full pl-9 pr-16 py-2 text-sm bg-gray-100 border border-transparent rounded-lg text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent focus:bg-white transition-all"
          />
          <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
            {searchQuery ? (
              <button onClick={() => setSearchQuery('')} className="p-1 rounded hover:bg-gray-200">
                <X className="w-3.5 h-3.5 text-gray-400" />
              </button>
            ) : (
              <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] text-gray-400 bg-gray-200/80 rounded border border-gray-300/50 font-mono">
                <span className="text-[11px]">{navigator.platform.includes('Mac') ? '\u2318' : 'Ctrl'}</span>K
              </kbd>
            )}
          </div>
        </div>
      </div>

      {/* Search Results */}
      {searchResults ? (
        <div className="flex-1 overflow-y-auto p-3">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider px-2 mb-3">
            {searchResults.length} result{searchResults.length !== 1 ? 's' : ''} found
          </p>
          {searchResults.length === 0 ? (
            <div className="text-center py-10">
              <Search className="w-8 h-8 text-gray-300 mx-auto mb-3" />
              <p className="text-sm text-gray-400">No results for &ldquo;{debouncedQuery}&rdquo;</p>
            </div>
          ) : (
            <div className="space-y-1">
              {searchResults.map((r) => (
                <button
                  key={r.sectionIndex}
                  onClick={() => goToSection(r.sectionIndex)}
                  className="w-full text-left p-3 rounded-lg hover:bg-indigo-50 transition-colors group border border-transparent hover:border-indigo-100"
                >
                  <p className="text-sm font-medium text-gray-800 group-hover:text-indigo-700 flex items-center gap-2">
                    <Hash className="w-3.5 h-3.5 text-gray-400 group-hover:text-indigo-500 shrink-0" />
                    {r.section.title}
                  </p>
                  {r.matches.map((m, mi) => (
                    <p
                      key={mi}
                      className="text-xs text-gray-500 mt-1 truncate pl-5.5"
                      dangerouslySetInnerHTML={{ __html: highlightMatch(m, debouncedQuery) }}
                    />
                  ))}
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        /* Nav Tree */
        <nav className="flex-1 overflow-y-auto py-3 px-2">
          <div className="space-y-px">
            {sections.map((section, idx) => {
              const Icon = getSectionIcon(section.title);
              const isActive = idx === activeSection;
              return (
                <div key={section.id}>
                  <div className="flex items-center">
                    {section.subsections.length > 0 ? (
                      <button
                        onClick={() => toggleNavExpand(section.id)}
                        className="p-1 rounded-md hover:bg-gray-200 transition-colors mr-0.5 shrink-0"
                      >
                        <ChevronDown
                          className={clsx(
                            'w-3.5 h-3.5 text-gray-400 transition-transform duration-200',
                            !expandedNav.has(section.id) && '-rotate-90'
                          )}
                        />
                      </button>
                    ) : (
                      <span className="w-6 shrink-0" />
                    )}
                    <button
                      onClick={() => goToSection(idx)}
                      className={clsx(
                        'flex-1 flex items-center gap-2 text-left px-2.5 py-2 text-sm rounded-lg transition-all duration-150',
                        isActive
                          ? 'bg-indigo-50 text-indigo-700 font-medium shadow-sm shadow-indigo-100'
                          : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                      )}
                    >
                      <Icon className={clsx('w-4 h-4 shrink-0', isActive ? 'text-indigo-500' : 'text-gray-400')} />
                      <span className="truncate">{section.title}</span>
                    </button>
                  </div>

                  {/* Subsections */}
                  {expandedNav.has(section.id) && section.subsections.length > 0 && (
                    <div className="ml-7 mt-0.5 space-y-px border-l-2 border-gray-100 pl-2">
                      {section.subsections.map((sub) => (
                        <button
                          key={sub.id}
                          onClick={() => {
                            goToSection(idx);
                            setTimeout(() => {
                              const el = document.getElementById(`sub-${sub.id}`);
                              el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                            }, 100);
                          }}
                          className="w-full text-left px-2.5 py-1.5 text-[13px] text-gray-500 hover:text-indigo-600 hover:bg-indigo-50/50 rounded-md transition-colors truncate"
                        >
                          {sub.title}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </nav>
      )}

      {/* Footer */}
      <div className="px-4 py-3 border-t border-gray-200/80 shrink-0">
        <p className="text-[11px] text-gray-400 text-center">
          {sections.length} sections &middot; {Math.round(markdown.length / 1000)}K characters
        </p>
      </div>
    </>
  );

  // ─── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full bg-white">
      {/* Mobile drawer overlay */}
      <NavDrawerOverlay open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />

      {/* Left Sidebar — Desktop: always visible, Mobile: slide-out drawer */}
      <aside
        className={clsx(
          'h-full bg-gray-50/80 border-r border-gray-200 flex flex-col shrink-0',
          // Desktop
          'hidden lg:flex lg:w-[260px]',
          // Mobile: positioned as drawer
          mobileNavOpen &&
            'fixed inset-y-0 left-0 z-50 flex w-[300px] shadow-2xl lg:static lg:shadow-none lg:z-auto'
        )}
        style={mobileNavOpen ? { display: 'flex' } : undefined}
      >
        {sidebarContent}
      </aside>

      {/* Center + Right Panel Container */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Bar */}
        <div className="h-14 border-b border-gray-200 flex items-center px-4 shrink-0 gap-2 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
          {/* Mobile hamburger */}
          <button
            onClick={() => setMobileNavOpen(true)}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors lg:hidden"
            aria-label="Open navigation"
          >
            <Menu className="w-5 h-5 text-gray-600" />
          </button>

          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
            aria-label="Back to chat"
          >
            <ArrowLeft className="w-5 h-5 text-gray-600" />
          </button>

          <div className="h-6 w-px bg-gray-200 mx-1" />

          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-semibold text-gray-900 truncate">
              {currentSection?.title || 'Documentation'}
            </h1>
            <p className="text-[11px] text-gray-400">
              Section {activeSection + 1} of {sections.length}
            </p>
          </div>

          {/* Pagination */}
          <div className="flex items-center gap-0.5">
            <button
              onClick={() => goToSection(activeSection - 1)}
              disabled={activeSection === 0}
              className={clsx(
                'p-2 rounded-lg transition-colors',
                activeSection === 0
                  ? 'text-gray-300 cursor-not-allowed'
                  : 'text-gray-600 hover:bg-gray-100'
              )}
              aria-label="Previous section"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <span className="text-xs text-gray-500 min-w-[44px] text-center font-mono tabular-nums">
              {activeSection + 1}/{sections.length}
            </span>
            <button
              onClick={() => goToSection(activeSection + 1)}
              disabled={activeSection >= sections.length - 1}
              className={clsx(
                'p-2 rounded-lg transition-colors',
                activeSection >= sections.length - 1
                  ? 'text-gray-300 cursor-not-allowed'
                  : 'text-gray-600 hover:bg-gray-100'
              )}
              aria-label="Next section"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content + TOC Layout */}
        <div className="flex-1 flex min-h-0">
          {/* Center Content Area */}
          <div
            ref={contentRef}
            className="flex-1 overflow-y-auto"
            onClick={(e) => {
              // Intercept clicks on internal anchor links and navigate to the correct section
              const target = e.target as HTMLElement;
              const anchor = target.closest('a');
              if (!anchor) return;
              const href = anchor.getAttribute('href') || '';
              // Handle internal hash links by finding the matching section
              if (href.startsWith('#')) {
                e.preventDefault();
                const slug = href.slice(1).toLowerCase();
                const idx = sections.findIndex(
                  (s) => slugify(s.title) === slug || s.id === slug
                );
                if (idx >= 0) goToSection(idx);
              }
            }}
          >
            <div className="max-w-3xl mx-auto px-6 sm:px-10 py-8 sm:py-10">
              {currentSection && (
                <article className="fade-in">
                  {/* Breadcrumb */}
                  <Breadcrumb items={breadcrumbItems} />

                  {/* Section header */}
                  <HeadingWithAnchor
                    level={2}
                    id={`section-${currentSection.id}`}
                    className="text-3xl font-bold text-gray-900 mb-2 tracking-tight"
                  >
                    {currentSection.title}
                  </HeadingWithAnchor>

                  {/* Thin accent line under title */}
                  <div className="w-12 h-1 bg-indigo-500 rounded-full mb-8" />

                  {/* Section content */}
                  {currentSection.content && (
                    <MarkdownContent content={currentSection.content} searchQuery={debouncedQuery} />
                  )}

                  {/* Subsections */}
                  {currentSection.subsections.map((sub) => (
                    <div key={sub.id} id={`sub-${sub.id}`} className="mt-10">
                      <HeadingWithAnchor
                        level={3}
                        id={`sub-${sub.id}`}
                        className="text-xl font-semibold text-gray-800 mb-4 pb-2 border-b border-gray-100"
                      >
                        {sub.title}
                      </HeadingWithAnchor>
                      <MarkdownContent content={sub.content} searchQuery={debouncedQuery} />
                    </div>
                  ))}
                </article>
              )}

              {/* Bottom Prev/Next Navigation */}
              <div className="mt-12 pt-8 border-t border-gray-200 grid grid-cols-2 gap-4">
                {activeSection > 0 ? (
                  <button
                    onClick={() => goToSection(activeSection - 1)}
                    className="flex items-center gap-3 p-4 text-left rounded-xl border border-gray-200 hover:border-indigo-300 hover:bg-indigo-50/30 transition-all group"
                  >
                    <ChevronLeft className="w-5 h-5 text-gray-400 group-hover:text-indigo-500 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Previous</p>
                      <p className="text-sm font-semibold text-gray-700 group-hover:text-indigo-700 truncate">
                        {sections[activeSection - 1]?.title}
                      </p>
                    </div>
                  </button>
                ) : (
                  <div />
                )}

                {activeSection < sections.length - 1 ? (
                  <button
                    onClick={() => goToSection(activeSection + 1)}
                    className="flex items-center justify-end gap-3 p-4 text-right rounded-xl border border-gray-200 hover:border-indigo-300 hover:bg-indigo-50/30 transition-all group"
                  >
                    <div className="min-w-0">
                      <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Next</p>
                      <p className="text-sm font-semibold text-gray-700 group-hover:text-indigo-700 truncate">
                        {sections[activeSection + 1]?.title}
                      </p>
                    </div>
                    <ChevronRight className="w-5 h-5 text-gray-400 group-hover:text-indigo-500 shrink-0" />
                  </button>
                ) : (
                  <div />
                )}
              </div>

              {/* Bottom spacer */}
              <div className="h-16" />
            </div>
          </div>

          {/* Right TOC Sidebar (desktop only, xl+) */}
          <aside className="hidden xl:block w-[200px] shrink-0 border-l border-gray-100">
            <div className="sticky top-14 p-4 pt-8 max-h-[calc(100vh-56px)] overflow-y-auto">
              <ScrollSpyTOC headings={tocHeadings} activeId={activeTOCId} />
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
