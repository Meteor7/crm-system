import { BarChart3, BriefcaseBusiness, Building2, CalendarDays, ClipboardCheck, ContactRound, Cpu, FileCheck2, FileText, FlaskConical, FolderLock, PackageCheck, UserRoundSearch } from '@lucide/vue'
import type { Component } from 'vue'
import type { Capability, UserRole } from '@/types/crm'

export interface NavigationItem {
  key: string
  label: string
  i18nKey?: string
  path: string
  icon: Component
  badge?: string
  capabilities: Capability[]
}

export interface NavigationGroup {
  label: string
  i18nKey?: string
  hiddenRoles?: UserRole[]
  items: NavigationItem[]
}

export const navigation: NavigationGroup[] = [
  {
    label: '管理中心',
    i18nKey: 'nav.management',
    items: [
      { key: 'dashboard', label: '信息中心', i18nKey: 'nav.dashboard', path: '/dashboard', icon: BarChart3, capabilities: ['dashboard:view'] },
      { key: 'calendar', label: 'Calendar', i18nKey: 'nav.calendar', path: '/calendar', icon: CalendarDays, capabilities: ['service:view'] },
    ],
  },
  {
    label: 'Sales 中心',
    i18nKey: 'nav.sales',
    hiddenRoles: ['Engineer'],
    items: [
      { key: 'leads', label: 'Leads', i18nKey: 'nav.leads', path: '/leads', icon: UserRoundSearch, capabilities: ['deal:view'] },
      { key: 'opportunities', label: 'Opportunities', i18nKey: 'nav.opportunities', path: '/opportunities', icon: BriefcaseBusiness, capabilities: ['deal:view'] },
      { key: 'accounts', label: '客户档案', i18nKey: 'nav.accounts', path: '/accounts', icon: Building2, capabilities: ['account:view'] },
      { key: 'contacts', label: '联系人', i18nKey: 'nav.contacts', path: '/contacts', icon: ContactRound, capabilities: ['contact:view'] },
      { key: 'quotations', label: 'Quotations', i18nKey: 'nav.quotations', path: '/quotations', icon: FileText, capabilities: ['quotation:view'] },
      { key: 'booking', label: 'Booking', i18nKey: 'nav.booking', path: '/booking', icon: PackageCheck, capabilities: ['deal:view'] },
      { key: 'visits', label: '拜访管理', i18nKey: 'nav.visits', path: '/visits', icon: CalendarDays, capabilities: ['visit:view'] },
    ],
  },
  {
    label: 'Demo 中心',
    i18nKey: 'nav.demo',
    items: [
      { key: 'demo-workflow', label: 'Demo 档案', i18nKey: 'nav.demoArchive', path: '/demo-workflow', icon: ClipboardCheck, capabilities: ['demo_request:view', 'evaluation:view'] },
      { key: 'demo-requests', label: 'Demo Request', i18nKey: 'nav.demoRequests', path: '/demo-requests', icon: FileText, capabilities: ['demo_request:view'] },
      { key: 'demo-test', label: 'Demo Test', i18nKey: 'nav.demoTest', path: '/evaluations', icon: FlaskConical, capabilities: ['evaluation:view'] },
    ],
  },
  {
    label: '设备与资料',
    i18nKey: 'nav.data',
    items: [
      { key: 'installed-tools', label: 'Installed Tools', i18nKey: 'nav.installedTools', path: '/installed-tools', icon: Cpu, capabilities: ['account:view'] },
      { key: 'rfqs', label: 'RFQ Center', i18nKey: 'nav.rfqs', path: '/rfqs', icon: FileCheck2, capabilities: ['rfq:view'] },
      { key: 'document-center', label: 'Document Center', i18nKey: 'nav.documents', path: '/document-center', icon: FolderLock, capabilities: ['contract:view', 'account:view'] },
    ],
  },
]
