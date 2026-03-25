import { useMemo, useState, memo, lazy, Suspense } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, Check } from 'lucide-react';

// Lazy-load syntax highlighter — ~800KB, only needed when code blocks appear
const LazySyntaxHighlighter = lazy(async () => {
  const [{ default: SyntaxHighlighter }, { default: oneDark }, ...languages] = await Promise.all([
    import('react-syntax-highlighter/dist/esm/prism-light'),
    import('react-syntax-highlighter/dist/esm/styles/prism/one-dark'),
    import('react-syntax-highlighter/dist/esm/languages/prism/javascript'),
    import('react-syntax-highlighter/dist/esm/languages/prism/typescript'),
    import('react-syntax-highlighter/dist/esm/languages/prism/python'),
    import('react-syntax-highlighter/dist/esm/languages/prism/json'),
    import('react-syntax-highlighter/dist/esm/languages/prism/bash'),
    import('react-syntax-highlighter/dist/esm/languages/prism/sql'),
    import('react-syntax-highlighter/dist/esm/languages/prism/css'),
    import('react-syntax-highlighter/dist/esm/languages/prism/markup'),
  ]);

  const langNames = ['javascript', 'typescript', 'python', 'json', 'bash', 'sql', 'css', 'markup'];
  languages.forEach((lang, i) => {
    SyntaxHighlighter.registerLanguage(langNames[i], lang.default);
  });

  // Return a wrapper component that applies oneDark style
  return {
    default: ({ language, children }: { language: string; children: string }) => (
      <SyntaxHighlighter
        style={oneDark}
        language={language || 'text'}
        PreTag="div"
        customStyle={{ margin: 0, borderRadius: 0, fontSize: '0.75rem' }}
      >
        {children}
      </SyntaxHighlighter>
    ),
  };
});

interface MessageContentProps {
  content: string;
  isUser: boolean;
}

function CodeBlockWithCopy({ language, children }: { language: string; children: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(children);
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
      <Suspense
        fallback={
          <pre className="bg-gray-900 text-gray-300 p-3 text-xs font-mono overflow-x-auto">
            <code>{children}</code>
          </pre>
        }
      >
        <LazySyntaxHighlighter language={language}>{children}</LazySyntaxHighlighter>
      </Suspense>
    </div>
  );
}

export const MessageContent = memo(function MessageContent({ content, isUser }: MessageContentProps) {
  const rendered = useMemo(() => {
    if (!content) return null;

    if (isUser) {
      return <p className="text-sm whitespace-pre-wrap">{content}</p>;
    }

    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Headings
          h1: ({ children }) => <h1 className="text-lg font-semibold text-gray-900 mt-3 mb-1">{children}</h1>,
          h2: ({ children }) => <h2 className="text-base font-semibold text-gray-900 mt-2 mb-1">{children}</h2>,
          h3: ({ children }) => <h3 className="text-sm font-semibold text-gray-900 mt-2 mb-0.5">{children}</h3>,
          h4: ({ children }) => <h4 className="text-sm font-semibold text-gray-900 mt-1">{children}</h4>,

          // Paragraphs
          p: ({ children }) => <p className="text-sm text-gray-900 my-1" style={{ lineHeight: '1.6' }}>{children}</p>,

          // Lists
          ul: ({ children }) => <ul className="my-1 pl-5 list-disc text-sm text-gray-900 space-y-0.5">{children}</ul>,
          ol: ({ children }) => <ol className="my-1 pl-5 list-decimal text-sm text-gray-900 space-y-0.5">{children}</ol>,
          li: ({ children }) => <li className="py-0.5" style={{ lineHeight: '1.6' }}>{children}</li>,

          // Inline code
          code: ({ className, children, ...props }) => {
            const match = /language-(\w+)/.exec(className || '');
            const codeString = String(children).replace(/\n$/, '');

            // Block code (has language class from ```)
            if (match) {
              return <CodeBlockWithCopy language={match[1]}>{codeString}</CodeBlockWithCopy>;
            }

            // Inline code
            return (
              <code className="bg-gray-100 text-teal-700 px-1 py-0.5 rounded text-xs font-mono" {...props}>
                {children}
              </code>
            );
          },

          // Pre — handle fenced code blocks without language
          pre: ({ children }) => {
            // react-markdown wraps code blocks in <pre><code>
            // If the code element already rendered a CodeBlockWithCopy, just pass through
            const child = children as React.ReactElement;
            if (child?.props?.className && /language-/.test(child.props.className)) {
              return <>{children}</>;
            }
            // Fenced code block without language
            const codeText = String(child?.props?.children || '').replace(/\n$/, '');
            return <CodeBlockWithCopy language="">{codeText}</CodeBlockWithCopy>;
          },

          // Tables with borders and zebra striping
          table: ({ children }) => (
            <div className="overflow-x-auto rounded-lg border border-gray-200 my-2">
              <table className="w-full text-sm">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-gray-100 border-b border-gray-200">{children}</thead>,
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => (
            <tr className="border-b border-gray-100 last:border-b-0 even:bg-gray-50">{children}</tr>
          ),
          th: ({ children }) => (
            <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap text-xs">{children}</th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-2 text-gray-900 whitespace-nowrap text-xs">{children}</td>
          ),

          // Block quote
          blockquote: ({ children }) => (
            <blockquote className="border-l-3 border-gray-300 pl-3 my-2 text-gray-600 italic">{children}</blockquote>
          ),

          // Horizontal rule
          hr: () => <hr className="my-3 border-gray-200" />,

          // Strong and emphasis
          strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
          em: ({ children }) => <em>{children}</em>,

          // Links
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-teal-700 underline hover:text-teal-900 transition-colors"
            >
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    );
  }, [content, isUser]);

  if (!rendered) return null;
  return <div>{rendered}</div>;
});
