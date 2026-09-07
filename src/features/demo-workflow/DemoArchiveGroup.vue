<script setup lang="ts">
import { salesEnumLabel } from '@/features/shared/sales-i18n'
import type { DemoArchiveGroup } from '@/domain/demo-archive'
import type { DemoWorkflowDto } from '@/types/workspaces'
import { personnelDisplayName } from '@/demo/personnel'
import { useI18n } from '@/i18n'

defineProps<{
  group: DemoArchiveGroup
  selectedId: string
  groupBy: 'customer' | 'equipment'
}>()
defineEmits<{ open: [item: DemoWorkflowDto] }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const groupLabel = (value: string) => value === '未指定设备' ? copy('Unspecified equipment', value) : value
</script>

<template>
  <section class="archive-group" data-demo-archive-group>
    <header>
      <strong>{{ groupLabel(group.label) }}</strong>
      <span>{{ group.count }}</span>
    </header>
    <button
      v-for="item in group.items"
      :key="item.id"
      type="button"
      class="archive-card"
      :class="{ active: selectedId === item.id }"
      :data-demo-id="item.id"
      @click="$emit('open', item)"
    >
      <span class="archive-card-head">
        <strong>{{ item.id }}</strong>
        <i :class="item.status.toLowerCase()">{{ salesEnumLabel(item.status, locale) }}</i>
      </span>
      <b>{{ item.title }}</b>
      <small>{{ groupBy === 'customer' ? item.equipment : item.account }}</small>
      <small>{{ copy('Sales', '销售') }} {{ personnelDisplayName(item.salesOwner) }} · {{ copy('Engineer', '工程师') }} {{ personnelDisplayName(item.engineerOwner) }}</small>
    </button>
  </section>
</template>

<style scoped>
.archive-group{display:grid;gap:8px}.archive-group>header{display:flex;align-items:center;justify-content:space-between;padding:5px 2px;color:#22272d}.archive-group>header strong{font-size:12px}.archive-group>header span{display:grid;min-width:24px;height:24px;place-items:center;color:#e86600;background:#fff0e2;border-radius:7px;font-size:11px;font-weight:800}.archive-card{display:grid;gap:6px;width:100%;padding:12px;color:#24282e;background:#fff;border:1px solid #dedbd6;border-radius:6px;cursor:pointer;text-align:left}.archive-card:hover,.archive-card:focus-visible,.archive-card.active{border-color:#f28a24;box-shadow:0 3px 12px rgba(27,31,35,.08);outline:0}.archive-card-head{display:flex;align-items:center;justify-content:space-between}.archive-card-head>strong{font-size:11px}.archive-card-head i{padding:3px 6px;color:#3c6b2a;background:#edf6e9;border-radius:5px;font-size:9px;font-style:normal;font-weight:750}.archive-card-head i.rejected{color:#9d3c38;background:#fff0ee}.archive-card b{overflow:hidden;font-size:12px;line-height:1.4;text-overflow:ellipsis;white-space:nowrap}.archive-card small{overflow:hidden;color:#6f747a;font-size:10px;text-overflow:ellipsis;white-space:nowrap}
</style>
