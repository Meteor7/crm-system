import { createApp, markRaw } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import type { CrmApi } from '@/api'
import AppShell from '@/app/AppShell.vue'
import { useAppStore } from '@/stores/app'
import ApprovalsDemoPage from './ApprovalsDemoPage.vue'
import ApprovalActionDemoPage from './ApprovalActionDemoPage.vue'
import { demoViewer } from './demo-fixtures'
import '@/design-system/tokens.css'
import '@/design-system/base.css'
import '@/design-system/workspace.css'
import '@/design-system/typography.css'

// Standalone preview only: the production entry, Frappe adapter and real business records are untouched.
const viewer = demoViewer('Manager')
const pinia = createPinia(), app = useAppStore(pinia)
app.bootstrap = { user: { id: viewer.id, name: viewer.name, initials: '王', role: viewer.role, team: 'Preview' }, capabilities: [...viewer.capabilities], version: 'approvals-ui-preview' }
app.activeApi = markRaw({ listNotifications: async () => ({ data: { items: [] }, warnings: [], meta: { total: 0 } }) }) as unknown as CrmApi
const router = createRouter({ history: createWebHashHistory(), routes: [
  { path: '/', component: ApprovalsDemoPage, meta: { navigationPath: '/dashboard' } },
  { path: '/dashboard', component: ApprovalsDemoPage },
  ...['/demo-requests', '/quotations/:quotationId', '/opportunities/:opportunityId', '/visits', '/rfqs/:rfqId', '/document-center', '/evaluations'].map(path => ({ path, component: ApprovalActionDemoPage, meta: { navigationPath: '/dashboard' } })),
  { path: '/:pathMatch(.*)*', component: ApprovalsDemoPage, meta: { navigationPath: '/dashboard' } },
] })
createApp(AppShell).use(pinia).use(router).mount('#app')
