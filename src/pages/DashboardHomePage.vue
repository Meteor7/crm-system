<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import { api as defaultApi, type CrmApi } from '@/api'
import { hasCapability } from '@/domain/permissions'
import { useAppStore } from '@/stores/app'

// Sales and Engineer keep the information centre /dashboard opened before the cockpit
// arrived. Neither page mounts until the session is known, so a Manager never pays for
// the information centre's queries on the way to the cockpit.
const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const ReviewPage = defineAsyncComponent(() => import('./ReviewPage.vue'))
const DashboardPage = defineAsyncComponent(() => import('./DashboardPage.vue'))

const app = useAppStore()
const sessionKnown = ref(false)
const cockpit = computed(() => hasCapability(app.bootstrap, 'cockpit:view'))

onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  sessionKnown.value = true
})
</script>

<template>
  <ReviewPage v-if="sessionKnown && cockpit" :api-client="apiClient" />
  <DashboardPage v-else-if="sessionKnown" :api-client="apiClient" />
</template>
