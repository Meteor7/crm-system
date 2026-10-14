<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { useI18n } from '@/i18n'
defineProps<{ pendingCount?: number }>()
const app = useAppStore(), { locale } = useI18n()
const tabs = computed(() => app.bootstrap?.user.role === 'Manager'
  ? [{ path: '/dashboard', label: 'Review' }, { path: '/plan', label: 'Plan' }, { path: '/warnings', label: 'Warnings' }, { path: '/opportunity-board', label: 'Opportunities' }, { path: '/approvals', label: locale.value === 'en-US' ? 'Pending approvals' : '待审批' }]
  : [{ path: '/dashboard', label: locale.value === 'en-US' ? 'Information overview' : '信息概览' }, { path: '/approvals', label: locale.value === 'en-US' ? 'Pending approvals' : '待审批' }])
</script>
<template><nav class="approval-workspace-tabs cockpit-tabs" :aria-label="locale === 'en-US' ? 'Workspace pages' : '工作台内页'"><RouterLink v-for="tab in tabs" :key="tab.path" :to="tab.path" :aria-current="$route.path === tab.path ? 'page' : undefined">{{ tab.label }}<span v-if="tab.path === '/approvals' && pendingCount !== undefined" class="cockpit-tab-count">{{ pendingCount }}</span></RouterLink></nav></template>
<style scoped>.approval-workspace-tabs{margin-bottom:22px}</style>
<style scoped src="@/features/cockpit/workspace-tabs.css"></style>
