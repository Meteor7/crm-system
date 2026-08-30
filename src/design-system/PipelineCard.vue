<script setup lang="ts">withDefaults(defineProps<{ tone?: string; title: string; summary: string; meta?: string; reason?: string; selected?: boolean }>(),{tone:'healthy',meta:'',reason:'',selected:false});defineEmits<{open:[]}>()</script>
<template><button type="button" class="card" :class="[`tone-${tone}`,{selected}]" @click="$emit('open')"><strong>{{ title }}</strong><span>{{ summary }}</span><small v-if="meta">{{ meta }}</small><em v-if="reason">{{ reason }}</em></button></template>
<style scoped>
.card{--tone:var(--crm-board-positive);position:relative;display:grid;width:100%;gap:var(--crm-space-2);padding:var(--crm-space-6) var(--crm-space-6) var(--crm-space-5) var(--crm-space-7);color:var(--crm-navy);background:var(--crm-surface-raised);border:1px solid var(--crm-line);border-radius:var(--crm-radius-sm);text-align:left;cursor:pointer}
.card:before{position:absolute;inset:-1px auto -1px -1px;width:var(--crm-board-card-marker-width);background:var(--tone);content:""}
.tone-stalled,.tone-warning{--tone:var(--crm-board-warning)}
.tone-critical,.tone-danger{--tone:var(--crm-board-danger)}
.tone-info,.tone-current{--tone:var(--crm-teal)}
.card.selected{border-color:var(--crm-pipeline-accent);box-shadow:0 var(--crm-space-1) var(--crm-space-6) var(--crm-board-overlay)}
strong{font-size:var(--crm-font-lg)}
span{font-size:var(--crm-font-sm);line-height:1.45}
small{color:var(--crm-text-muted)}
em{padding-top:var(--crm-space-2);color:var(--tone);border-top:1px solid var(--crm-line);font-size:var(--crm-font-xs);font-style:normal;font-weight:700}
</style>
