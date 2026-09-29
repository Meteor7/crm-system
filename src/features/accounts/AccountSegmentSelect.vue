<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from '@/i18n'

const CUSTOM_SEGMENT = '__custom_account_segment__'
const props = withDefaults(defineProps<{
  modelValue: string
  segments: readonly string[]
  label: string
  required?: boolean
  customOptionLabel?: string
  customInputLabel?: string
  customPlaceholder?: string
  emptyPlaceholder?: string
  customOnEmpty?: boolean
  /** Display text for a stored option, such as a preset region shown in Chinese. */
  optionLabel?: (value: string) => string
}>(), {
  required: false,
  customOptionLabel: undefined,
  customInputLabel: undefined,
  customPlaceholder: undefined,
  emptyPlaceholder: undefined,
  customOnEmpty: true,
  optionLabel: undefined,
})
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const { locale, t } = useI18n()

const options = computed(() => [...new Set(props.segments.map((value) => value.trim()).filter(Boolean))])
const customMode = ref(props.modelValue ? !options.value.includes(props.modelValue) : props.customOnEmpty)
const selectedValue = computed(() => customMode.value ? CUSTOM_SEGMENT : props.modelValue)
let lastCustomInput: string | undefined

watch(
  () => [props.modelValue, ...options.value],
  () => {
    // Keep typed option prefixes editable while still syncing external values.
    if (customMode.value && props.modelValue === lastCustomInput) return
    lastCustomInput = undefined
    if (options.value.includes(props.modelValue)) customMode.value = false
    else if (props.modelValue) customMode.value = true
    else if (!customMode.value) customMode.value = props.customOnEmpty
  },
)

function selectSegment(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  customMode.value = value === CUSTOM_SEGMENT
  emit('update:modelValue', customMode.value ? '' : value)
}

function updateCustomSegment(event: Event) {
  lastCustomInput = (event.target as HTMLInputElement).value
  emit('update:modelValue', lastCustomInput)
}
</script>

<template>
  <div class="account-segment-select">
    <select :value="selectedValue" :aria-label="label" :required="required" @change="selectSegment">
      <option v-if="!customMode && !modelValue && emptyPlaceholder" value="" disabled>{{ emptyPlaceholder }}</option>
      <option v-for="segment in options" :key="segment" :value="segment">{{ optionLabel ? optionLabel(segment) : segment }}</option>
      <option :value="CUSTOM_SEGMENT">{{ customOptionLabel || (locale === 'en-US' ? '+ Custom area' : '＋自定义领域') }}</option>
    </select>
    <input
      v-if="customMode"
      :value="modelValue"
      :aria-label="customInputLabel || t('common.customField', { label })"
      :required="required"
      :placeholder="customPlaceholder || (locale === 'en-US' ? 'Enter a custom business area' : '请输入自定义业务领域')"
      @input="updateCustomSegment"
    />
  </div>
</template>

<style scoped>
.account-segment-select{display:grid;gap:6px;width:100%}
.account-segment-select select,.account-segment-select input{width:100%;height:38px;padding:0 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;box-sizing:border-box;font:inherit}
.account-segment-select select:focus,.account-segment-select input:focus{border-color:var(--crm-teal);outline:0}
</style>
