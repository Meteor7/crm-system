<script setup lang="ts">
import { computed } from 'vue'
import { groupDemoArchives, type DemoArchiveGroupMode } from '@/domain/demo-archive'
import type { DemoWorkflowDto } from '@/types/workspaces'
import DemoArchiveGroup from './DemoArchiveGroup.vue'
import { personnelDisplayName } from '@/demo/personnel'

const props = defineProps<{
  items: DemoWorkflowDto[]
  result: 'all' | 'Accepted' | 'Rejected'
  salesOwner: string
  engineerOwner: string
  groupBy: DemoArchiveGroupMode
  selectedId: string
}>()
const emit = defineEmits<{
  'update:result': [value: 'all' | 'Accepted' | 'Rejected']
  'update:salesOwner': [value: string]
  'update:engineerOwner': [value: string]
  'group-change': [value: DemoArchiveGroupMode]
  open: [item: DemoWorkflowDto]
}>()

const archived = computed(() => props.items.filter((item) => item.archiveCategory === 'Completed'))
const salesOwners = computed(() => [...new Set(archived.value.map((item) => item.salesOwner))].sort())
const engineerOwners = computed(() => [...new Set(archived.value.map((item) => item.engineerOwner))].sort())
const filtered = computed(() => {
  return archived.value.filter((item) =>
    (props.result === 'all' || item.status === props.result)
    && (props.salesOwner === 'all' || item.salesOwner === props.salesOwner)
    && (props.engineerOwner === 'all' || item.engineerOwner === props.engineerOwner),
  )
})
const groups = computed(() => groupDemoArchives(filtered.value, props.groupBy))
</script>

<template>
  <aside class="archive-browser" data-demo-archive>
    <div class="archive-tools">
      <label>
        <span>归档结果</span>
        <select
          :value="result"
          aria-label="Archive Result"
          @change="emit('update:result', ($event.target as HTMLSelectElement).value as 'all' | 'Accepted' | 'Rejected')"
        >
          <option value="all">全部</option>
          <option value="Accepted">Accepted</option>
          <option value="Rejected">Rejected</option>
        </select>
      </label>
      <label>
        <span>Sales</span>
        <select
          :value="salesOwner"
          aria-label="Archive Sales Owner"
          @change="emit('update:salesOwner', ($event.target as HTMLSelectElement).value)"
        >
          <option value="all">全部</option>
          <option v-for="owner in salesOwners" :key="owner" :value="owner">{{ personnelDisplayName(owner) }}</option>
        </select>
      </label>
      <label>
        <span>Engineer</span>
        <select
          :value="engineerOwner"
          aria-label="Archive Engineer Owner"
          @change="emit('update:engineerOwner', ($event.target as HTMLSelectElement).value)"
        >
          <option value="all">全部</option>
          <option v-for="owner in engineerOwners" :key="owner" :value="owner">{{ personnelDisplayName(owner) }}</option>
        </select>
      </label>
    </div>

    <div class="group-switch" aria-label="Demo 档案分类">
      <button
        type="button"
        data-archive-group-mode="customer"
        :class="{ active: groupBy === 'customer' }"
        @click="emit('group-change', 'customer')"
      >按客户</button>
      <button
        type="button"
        data-archive-group-mode="equipment"
        :class="{ active: groupBy === 'equipment' }"
        @click="emit('group-change', 'equipment')"
      >按设备</button>
    </div>

    <div v-if="groups.length" class="archive-groups">
      <DemoArchiveGroup
        v-for="group in groups"
        :key="group.label"
        :group="group"
        :selected-id="selectedId"
        :group-by="groupBy"
        @open="emit('open', $event)"
      />
    </div>
    <p v-else class="archive-empty">当前筛选范围内暂无已归档 Demo。</p>
  </aside>
</template>

<style scoped>
.archive-browser{display:grid;gap:13px;min-width:0;align-content:start}.archive-tools{display:grid;grid-template-columns:1fr 1fr;gap:8px}.archive-tools label{display:flex;min-width:0;height:42px;align-items:center;gap:7px;padding:0 10px;background:#fff;border:1px solid #d8d4ce;border-radius:6px}.archive-tools label>span{color:#353a41;font-size:10px;font-weight:750}.archive-tools input,.archive-tools select{min-width:0;flex:1;color:#292e34;background:transparent;border:0;outline:0;font-size:11px}.archive-search{grid-column:1/-1;color:#686d73}.group-switch{display:grid;grid-template-columns:1fr 1fr;padding:3px;background:#ece9e3;border-radius:7px}.group-switch button{height:34px;color:#686d73;background:transparent;border:0;border-radius:5px;cursor:pointer;font-size:11px;font-weight:750}.group-switch button.active{color:#e86600;background:#fff;box-shadow:0 1px 5px rgba(30,34,38,.08)}.archive-groups{display:grid;max-height:calc(100vh - 330px);gap:15px;padding-right:3px;overflow-y:auto;overscroll-behavior:contain}.archive-empty{margin:0;padding:32px 16px;color:#858a90;background:#fff;border:1px dashed #d9d5ce;border-radius:7px;font-size:11px;text-align:center}@media(max-width:560px){.archive-tools{grid-template-columns:1fr}.archive-search{grid-column:auto}}
</style>
