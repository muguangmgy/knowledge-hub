<template>
  <div class="page admin-page">
    <el-card shadow="never" class="panel">
      <template #header>
        <div class="card-head">
          <span>开发调试</span>
          <el-tag size="small" type="warning">仅本浏览器生效</el-tag>
        </div>
      </template>

      <el-form label-width="160px" class="debug-form">
        <el-form-item label="对话使用流式输出">
          <el-switch v-model="streamOn" @change="onStreamChange" />
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
/** 开发向开关：对话流式/同步；偏好存 localStorage，不落库。 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  isChatStreamEnabled,
  setChatStreamEnabled,
} from '../../utils/chatStreamPref'

const streamOn = ref(isChatStreamEnabled())

function onStreamChange(val) {
  setChatStreamEnabled(!!val)
  streamOn.value = isChatStreamEnabled()
  ElMessage.success(val ? '已开启流式输出' : '已关闭流式，改用同步问答')
}
</script>

<style scoped>
.card-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.debug-form {
  max-width: 720px;
  padding-top: 8px;
}
</style>
