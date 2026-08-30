<script setup lang="ts">
import { ArrowDownRight, ArrowUpRight } from '@lucide/vue'
import type { Component } from 'vue'

defineProps<{ label: string; value: string; detail: string; delta?: string; direction?: 'up' | 'down'; icon: Component; tone?: 'teal' | 'lime' | 'amber' | 'navy' }>()
</script>

<template>
  <article class="kpi-card" :class="`tone-${tone ?? 'teal'}`">
    <div class="kpi-top"><span class="kpi-icon"><component :is="icon" :size="19" /></span><span v-if="delta" class="delta" :class="direction"><ArrowUpRight v-if="direction !== 'down'" :size="13" /><ArrowDownRight v-else :size="13" />{{ delta }}</span></div>
    <strong class="tabular">{{ value }}</strong>
    <h3>{{ label }}</h3>
    <p>{{ detail }}</p>
  </article>
</template>

<style scoped>
.kpi-card { position: relative; min-width: 0; overflow: hidden; padding: 17px; background: #fff; border: 1px solid var(--crm-line); border-radius: var(--crm-radius-md); }
.kpi-card::after { position: absolute; right: -24px; bottom: -30px; width: 82px; height: 82px; background: var(--accent-soft); border-radius: 50%; content: ''; }
.tone-teal { --accent: var(--crm-teal); --accent-soft: var(--crm-brand-soft); }
.tone-lime { --accent: #7d9427; --accent-soft: #eff4d7; }
.tone-amber { --accent: #a8791f; --accent-soft: #fff4dd; }
.tone-navy { --accent: var(--crm-navy); --accent-soft: #ECEDEF; }
.kpi-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.kpi-icon { display: grid; width: 34px; height: 34px; place-items: center; color: var(--accent); background: var(--accent-soft); border-radius: 10px; }
.delta { display: flex; align-items: center; gap: 2px; color: var(--crm-teal); font-size: 10px; font-weight: 700; }
.delta.down { color: var(--crm-danger); }
strong { position: relative; z-index: 1; display: block; color: var(--crm-navy); font-size: clamp(21px, 2vw, 28px); letter-spacing: -.04em; }
h3 { position: relative; z-index: 1; margin: 4px 0 8px; font-size: 12px; }
p { position: relative; z-index: 1; margin: 0; color: var(--crm-text-muted); font-size: 10px; line-height: 1.45; }
</style>
