<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from '@/i18n'
import { closeModal, modalLayer, openModal, topModal } from './modal-stack'

/** `danger`: the action removes or closes something (an archive, a loss); the confirm button says so by its colour. */
defineProps<{ title: string; eyebrow?: string; busy?: boolean; wide?: boolean; submitDisabled?: boolean; submitLabel?: string; cancelLabel?: string; closeLabel?: string; busyLabel?: string; danger?: boolean }>()
const { t } = useI18n()
const emit = defineEmits<{ close: []; submit: [] }>()
const host = ref<HTMLElement | null>(null)
const card = ref<HTMLElement | null>(null)
let opener: HTMLElement | null = null
const layer = computed(() => ({ zIndex: modalLayer(host.value) }))
function focusable() {
  return [...(card.value?.querySelectorAll<HTMLElement>('button, input, select, textarea, a[href], [tabindex]') ?? [])]
    .filter(element => {
      if (element.tabIndex < 0 || element.matches(':disabled, input[type="hidden"]') || element.closest('[hidden], [inert]')) return false
      for (let current: HTMLElement | null = element; current && current !== host.value; current = current.parentElement) {
        const style = getComputedStyle(current)
        if (style.display === 'none' || style.visibility === 'hidden') return false
      }
      return true
    })
}
function keydown(event: KeyboardEvent) {
  if (topModal() !== host.value || event.isComposing || event.defaultPrevented) return
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    emit('close')
  } else if (event.key === 'Tab') {
    const items = focusable(), first = items[0], last = items.at(-1)
    if (!first) { event.preventDefault(); card.value?.focus(); return }
    if (!card.value?.contains(document.activeElement) || (event.shiftKey ? document.activeElement === first : document.activeElement === last)) {
      event.preventDefault()
      ;(event.shiftKey ? last : first)?.focus()
    }
  }
}
onMounted(async () => {
  opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
  if (host.value) openModal(host.value)
  document.addEventListener('keydown', keydown)
  await nextTick()
  if (host.value?.isConnected && topModal() === host.value) (focusable()[0] ?? card.value)?.focus({ preventScroll: true })
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', keydown)
  if (host.value) closeModal(host.value)
})
onUnmounted(async () => {
  await nextTick()
  const activeModal = topModal()
  if (opener?.isConnected && (!activeModal || activeModal.contains(opener))) opener.focus({ preventScroll: true })
})
</script>

<template>
  <div ref="host" class="modal-host" :style="layer" role="presentation" @mousedown.self="$emit('close')">
    <section ref="card" class="modal-card" :class="{ wide }" role="dialog" aria-modal="true" :aria-label="title" tabindex="-1">
      <header><div><span>{{ eyebrow || 'WORKFLOW' }}</span><h2>{{ title }}</h2></div><button type="button" :aria-label="closeLabel ?? t('common.close')" @click="$emit('close')"><X :size="18" /></button></header>
      <form @submit.prevent="$emit('submit')">
        <div class="modal-body"><slot /></div>
        <div v-if="$slots.feedback" class="modal-feedback"><slot name="feedback" /></div>
        <footer><button class="secondary-button" type="button" @click="$emit('close')">{{ cancelLabel ?? t('common.cancel') }}</button><button class="primary-button" :class="{ 'danger-action': danger }" data-modal-submit type="submit" :disabled="busy || submitDisabled">{{ busy ? (busyLabel ?? t('common.processing')) : submitLabel || t('common.saveAndContinue') }}</button></footer>
      </form>
    </section>
  </div>
</template>

<style scoped>
.modal-host{position:fixed;inset:0;display:grid;overflow-y:auto;overscroll-behavior:contain;place-items:center;padding:24px;background:rgba(7,29,37,.5)}
.modal-card{width:min(680px,100%);max-height:min(760px,90dvh);overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:16px;box-shadow:0 26px 70px rgba(8,32,40,.25)}
.modal-card.wide{width:min(1120px,100%)}
.modal-card>header{display:flex;align-items:center;justify-content:space-between;padding:20px 22px;color:#fff;background:var(--crm-navy)}
.modal-card>header span{color:#98c9c4;font-size:8px;font-weight:800;letter-spacing:.12em}.modal-card h2{margin:4px 0 0;font-size:17px}.modal-card>header button{display:grid;width:32px;height:32px;place-items:center;color:#fff;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:9px;cursor:pointer}
.modal-card form{display:flex;max-height:calc(min(760px,90dvh) - 78px);flex-direction:column}.modal-body{overflow:auto;padding:20px 22px}.modal-card footer{display:flex;justify-content:flex-end;gap:8px;padding:14px 22px;background:#F5F7FB;border-top:1px solid var(--crm-line)}
.modal-card footer .primary-button.danger-action{color:#fff;background:#a93333;border-color:#a93333;box-shadow:0 5px 14px rgba(169,51,51,.2)}.modal-card footer .primary-button.danger-action:not(:disabled):hover{background:#8f2a2a;border-color:#8f2a2a;box-shadow:0 7px 18px rgba(169,51,51,.28)}.modal-card footer .primary-button.danger-action:disabled{color:#819092;background:#e8eeed;border-color:#d9e3e1;box-shadow:none}
.modal-card>header,.modal-card footer,.modal-feedback{flex-shrink:0}.modal-feedback{padding:10px 22px 0;max-height:25dvh;overflow:auto}.modal-card{outline:none}
@media(max-width:560px){.modal-host{align-items:end;padding:0}.modal-card{max-height:92dvh;border-radius:16px 16px 0 0}}
</style>
