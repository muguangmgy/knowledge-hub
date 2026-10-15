import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({
  gfm: true,
  breaks: true,
})

// 外链新开标签页；DOMPurify 默认会去掉 target，需显式放行
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName !== 'A') return
  const href = node.getAttribute('href') || ''
  if (/^https?:\/\//i.test(href) || href.startsWith('//')) {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
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
    ADD_ATTR: ['target'],
  })
}
