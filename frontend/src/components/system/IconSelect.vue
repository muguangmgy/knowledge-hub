<template>
  <div class="icon-select">
    <el-input
      :model-value="modelValue"
      clearable
      placeholder="选择或输入图标名"
      @update:model-value="emitValue"
    >
      <template #prefix>
        <el-icon v-if="current" :size="16">
          <component :is="current" />
        </el-icon>
      </template>
      <template #append>
        <el-popover
          v-model:visible="open"
          placement="bottom-end"
          :width="360"
          trigger="click"
          :teleported="true"
        >
          <template #reference>
            <el-button :icon="Grid" />
          </template>
          <div class="icon-picker">
            <el-input
              v-model="keyword"
              clearable
              size="small"
              placeholder="搜索图标"
              class="icon-picker-search"
            />
            <div class="icon-picker-grid">
              <button
                v-for="name in filtered"
                :key="name"
                type="button"
                class="icon-picker-item"
                :class="{ active: name === modelValue }"
                :title="name"
                @click="pick(name)"
              >
                <el-icon :size="18">
                  <component :is="iconMap[name]" />
                </el-icon>
              </button>
              <p v-if="!filtered.length" class="icon-picker-empty">无匹配图标</p>
            </div>
          </div>
        </el-popover>
      </template>
    </el-input>
  </div>
</template>

<script setup>
/** 菜单图标选择器：可输入组件名，或从 Element Plus Icons 网格挑选。 */
import { computed, ref } from 'vue'
import { Grid } from '@element-plus/icons-vue'
import { iconMap, iconNames, resolveIcon } from '../../utils/icons'

const props = defineProps({
  /** Element Plus Icons 组件名字符串，如 Setting */
  modelValue: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

const open = ref(false)
const keyword = ref('')

const current = computed(() => resolveIcon(props.modelValue))

/** 按关键字过滤图标名（忽略大小写）。 */
const filtered = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return iconNames
  return iconNames.filter((n) => n.toLowerCase().includes(q))
})

function emitValue(v) {
  emit('update:modelValue', v || '')
}

/** 点选图标后写回并关闭弹层。 */
function pick(name) {
  emitValue(name)
  open.value = false
  keyword.value = ''
}
</script>

<style scoped>
.icon-select {
  width: 100%;
}

.icon-picker-search {
  margin-bottom: 10px;
}

.icon-picker-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 4px;
  max-height: 240px;
  overflow-y: auto;
}

.icon-picker-item {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  aspect-ratio: 1;
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}

.icon-picker-item:hover {
  background: var(--accent-soft);
  color: var(--accent);
}

.icon-picker-item.active {
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--accent);
}

.icon-picker-empty {
  grid-column: 1 / -1;
  margin: 12px 0;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}
</style>
