import type { ComponentPropsWithoutRef } from 'react';
import ReactMarkdown, { type Components, type Options } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { safeHttpUrl } from './sources';

// Bot answers in Markdown (GitHub flavour: lists, tables, links, code) with
// formulas in $$...$$ (KaTeX). Model output is not trusted: raw HTML is
// dropped, only http(s) links survive and images are never loaded - an image
// URL from the model could track the reader, so its alt text is shown instead.

// "$" alone is common in Polish text (prices, shell snippets), so only $$...$$ is math.
const REMARK_PLUGINS: Options['remarkPlugins'] = [remarkGfm, [remarkMath, { singleDollarTextMath: false }]];
// broken TeX shows as text in the error colour instead of throwing
const REHYPE_PLUGINS: Options['rehypePlugins'] = [[rehypeKatex, { throwOnError: false, strict: false }]];

function Link({ href, children }: ComponentPropsWithoutRef<'a'>) {
  const url = safeHttpUrl(href ?? null);
  if (url === null) return <>{children}</>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="ksi-link break-words">
      {children}
    </a>
  );
}

function Image({ alt }: ComponentPropsWithoutRef<'img'>) {
  return alt ? <span className="italic text-muted">[{alt}]</span> : null;
}

// Tailwind has no typography plugin here - each element gets the chat's own tokens.
const COMPONENTS: Components = {
  a: Link,
  img: Image,
  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
  h1: ({ children }) => <h3 className="mt-3 mb-1.5 first:mt-0 font-head text-base font-semibold">{children}</h3>,
  h2: ({ children }) => <h3 className="mt-3 mb-1.5 first:mt-0 font-head text-base font-semibold">{children}</h3>,
  h3: ({ children }) => <h4 className="mt-3 mb-1 first:mt-0 font-head text-sm font-semibold">{children}</h4>,
  h4: ({ children }) => <h4 className="mt-3 mb-1 first:mt-0 text-sm font-semibold">{children}</h4>,
  ul: ({ children }) => <ul className="my-2 pl-5 list-disc space-y-1 first:mt-0 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 pl-5 list-decimal space-y-1 first:mt-0 last:mb-0">{children}</ol>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-line-strong pl-3 text-muted">{children}</blockquote>
  ),
  hr: () => <hr className="my-3 border-line" />,
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded-control border border-line bg-surface-sunken p-3 text-xs leading-relaxed">
      {children}
    </pre>
  ),
  code: ({ className, children }) => (
    // fenced code gets a language-* class and sits inside <pre>; inline code gets a chip
    <code className={className ? 'font-mono' : 'rounded-[3px] bg-surface-sunken px-1 py-0.5 font-mono text-[0.85em]'}>
      {children}
    </code>
  ),
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="w-full border-collapse text-left text-[13px]">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border border-line bg-surface-sunken px-2 py-1 font-semibold">{children}</th>,
  td: ({ children }) => <td className="border border-line px-2 py-1 align-top">{children}</td>,
};

interface MarkdownTextProps {
  text: string;
}

export default function MarkdownText({ text }: MarkdownTextProps) {
  return (
    <div className="ksi-markdown min-w-0 break-words">
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
        components={COMPONENTS}
        skipHtml
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
