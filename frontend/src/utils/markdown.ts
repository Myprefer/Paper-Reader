import { marked } from 'marked';
import katex from 'katex';
import hljs from 'highlight.js';

/**
 * Render Markdown string to HTML with KaTeX math support.
 * Handles $$...$$ (display) and $...$ (inline) math blocks.
 */
export function renderMarkdown(src: string): string {
  if (!src || !src.trim()) {
    return '<div class="empty-state"><div class="text">暂无笔记内容，点击 ✏️ 编辑 开始撰写</div></div>';
  }

  const mathBlocks: { math: string; display: boolean }[] = [];
  let processed = src;

  // Block math: $$...$$
  processed = processed.replace(/\$\$([\s\S]*?)\$\$/g, (_, math: string) => {
    const i = mathBlocks.length;
    mathBlocks.push({ math: math.trim(), display: true });
    return `%%MATHBLOCK${i}%%`;
  });

  // Inline math: $...$
  processed = processed.replace(/\$([^\$\n]+?)\$/g, (_, math: string) => {
    const i = mathBlocks.length;
    mathBlocks.push({ math: math.trim(), display: false });
    return `%%MATHBLOCK${i}%%`;
  });

  marked.setOptions({ breaks: true, gfm: true });
  let html = marked.parse(processed) as string;

  // Restore math blocks → KaTeX
  html = html.replace(/%%MATHBLOCK(\d+)%%/g, (_, idx: string) => {
    const { math, display } = mathBlocks[parseInt(idx)];
    try {
      return katex.renderToString(math, { displayMode: display, throwOnError: false });
    } catch {
      return `<code class="math-error">${math}</code>`;
    }
  });

  return html;
}

/**
 * Apply highlight.js to all <pre><code> blocks in a container.
 */
export function highlightCodeBlocks(container: HTMLElement): void {
  container.querySelectorAll('pre code').forEach((block) => {
    hljs.highlightElement(block as HTMLElement);
  });
}
