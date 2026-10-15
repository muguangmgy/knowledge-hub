/** Element Plus Icons 全量导出，供选择器与侧栏动态渲染共用。 */
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

export const iconMap = ElementPlusIconsVue

/** 组件名列表（排除非图标导出）。 */
export const iconNames = Object.keys(ElementPlusIconsVue).filter(
  (name) => typeof ElementPlusIconsVue[name] === 'object',
)

/** 按名称解析图标组件；无效名返回 null。 */
export function resolveIcon(name) {
  if (!name || typeof name !== 'string') return null
  return ElementPlusIconsVue[name] || null
}
