<script setup lang="ts">
import { X } from '@lucide/vue'
import { useI18n } from '@/i18n'

defineProps<{ title: string; eyebrow?: string; busy?: boolean; wide?: boolean; submitDisabled?: boolean; submitLabel?: string; cancelLabel?: string; closeLabel?: string; busyLabel?: string }>()
const { t } = useI18n()
defineEmits<{ close: []; submit: [] }>()
</script>

<template>
  <div class="modal-host" role="presentation" @mousedown.self="$emit('close')">
    <section class="modal-card" :class="{ wide }" role="dialog" aria-modal="true" :aria-label="title">
      <header><div><span>{{ eyebrow || 'WORKFLOW' }}</span><h2>{{ title }}</h2></div><button type="button" :aria-label="closeLabel ?? t('common.close')" @click="$emit('close')"><X :size="18" /></button></header>
      <form @submit.prevent="$emit('submit')">
        <div class="modal-body"><slot /></div>
        <footer><button class="secondary-button" type="button" @click="$emit('close')">{{ cancelLabel ?? t('common.cancel') }}</button><button class="primary-button" data-modal-submit type="submit" :disabled="busy || submitDisabled">{{ busy ? (busyLabel ?? t('common.processing')) : submitLabel || t('common.saveAndContinue') }}</button></footer>
      </form>
    </section>
  </div>
</template>

<style scoped>
.modal-host{position:absolute;inset:0;z-index:2200;display:grid;min-height:100%;place-items:center;padding:24px;background:rgba(7,29,37,.5)}
.modal-card{width:min(680px,100%);max-height:min(760px,90dvh);overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:16px;box-shadow:0 26px 70px rgba(8,32,40,.25)}
.modal-card.wide{width:min(1120px,100%)}
.modal-card>header{display:flex;align-items:center;justify-content:space-between;padding:20px 22px;color:#fff;background:var(--crm-navy)}
.modal-card>header span{color:#98c9c4;font-size:8px;font-weight:800;letter-spacing:.12em}.modal-card h2{margin:4px 0 0;font-size:17px}.modal-card>header button{display:grid;width:32px;height:32px;place-items:center;color:#fff;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:9px;cursor:pointer}
.modal-card form{display:flex;max-height:calc(min(760px,90dvh) - 78px);flex-direction:column}.modal-body{overflow:auto;padding:20px 22px}.modal-card footer{display:flex;justify-content:flex-end;gap:8px;padding:14px 22px;background:#FAF8F5;border-top:1px solid var(--crm-line)}
@media(max-width:560px){.modal-host{align-items:end;padding:0}.modal-card{max-height:92dvh;border-radius:16px 16px 0 0}}
</style>
