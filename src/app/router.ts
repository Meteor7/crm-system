import { createMemoryHistory, createRouter, createWebHashHistory, createWebHistory, type RouteLocationGeneric, type RouteLocationRaw, type RouteRecordRaw } from 'vue-router'
import { defineComponent } from 'vue'
import { usesFrappeRuntime } from './runtime-mode'

function placeholder(title: string) {
  return defineComponent({
    name: `${title}Placeholder`,
    template: `<div class="route-placeholder" data-testid="route-placeholder">${title}</div>`,
  })
}

function retiredSalesRedirect(to: RouteLocationGeneric): RouteLocationRaw {
  const { view: _view, ...query } = to.query
  return { name: 'opportunities', query }
}

function retiredCombinedRedirect(to: RouteLocationGeneric): RouteLocationRaw {
  const { view, ...query } = to.query
  return view === 'bookings' || view === 'booking'
    ? { name: 'booking', query }
    : { name: 'opportunities', query }
}

function retiredLeadsOpportunitiesRedirect(to: RouteLocationGeneric): RouteLocationRaw {
  const { view, ...query } = to.query
  return { name: view === 'opportunities' ? 'opportunities' : 'leads', query }
}

export const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: 'dashboard', component: () => import('@/pages/DashboardPage.vue') },
  { path: '/accounts', name: 'accounts', component: () => import('@/pages/AccountsPage.vue') },
  { path: '/accounts/:accountId', name: 'account-detail', component: () => import('@/pages/AccountDetailPage.vue'), meta: { navigationPath: '/accounts' } },
  { path: '/contacts', name: 'contacts', component: () => import('@/pages/ContactsPage.vue') },
  { path: '/contacts/:contactId', name: 'contact-detail', component: () => import('@/pages/ContactDetailPage.vue'), meta: { navigationPath: '/contacts' } },
  { path: '/leads-opportunities', name: 'leads-opportunities', redirect: retiredLeadsOpportunitiesRedirect },
  { path: '/leads', name: 'leads', component: () => import('@/pages/LeadsOpportunitiesPage.vue'), props: { fixedView: 'leads' } },
  { path: '/leads/:leadId', name: 'lead-detail', component: () => import('@/pages/LeadDetailPage.vue'), meta: { navigationPath: '/leads' } },
  { path: '/opportunities', name: 'opportunities', component: () => import('@/pages/LeadsOpportunitiesPage.vue'), props: { fixedView: 'opportunities' } },
  { path: '/opportunities/:opportunityId', name: 'opportunity-detail', component: () => import('@/pages/OpportunityDetailPage.vue'), meta: { navigationPath: '/opportunities' } },
  { path: '/booking', name: 'booking', component: () => import('@/pages/BookingPage.vue') },
  { path: '/booking/:bookingId', name: 'booking-detail', component: () => import('@/pages/BookingDetailPage.vue'), meta: { navigationPath: '/booking' } },
  { path: '/visits', name: 'visits', component: () => import('@/pages/VisitsPage.vue') },
  { path: '/visits/:visitId', name: 'visit-detail', component: () => import('@/pages/VisitDetailPage.vue'), meta: { navigationPath: '/visits' } },
  { path: '/stakeholders', redirect: '/contacts' },
  { path: '/requirements', name: 'requirements', component: () => import('@/pages/RequirementsPage.vue') },
  { path: '/pipeline', redirect: { name: 'opportunities' } },
  { path: '/opportunities-booking', redirect: retiredCombinedRedirect },
  { path: '/opportunity-strategy', redirect: retiredSalesRedirect },
  { path: '/demo-requests', name: 'demo-requests', component: () => import('@/pages/DemoRequestsPage.vue') },
  { path: '/evaluations', name: 'evaluations', component: () => import('@/pages/EvaluationsPage.vue') },
  { path: '/demo-workflow/:demoId', name: 'demo-detail', component: () => import('@/pages/DemoDetailPage.vue'), meta: { navigationPath: '/demo-workflow' } },
  { path: '/demo-workflow', name: 'demo-workflow', component: () => import('@/pages/DemoWorkflowPage.vue') },
  { path: '/contracts', name: 'contracts', component: () => import('@/pages/ContractsPage.vue') },
  { path: '/quotations', name: 'quotations', component: () => import('@/pages/QuotationsPage.vue') },
  { path: '/quotations/:quotationId', name: 'quotation-detail', component: () => import('@/pages/QuotationDetailPage.vue'), meta: { navigationPath: '/quotations' } },
  { path: '/installed-tools', name: 'installed-tools', component: () => import('@/pages/InstalledToolsPage.vue') },
  { path: '/calendar', name: 'calendar', component: () => import('@/pages/ServiceCalendarPage.vue') },
  { path: '/service-calendar', redirect: '/calendar' },
  { path: '/document-center', name: 'document-center', component: () => import('@/pages/DocumentCenterPage.vue') },
  { path: '/rfqs', name: 'rfqs', component: () => import('@/pages/RfqsPage.vue') },
  { path: '/rfqs/:rfqId', name: 'rfq-detail', component: () => import('@/pages/RfqDetailPage.vue'), meta: { navigationPath: '/rfqs' } },
]

export function createAppRouter() {
  return createRouter({ history: createMemoryHistory(), routes })
}

const useHashHistory = usesFrappeRuntime(import.meta.env.MODE)
export const router = createRouter({ history: useHashHistory ? createWebHashHistory() : createWebHistory(), routes })
