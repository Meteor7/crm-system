<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { Check, ChevronDown, Plus, Search } from '@lucide/vue'
import type { QuotationCatalogItemDto } from './types'

const props = withDefaults(defineProps<{
  options: QuotationCatalogItemDto[]
  selectedIds?: string[]
  label: string
  placeholder: string
  customPlaceholder: string
  testId: string
  multiple?: boolean
  disabled?: boolean
}>(), { selectedIds: () => [], multiple: false, disabled: false })
const emit = defineEmits<{ select: [item: QuotationCatalogItemDto]; custom: [name: string] }>()

const open = ref(false)
const search = ref('')
const customName = ref('')
const searchInput = ref<HTMLInputElement>()
const normalizedSearch = computed(() => search.value.trim().toLocaleLowerCase())
const filteredOptions = computed(() => props.options.filter((item) =>
  !normalizedSearch.value || item.name.toLocaleLowerCase().includes(normalizedSearch.value),
))

async function toggle() {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) {
    search.value = ''
    await nextTick()
    searchInput.value?.focus()
  }
}
function choose(item: QuotationCatalogItemDto) {
  if (props.selectedIds.includes(item.id)) return
  emit('select', item)
  if (!props.multiple) open.value = false
}
function addCustom() {
  const name = customName.value.trim().replace(/\s+/g, ' ')
  if (!name) return
  emit('custom', name)
  customName.value = ''
  if (!props.multiple) open.value = false
}
function closeOnFocusOut(event: FocusEvent) {
  if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node | null)) open.value = false
}
</script>

<template>
  <div class="catalog-filter" :data-testid="testId" @focusout="closeOnFocusOut">
    <button class="catalog-trigger" type="button" role="combobox" :aria-label="label" :aria-expanded="open" aria-haspopup="listbox" :disabled="disabled" @click="toggle" @keydown.escape.prevent="open=false">
      <Plus :size="14" aria-hidden="true" /><span>{{ placeholder }}</span><ChevronDown :size="14" aria-hidden="true" />
    </button>
    <div v-if="open" class="catalog-menu">
      <label class="catalog-search"><Search :size="14" aria-hidden="true" /><input ref="searchInput" v-model="search" :aria-label="`${label}搜索`" placeholder="搜索已有选项" /></label>
      <div class="catalog-options" role="listbox" :aria-label="label" :aria-multiselectable="multiple">
        <button v-for="item in filteredOptions" :key="item.id" type="button" role="option" :aria-selected="selectedIds.includes(item.id)" :disabled="selectedIds.includes(item.id)" @click="choose(item)">
          <span>{{ item.name }}</span><Check v-if="selectedIds.includes(item.id)" :size="13" aria-hidden="true" />
        </button>
        <p v-if="!filteredOptions.length">没有匹配的已有选项</p>
      </div>
      <div class="catalog-custom">
        <input v-model="customName" :aria-label="`${label}自定义名称`" :placeholder="customPlaceholder" maxlength="140" @keydown.enter.prevent="addCustom" />
        <button type="button" :disabled="!customName.trim()" :aria-label="`新增自定义${label}`" @click="addCustom"><Plus :size="14" aria-hidden="true" /></button>
      </div>
      <small>自定义内容将在提交审批或直接发布后加入全局目录</small>
    </div>
  </div>
</template>

<style scoped>
.catalog-filter{position:relative;min-width:0}.catalog-trigger{display:inline-flex;min-height:34px;align-items:center;gap:6px;padding:0 10px;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:7px;font:inherit;font-weight:700;cursor:pointer}.catalog-trigger span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.catalog-trigger svg:last-child{margin-left:auto}.catalog-trigger:disabled{cursor:not-allowed;opacity:.55}.catalog-menu{position:absolute;z-index:90;top:calc(100% + 6px);right:0;width:min(360px,calc(100vw - 32px));padding:8px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;box-shadow:0 14px 34px rgba(8,32,40,.16)}.catalog-search{display:flex;align-items:center;gap:7px;padding:0 9px;border:1px solid var(--crm-line);border-radius:7px}.catalog-search:focus-within{border-color:var(--crm-teal)}.catalog-search input,.catalog-custom input{width:100%;height:34px;padding:0;border:0;outline:0;font:inherit}.catalog-options{display:grid;max-height:220px;gap:2px;margin:7px 0;overflow:auto}.catalog-options button{display:flex;min-height:34px;align-items:center;justify-content:space-between;gap:8px;padding:7px 9px;color:var(--crm-text);background:transparent;border:0;border-radius:5px;font:inherit;text-align:left;cursor:pointer}.catalog-options button:hover,.catalog-options button:focus-visible{color:var(--crm-teal);background:#eef6f5;outline:0}.catalog-options button:disabled{cursor:default;opacity:.55}.catalog-options p{margin:8px;color:var(--crm-muted);font-size:10px;text-align:center}.catalog-custom{display:grid;grid-template-columns:1fr 34px;align-items:center;border:1px solid var(--crm-line);border-radius:7px;overflow:hidden}.catalog-custom input{padding:0 9px}.catalog-custom button{display:grid;width:34px;height:34px;place-items:center;color:#fff;background:var(--crm-teal);border:0;cursor:pointer}.catalog-custom button:disabled{cursor:not-allowed;opacity:.45}.catalog-menu>small{display:block;margin-top:6px;color:var(--crm-muted);font-size:9px;line-height:1.4}@media(max-width:640px){.catalog-trigger{width:100%}.catalog-menu{right:auto;left:0}}
</style>