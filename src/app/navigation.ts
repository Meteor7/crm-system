import { BarChart3, BriefcaseBusiness, Building2, CalendarDays, ClipboardCheck, ContactRound, Cpu, FileCheck2, FileText, FlaskConical, FolderLock, PackageCheck, UserRoundSearch } from '@lucide/vue'
import type { Component } from 'vue'
import type { Capability, UserRole } from '@/types/crm'

export interface NavigationItem {
  key: string
  label: string
  path: string
  icon: Component
  badge?: string
  capabilities: Capability[]
}

export interface NavigationGroup {
  label: string
  hiddenRoles?: UserRole[]
  items: NavigationItem[]
}

export const navigation: NavigationGroup[] = [
  {
    label: '管理中心',
    items: [
      { key: 'dashboard', label: '信息中心', path: '/dashboard', icon: BarChart3, capabilities: ['dashboard:view'] },
      { key: 'calendar', label: 'Calendar', path: '/calendar', icon: CalendarDays, capabilities: ['service:view'] },
    ],
  },
  {
    label: 'Sales 中心',
    hiddenRoles: ['Engineer'],
    items: [
      { key: 'leads', label: 'Leads', path: '/leads', icon: UserRoundSearch, capabilities: ['deal:view'] },
      { key: 'opportunities', label: 'Opportunities', path: '/opportunities', icon: BriefcaseBusiness, capabilities: ['deal:view'] },
      { key: 'accounts', label: '客户档案', path: '/accounts', icon: Building2, capabilities: ['account:view'] },
      { key: 'contacts', label: '联系人', path: '/contacts', icon: ContactRound, capabilities: ['contact:view'] },
      { key: 'quotations', label: 'Quotations', path: '/quotations', icon: FileText, capabilities: ['quotation:view'] },
      { key: 'booking', label: 'Booking', path: '/booking', icon: PackageCheck, capabilities: ['deal:view'] },
      { key: 'visits', label: '拜访管理', path: '/visits', icon: CalendarDays, capabilities: ['visit:view'] },
    ],
  },
  {
    label: 'Demo 中心',
    items: [
      { key: 'demo-workflow', label: 'Demo 档案', path: '/demo-workflow', icon: ClipboardCheck, capabilities: ['demo_request:view', 'evaluation:view'] },
      { key: 'demo-requests', label: 'Demo Request', path: '/demo-requests', icon: FileText, capabilities: ['demo_request:view'] },
      { key: 'demo-test', label: 'Demo Test', path: '/evaluations', icon: FlaskConical, capabilities: ['evaluation:view'] },
    ],
  },
  {
    label: '设备与资料',
    items: [
      { key: 'installed-tools', label: 'Installed Tools', path: '/installed-tools', icon: Cpu, capabilities: ['account:view'] },
      { key: 'rfqs', label: 'RFQ Center', path: '/rfqs', icon: FileCheck2, capabilities: ['rfq:view'] },
      { key: 'document-center', label: 'Document Center', path: '/document-center', icon: FolderLock, capabilities: ['contract:view', 'account:view'] },
    ],
  },
]
