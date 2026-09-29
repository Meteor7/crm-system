<script setup lang="ts">
import { ref } from 'vue'
import { MessageSquareText, X } from '@lucide/vue'
import type { EvaluationDto } from '@/types/crm'
import { useI18n, useLocaleMessage } from '@/i18n'

type CustomerCommentOutcome = 'archive' | 'retest'

const props = withDefaults(defineProps<{
  evaluation: EvaluationDto
  busy?: boolean
  submitError?: string
  defaultOutcome?: CustomerCommentOutcome
}>(), { busy: false, submitError: '', defaultOutcome: 'archive' })
const emit = defineEmits<{ close: []; submit: [payload: { comment: string; outcome: CustomerCommentOutcome }] }>()
const comment = ref('')
const outcome = ref<CustomerCommentOutcome>(props.defaultOutcome)
const error = useLocaleMessage()
const { locale, t, message } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese

function submit() {
  const body = comment.value.trim()
  if (!body) { error.value = message('customerComment.required'); return }
  error.value = ''
  emit('submit', { comment: body, outcome: outcome.value })
}
</script>

<template>
  <div class="host" role="presentation" @mousedown.self="!busy && emit('close')">
    <section role="dialog" aria-modal="true" :aria-label="t('customerComment.title')">
      <header><div><span>CUSTOMER COMMENT</span><h2>{{ t('customerComment.title') }}</h2></div><button type="button" :aria-label="t('detail.close')" :disabled="busy" @click="emit('close')"><X :size="18" /></button></header>
      <div class="body">
        <p>{{ evaluation.title }} · {{ evaluation.id }} · {{ copy(`Round ${evaluation.testRound}`, `第 ${evaluation.testRound} 轮`) }}</p>
        <p class="hint">{{ t('customerComment.hint') }}</p>
        <label>
          {{ copy('Customer comment', '客户意见') }}
          <textarea
            v-model="comment"
            data-customer-comment-body
            :aria-label="copy('Customer comment', '客户意见')"
            maxlength="1000"
            rows="4"
            required
          />
        </label>
        <fieldset>
          <legend>{{ copy('Next step', '后续动作') }}</legend>
          <label class="choice"><input v-model="outcome" type="radio" value="archive" data-outcome-archive />{{ t('customerComment.archive') }}</label>
          <label class="choice"><input v-model="outcome" type="radio" value="retest" data-outcome-retest />{{ t('customerComment.retest') }}</label>
        </fieldset>
        <p v-if="error || submitError" class="error" role="alert">{{ error || submitError }}</p>
      </div>
      <footer>
        <button type="button" class="secondary-button" :disabled="busy" @click="emit('close')">{{ t('detail.cancel') }}</button>
        <button type="button" class="primary-button" :disabled="busy || !comment.trim()" data-submit-customer-comment @click="submit">
          <MessageSquareText :size="15" />{{ busy ? t('common.processing') : t('customerComment.submit') }}
        </button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.host{position:fixed;inset:0;z-index:2200;overflow-y:auto;overscroll-behavior:contain;display:grid;place-items:center;padding:24px;background:rgba(7,29,37,.5)}section{width:min(560px,100%);overflow:hidden;background:#fff;border-radius:14px}header,footer{display:flex;align-items:center;justify-content:space-between;padding:16px 18px}header{color:#fff;background:var(--crm-navy)}header span{color:#98c9c4;font-size:8px;font-weight:800}h2{margin:3px 0 0;font-size:17px}header button{color:#fff;background:transparent;border:0}.body{display:grid;gap:12px;padding:20px}.body p{margin:0;color:var(--crm-text-muted)}.hint{font-size:11px;line-height:1.6}label{display:grid;gap:8px;font-weight:700}textarea{width:100%;padding:9px;font:inherit;border:1px solid var(--crm-line);border-radius:8px;resize:vertical}fieldset{display:grid;gap:7px;margin:0;padding:11px;border:1px solid var(--crm-line);border-radius:9px}legend{padding:0 5px;color:var(--crm-text-muted);font-size:9px;font-weight:800}.choice{display:flex;align-items:center;gap:7px;font-weight:600}.choice input{margin:0}.error{display:grid;gap:4px;padding:9px;color:var(--crm-danger);background:var(--crm-danger-soft)}footer{justify-content:flex-end;gap:8px;border-top:1px solid var(--crm-line)}footer button{display:flex;align-items:center;gap:6px}
</style>
