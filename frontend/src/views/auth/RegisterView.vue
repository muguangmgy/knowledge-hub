<template>
  <div class="auth-wrap">
    <div class="card auth-card fade-up">
      <div class="brand-row">
        <img class="brand-mark" src="/logo.svg" width="28" height="28" alt="" />
        <span class="brand-name">Knowledge Hub</span>
      </div>
      <h1>注册</h1>
      <p class="hint">创建账号后即可管理文档与发起问答</p>
      <el-form :model="form" label-position="top" @submit.prevent="onSubmit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" size="large" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            size="large"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>
        <el-button type="primary" size="large" :loading="loading" native-type="submit" class="submit">
          注册
        </el-button>
      </el-form>
      <p class="footer">
        已有账号？
        <RouterLink to="/login">登录</RouterLink>
      </p>
    </div>
  </div>
</template>

<script setup>
/** 注册页；成功后引导去登录。 */
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../../stores/user'

const userStore = useUserStore()
const router = useRouter()
const loading = ref(false)
const form = reactive({
  username: '',
  password: '',
})

/** 提交注册。 */
async function onSubmit() {
  loading.value = true
  try {
    await userStore.register(form)
    ElMessage.success('注册成功，请登录')
    router.push('/login')
  } catch (err) {
    ElMessage.error(err?.message || '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.brand-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 22px;
}

.brand-mark {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: block;
}

.brand-name {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

h1 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.hint {
  margin: 0 0 22px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.5;
}

.submit {
  width: 100%;
  margin-top: 4px;
  font-weight: 600;
}

.footer {
  margin: 18px 0 0;
  color: var(--muted);
  font-size: 13px;
  text-align: center;
}

.footer a {
  color: var(--accent);
  font-weight: 500;
}

.footer a:hover {
  text-decoration: underline;
}

:deep(.el-form-item__label) {
  font-weight: 500;
  color: var(--text-secondary);
}
</style>
