import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({
  gfm: true,
  breaks: true,
})

/**
 * Markdown → 安全 HTML（助手消息渲染用；GFM 表格需开启）。
 * DOMPurify 防 XSS；用户气泡勿走此函数。
 * @param {string} text
 * @returns {string}
 */
export function renderMarkdown(text) {
  const raw = typeof text === 'string' ? text : ''
  if (!raw.trim()) return ''
  const html = marked.parse(raw, { async: false })
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
  })
}
