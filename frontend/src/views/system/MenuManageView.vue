<template>
  <div class="page admin-page">
    <el-card shadow="never" class="panel">
      <div class="toolbar">
        <el-button type="primary" @click="openCreate(0)">新建菜单</el-button>
      </div>

      <el-table
        :data="flatRows"
        v-loading="loading"
        row-key="id"
        default-expand-all
        :tree-props="{ children: 'children' }"
        stripe
        border
        height="100%"
        class="fill-table"
      >
        <el-table-column prop="name" label="名称" min-width="180" align="center" />
        <el-table-column prop="type" label="类型" width="110" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="typeTag(row.type)">{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="path" label="路径" min-width="140" align="center" show-overflow-tooltip />
        <el-table-column prop="perms" label="perms" min-width="140" align="center" show-overflow-tooltip />
        <el-table-column prop="sort" label="排序" width="80" align="center" />
        <el-table-column prop="visible" label="可见" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.visible === 1 ? 'success' : 'info'">
              {{ row.visible === 1 ? '显示' : '隐藏' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 1 ? 'success' : 'info'">
              {{ row.status === 1 ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="openCreate(row.id)">子节点</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button
              link
              type="danger"
              :disabled="isBuiltin(row)"
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
      :title="mode === 'create' ? '新建菜单' : '编辑菜单'"
      width="480px"
      destroy-on-close
    >
      <el-form label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.type" style="width: 100%">
            <el-option label="目录" value="catalog" />
            <el-option label="菜单" value="menu" />
            <el-option label="按钮" value="button" />
          </el-select>
        </el-form-item>
        <el-form-item label="路径">
          <el-input v-model="form.path" placeholder="/system/xxx" />
        </el-form-item>
        <el-form-item label="perms">
          <el-input v-model="form.perms" />
        </el-form-item>
        <el-form-item label="图标">
          <IconSelect v-model="form.icon" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort" :min="0" />
        </el-form-item>
        <el-form-item label="可见">
          <el-radio-group v-model="form.visible">
            <el-radio-button :value="1">显示</el-radio-button>
            <el-radio-button :value="0">隐藏</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio-button :value="1">正常</el-radio-button>
            <el-radio-button :value="0">禁用</el-radio-button>
          </el-radio-group>
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
/** 菜单管理：树表 CRUD；内置系统管理目录及三页不可删。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as menusApi from '../../api/menus'
import IconSelect from '../../components/system/IconSelect.vue'

/** 与后端 is_builtin_menu 对齐：三管理页 path + 系统管理目录 perms */
const BUILTIN_PATHS = new Set([
  '/system/users',
  '/system/roles',
  '/system/menus',
  '/system/dev',
])
const BUILTIN_CATALOG_PERMS = new Set(['system:catalog'])

const loading = ref(false)
const saving = ref(false)
const tree = ref([])
const visible = ref(false)
const mode = ref('create')
const form = reactive({
  id: null,
  parentId: 0,
  name: '',
  type: 'menu',
  path: '',
  perms: '',
  icon: '',
  sort: 0,
  visible: 1,
  status: 1,
})

const flatRows = computed(() => tree.value)

function typeLabel(t) {
  return { catalog: '目录', menu: '菜单', button: '按钮' }[t] || t
}

function typeTag(t) {
  return { catalog: '', menu: 'success', button: 'warning' }[t] || 'info'
}

/** 内置节点：前端禁用删除；后端 delete 亦拒绝。 */
function isBuiltin(row) {
  if (row.path && BUILTIN_PATHS.has(row.path)) return true
  if (row.type === 'catalog' && BUILTIN_CATALOG_PERMS.has(row.perms)) return true
  return false
}

async function load() {
  loading.value = true
  try {
    const res = await menusApi.fetchMenuTree()
    tree.value = res.data || []
  } catch (e) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate(parentId) {
  mode.value = 'create'
  Object.assign(form, {
    id: null,
    parentId,
    name: '',
    type: 'menu',
    path: '',
    perms: '',
    icon: '',
    sort: 0,
    visible: 1,
    status: 1,
  })
  visible.value = true
}

function openEdit(row) {
  mode.value = 'edit'
  Object.assign(form, {
    id: row.id,
    parentId: row.parentId,
    name: row.name,
    type: row.type,
    path: row.path || '',
    perms: row.perms || '',
    icon: row.icon || '',
    sort: row.sort ?? 0,
    visible: row.visible ?? 1,
    status: row.status ?? 1,
  })
  visible.value = true
}

async function save() {
  const body = {
    parentId: form.parentId,
    name: form.name,
    type: form.type,
    path: form.path || null,
    perms: form.perms || null,
    icon: form.icon || null,
    sort: form.sort,
    visible: form.visible,
    status: form.status,
  }
  saving.value = true
  try {
    if (mode.value === 'create') {
      await menusApi.createMenu(body)
      ElMessage.success('已创建')
    } else {
      await menusApi.updateMenu(form.id, body)
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
    await ElMessageBox.confirm(`确认删除菜单 ${row.name}？`, '提示', { type: 'warning' })
    await menusApi.deleteMenu(row.id)
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
