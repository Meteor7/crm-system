<script setup lang="ts">
defineProps<{ title?: string; eyebrow?: string; description?: string; flush?: boolean }>()
</script>

<template>
  <section class="section-card" :class="{ flush }">
    <header v-if="title || eyebrow || $slots.action">
      <div><span v-if="eyebrow">{{ eyebrow }}</span><h2 v-if="title">{{ title }}</h2><p v-if="description">{{ description }}</p></div>
      <slot name="action" />
    </header>
    <div class="section-body"><slot /></div>
  </section>
</template>

<style scoped>
.section-card { min-width: 0; background: var(--crm-surface-raised); border: 1px solid var(--crm-line); border-radius: var(--crm-radius-md); box-shadow: 0 1px 1px rgba(31,35,41,.02); }
.section-card > header { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 19px 20px 14px; }
header span { color: var(--crm-teal); font-size: 9px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
h2 { margin: 3px 0 0; color: var(--crm-navy); font-size: 15px; letter-spacing: -.01em; }
p { margin: 5px 0 0; color: var(--crm-text-muted); font-size: 11px; }
.section-body { padding: 6px 20px 20px; }
.flush .section-body { padding: 0; }
</style>
