<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from '@/i18n'

const CUSTOM_SEGMENT = '__custom_account_segment__'
const props = withDefaults(defineProps<{
  modelValue: string
  segments: string[]
  label: string
  required?: boolean
}>(), { required: false })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const { locale, t } = useI18n()

const options = computed(() => [...new Set(props.segments.map((value) => value.trim()).filter(Boolean))])
const customMode = ref(!options.value.includes(props.modelValue))
const selectedValue = computed(() => customMode.value ? CUSTOM_SEGMENT : props.modelValue)

watch(
  () => [props.modelValue, ...options.value],
  () => {
    if (options.value.includes(props.modelValue)) customMode.value = false
    else if (props.modelValue) customMode.value = true
  },
)

function selectSegment(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  customMode.value = value === CUSTOM_SEGMENT
  emit('update:modelValue', customMode.value ? '' : value)
}

function updateCustomSegment(event: Event) {
  emit('update:modelValue', (event.target as HTMLInputElement).value)
}
</script>

<template>
  <div class="account-segment-select">
    <select :value="selectedValue" :aria-label="label" :required="required" @change="selectSegment">
      <option v-for="segment in options" :key="segment" :value="segment">{{ segment }}</option>
      <option :value="CUSTOM_SEGMENT">{{ locale === 'en-US' ? '+ Custom area' : '＋自定义领域' }}</option>
    </select>
    <input
      v-if="customMode"
      :value="modelValue"
      :aria-label="t('common.customField', { label })"
      :required="required"
      :placeholder="locale === 'en-US' ? 'Enter a custom business area' : '请输入自定义业务领域'"
      @input="updateCustomSegment"
    />
  </div>
</template>

<style scoped>
.account-segment-select{display:grid;gap:6px;width:100%}
.account-segment-select select,.account-segment-select input{width:100%;height:38px;padding:0 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;box-sizing:border-box;font:inherit}
.account-segment-select select:focus,.account-segment-select input:focus{border-color:var(--crm-teal);outline:0}
</style>
