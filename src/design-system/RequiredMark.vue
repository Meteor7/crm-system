<script setup lang="ts">
withDefaults(defineProps<{ show?: boolean }>(), { show: true })
</script>

<template>
  <span v-if="show" class="required-mark" data-required-mark aria-hidden="true">*</span>
</template>

<style scoped>
.required-mark{margin-left:3px;color:var(--crm-danger)!important;font-size:1.35em!important;font-weight:800}
</style>
