<script setup lang="ts">
import type { Component } from 'vue'
import type { Tone } from '@/demo/operations-data'

withDefaults(defineProps<{ label: string; value: string; detail?: string; delta?: string; tone?: Tone; icon?: Component }>(), { detail: '', delta: '', tone: 'neutral', icon: undefined })
</script>

<template>
  <article class="workspace-metric" :class="`is-${tone}`">
    <div class="metric-heading"><span>{{ label }}</span><component :is="icon" v-if="icon" :size="17" /></div>
    <strong>{{ value }}</strong>
    <footer><small>{{ detail }}</small><b v-if="delta">{{ delta }}</b></footer>
  </article>
</template>
