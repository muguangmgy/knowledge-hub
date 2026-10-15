<template>
  <div class="page admin-page">
    <el-card shadow="never" class="panel">
      <div class="toolbar">
        <el-button type="primary" @click="openCreate">新建角色</el-button>
      </div>

      <el-table :data="items" v-loading="loading" stripe border height="100%" class="fill-table">
        <el-table-column prop="code" label="编码" width="140" align="center" />
        <el-table-column prop="name" label="名称" min-width="140" align="center" />
        <el-table-column label="菜单数" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ (row.menuIds || []).length }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button
              link
              type="danger"
              :disabled="isBuiltin(row.code)"
              @click="onDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="visible"
      :title="mode === 'create' ? '新建角色' : '编辑角色'"
      width="520px"
      destroy-on-close
    >
      <el-form label-width="80px">
        <el-form-item label="编码">
          <el-input v-model="form.code" :disabled="mode === 'edit'" placeholder="如 editor" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="菜单">
          <el-scrollbar max-height="320px">
            <el-tree
              ref="treeRef"
              :data="menuTree"
              node-key="id"
              show-checkbox
              default-expand-all
              :props="{ label: 'name', children: 'children' }"
            />
          </el-scrollbar>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/** 角色管理：列表 / 新建编辑（勾选菜单树）/ 删除；内置 admin、user 不可删。 */
import { nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as rolesApi from '../../api/roles'
import * as menusApi from '../../api/menus'

/** 种子内置角色，前端禁用删除按钮（后端亦拦截）。 */
const BUILTIN = new Set(['admin', 'user'])

const loading = ref(false)
const saving = ref(false)
const items = ref([])
const menuTree = ref([])
const visible = ref(false)
const mode = ref('create')
const treeRef = ref(null)
const form = reactive({ id: null, code: '', name: '', menuIds: [] })

function isBuiltin(code) {
  return BUILTIN.has(code)
}

async function load() {
  loading.value = true
  try {
    const [rolesRes, menusRes] = await Promise.all([
      rolesApi.listRoles(),
      menusApi.fetchMenuTree(),
    ])
    items.value = rolesRes.data || []
    menuTree.value = menusRes.data || []
  } catch (e) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  mode.value = 'create'
  Object.assign(form, { id: null, code: '', name: '', menuIds: [] })
  visible.value = true
  nextTick(() => treeRef.value?.setCheckedKeys([]))
}

function openEdit(row) {
  mode.value = 'edit'
  Object.assign(form, {
    id: row.id,
    code: row.code,
    name: row.name,
    menuIds: [...(row.menuIds || [])],
  })
  visible.value = true
  nextTick(() => {
    treeRef.value?.setCheckedKeys(form.menuIds, false)
  })
}

async function save() {
  // 方案 A：只提交勾选节点（多为叶子），祖先由 /me 读时闭包补全
  const menuIds = treeRef.value?.getCheckedKeys(true) || []
  saving.value = true
  try {
    if (mode.value === 'create') {
      await rolesApi.createRole({
        code: form.code,
        name: form.name,
        menuIds,
      })
      ElMessage.success('已创建')
    } else {
      await rolesApi.updateRole(form.id, { name: form.name, menuIds })
      ElMessage.success('已保存')
    }
    visible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除角色 ${row.name}？`, '提示', { type: 'warning' })
    await rolesApi.deleteRole(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    if (e === 'cancel' || e === 'close') return
    ElMessage.error(e?.message || '删除失败')
  }
}

onMounted(load)
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

.toolbar {
  margin-bottom: 12px;
}

.fill-table {
  flex: 1;
}
</style>
