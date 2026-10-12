<template>
  <div v-if="items?.length" class="citations">
    <div class="title">引用来源</div>
    <div v-for="c in items" :key="`${c.index}-${c.chunk_id}`" class="item">
      <div class="head">
        <span class="idx">[{{ c.index }}]</span>
        {{ c.title }}
      </div>
      <div v-if="c.heading_path" class="path">{{ c.heading_path }}</div>
      <div class="snippet">{{ c.snippet }}</div>
    </div>
  </div>
</template>

<script setup>
/** 引用来源短摘录列表（与答案 [n] 对齐）。 */
defineProps({
  items: {
    type: Array,
    default: () => [],
  },
})
</script>

<style scoped>
.citations {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--muted);
  margin-bottom: 8px;
  text-transform: uppercase;
}

.item {
  margin-bottom: 8px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  font-size: 12px;
}

.item:last-child {
  margin-bottom: 0;
}

.head {
  font-weight: 600;
  color: var(--text);
  line-height: 1.4;
}

.idx {
  color: var(--accent);
  margin-right: 2px;
}

.path {
  color: var(--muted);
  font-size: 11px;
  margin-top: 2px;
}

.snippet {
  margin-top: 4px;
  color: var(--text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
