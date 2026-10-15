<template>
  <div class="page admin-page">
    <el-card shadow="never" class="panel">
      <el-form :inline="true" class="filter" @submit.prevent="load">
        <el-form-item label="用户名">
          <el-input
            v-model="query.username"
            clearable
            placeholder="模糊查询"
            style="width: 160px"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 120px">
            <el-option label="正常" :value="1" />
            <el-option label="禁用" :value="0" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
          <el-button type="primary" plain @click="openCreate">新建</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="items" v-loading="loading" stripe border height="100%" class="fill-table">
        <el-table-column prop="username" label="用户名" min-width="120" align="center" />
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'info'" size="small">
              {{ row.status === 1 ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="角色" min-width="160" align="center">
          <template #default="{ row }">
            <el-space wrap>
              <el-tag
                v-for="name in roleNameList(row.roleIds)"
                :key="name"
                size="small"
                type="info"
              >
                {{ name }}
              </el-tag>
              <span v-if="!roleNameList(row.roleIds).length" class="muted">—</span>
            </el-space>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button
              link
              type="warning"
              :disabled="row.id === meId"
              @click="toggleStatus(row)"
            >
              {{ row.status === 1 ? '禁用' : '启用' }}
            </el-button>
            <el-button link type="primary" @click="openResetPwd(row)">重置密码</el-button>
            <el-button
              link
              type="danger"
              :disabled="row.id === meId"
              @click="onDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="total"
          :page-size="query.pageSize"
          :current-page="query.page"
          @current-change="onPage"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="formVisible"
      :title="formMode === 'create' ? '新建用户' : '编辑用户'"
      width="420px"
      destroy-on-close
    >
      <el-form label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="form.username" :disabled="formMode === 'edit'" />
        </el-form-item>
        <el-form-item v-if="formMode === 'create'" label="密码">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width: 100%">
            <el-option label="正常" :value="1" />
            <el-option label="禁用" :value="0" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.roleIds" multiple style="width: 100%">
            <el-option v-for="r in roles" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveForm">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="pwdVisible" title="重置密码" width="400px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="新密码">
          <el-input v-model="pwdForm.password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="savePwd">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/** 用户管理：列表 / 新建 / 启停 / 分配角色 / 重置密码；禁止操作自己。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as usersApi from '../../api/users'
import * as rolesApi from '../../api/roles'
import { useUserStore } from '../../stores/user'

const userStore = useUserStore()
/** 当前登录用户 id；禁用/删除按钮对其不可用 */
const meId = computed(() => userStore.profile?.id)

const loading = ref(false)
const saving = ref(false)
const items = ref([])
const total = ref(0)
const roles = ref([])
const query = reactive({ page: 1, pageSize: 20, username: '', status: null })

const formVisible = ref(false)
const formMode = ref('create')
const form = reactive({ id: null, username: '', password: '', status: 1, roleIds: [] })

const pwdVisible = ref(false)
const pwdForm = reactive({ id: null, password: '' })

/** roleIds → 角色显示名（列表展示用）。 */
function roleNameList(ids) {
  const map = Object.fromEntries(roles.value.map((r) => [r.id, r.name]))
  return (ids || []).map((id) => map[id] || String(id))
}

async function loadRoles() {
  const res = await rolesApi.listRoles()
  roles.value = res.data || []
}

async function load() {
  loading.value = true
  try {
    const res = await usersApi.listUsers({
      page: query.page,
      pageSize: query.pageSize,
      username: query.username || undefined,
      status: query.status === null || query.status === '' ? undefined : query.status,
    })
    items.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (e) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function onPage(p) {
  query.page = p
  load()
}

function openCreate() {
  formMode.value = 'create'
  Object.assign(form, { id: null, username: '', password: '', status: 1, roleIds: [] })
  formVisible.value = true
}

function openEdit(row) {
  formMode.value = 'edit'
  Object.assign(form, {
    id: row.id,
    username: row.username,
    password: '',
    status: row.status,
    roleIds: [...(row.roleIds || [])],
  })
  formVisible.value = true
}

async function saveForm() {
  saving.value = true
  try {
    if (formMode.value === 'create') {
      await usersApi.createUser({
        username: form.username,
        password: form.password,
        status: form.status,
        roleIds: form.roleIds,
      })
      ElMessage.success('已创建')
    } else {
      await usersApi.updateUser(form.id, {
        status: form.status,
        roleIds: form.roleIds,
      })
      ElMessage.success('已保存')
    }
    formVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function openResetPwd(row) {
  pwdForm.id = row.id
  pwdForm.password = ''
  pwdVisible.value = true
}

async function savePwd() {
  saving.value = true
  try {
    await usersApi.updateUser(pwdForm.id, { password: pwdForm.password })
    ElMessage.success('密码已重置')
    pwdVisible.value = false
  } catch (e) {
    ElMessage.error(e?.message || '重置失败')
  } finally {
    saving.value = false
  }
}

/** 启用/禁用；后端拒绝操作当前登录用户。 */
async function toggleStatus(row) {
  const next = row.status === 1 ? 0 : 1
  try {
    await usersApi.updateUser(row.id, { status: next })
    ElMessage.success('已更新')
    await load()
  } catch (e) {
    ElMessage.error(e?.message || '更新失败')
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除用户 ${row.username}？`, '提示', { type: 'warning' })
    await usersApi.deleteUser(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    if (e === 'cancel' || e === 'close') return
    ElMessage.error(e?.message || '删除失败')
  }
}

onMounted(async () => {
  await loadRoles()
  await load()
})
</script>

<style scoped>
.panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: none;
}

.panel :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 16px 20px;
}

.filter {
  margin-bottom: 4px;
}

.filter :deep(.el-form-item) {
  margin-bottom: 12px;
}

.fill-table {
  flex: 1;
}

.pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}

.muted {
  color: var(--muted);
  font-size: 13px;
}
</style>
