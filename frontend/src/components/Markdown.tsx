// 讨论报告 / 三视角全文的 Markdown 渲染：react-markdown + remark-gfm。
// react-markdown 渲染为 React 元素而非 HTML 字符串，默认转义原始 HTML，天然防注入。
// 支持 CommonMark + GFM（表格、删除线、任务列表），覆盖讨论报告的实际输出。

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function Markdown({ text, className = "" }: { text: string; className?: string }) {
  return (
    <div className={`md ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}
