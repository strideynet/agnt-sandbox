import ReactMarkdown from 'react-markdown';

interface MarkdownProps {
  children: string;
  className?: string;
}

export function Markdown({ children, className = '' }: MarkdownProps) {
  return (
    <div className={`prose prose-sm max-w-none ${className}`}>
      <ReactMarkdown
        components={{
          // Style code blocks
          pre: ({ children }) => (
            <pre className="bg-gray-900 text-gray-100 rounded p-3 overflow-x-auto text-xs">
              {children}
            </pre>
          ),
          code: ({ children, className }) => {
            // Inline code vs block code
            const isBlock = className?.includes('language-');
            if (isBlock) {
              return <code className="text-green-400">{children}</code>;
            }
            return (
              <code className="bg-gray-200 text-gray-800 px-1 py-0.5 rounded text-xs">
                {children}
              </code>
            );
          },
          // Style headings
          h1: ({ children }) => (
            <h1 className="text-xl font-bold mt-4 mb-2">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-lg font-bold mt-3 mb-2">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-base font-bold mt-2 mb-1">{children}</h3>
          ),
          // Style lists
          ul: ({ children }) => (
            <ul className="list-disc pl-5 space-y-1">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-5 space-y-1">{children}</ol>
          ),
          // Style paragraphs
          p: ({ children }) => <p className="mb-2">{children}</p>,
          // Style links
          a: ({ children, href }) => (
            <a
              href={href}
              className="text-blue-600 hover:underline"
              target="_blank"
              rel="noopener noreferrer"
            >
              {children}
            </a>
          ),
          // Style blockquotes
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-gray-300 pl-4 italic text-gray-600">
              {children}
            </blockquote>
          ),
          // Style tables
          table: ({ children }) => (
            <table className="border-collapse border border-gray-300 w-full text-sm">
              {children}
            </table>
          ),
          th: ({ children }) => (
            <th className="border border-gray-300 px-2 py-1 bg-gray-100 font-semibold text-left">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-gray-300 px-2 py-1">{children}</td>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
