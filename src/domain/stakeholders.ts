import type { ContactDto } from '@/types/crm'

export interface StakeholderNode {
  contact: ContactDto
  children: StakeholderNode[]
  dataQuality?: 'missing-parent' | 'cycle'
}

export function validateReportingLine(rows: ContactDto[], contactId: string, reportsToContactId?: string) {
  if (!reportsToContactId) return
  if (contactId === reportsToContactId) throw new Error('关键人不能汇报给自己')
  const byId = new Map(rows.map((item) => [item.id, item]))
  const contact = byId.get(contactId)
  let current: string | undefined = reportsToContactId
  const visited = new Set<string>()
  while (current) {
    if (current === contactId) throw new Error('该汇报关系会形成循环汇报')
    if (visited.has(current)) throw new Error('现有数据中存在循环汇报')
    visited.add(current)
    const parent = byId.get(current)
    if (parent && contact && parent.accountId !== contact.accountId) {
      throw new Error('汇报对象必须属于同一客户')
    }
    current = parent?.reportsToContactId
  }
}

export function buildStakeholderForest(rows: ContactDto[]): StakeholderNode[] {
  const nodes = new Map(rows.map((contact) => [contact.id, { contact, children: [] } as StakeholderNode]))
  const roots: StakeholderNode[] = []
  rows.forEach((contact) => {
    const node = nodes.get(contact.id)!
    if (!contact.reportsToContactId) {
      roots.push(node)
      return
    }
    const parent = nodes.get(contact.reportsToContactId)
    if (!parent || parent.contact.accountId !== contact.accountId) {
      node.dataQuality = 'missing-parent'
      roots.push(node)
      return
    }
    const visited = new Set([contact.id])
    let ancestorId: string | undefined = contact.reportsToContactId
    let cycle = false
    while (ancestorId) {
      if (visited.has(ancestorId)) { cycle = true; break }
      visited.add(ancestorId)
      ancestorId = nodes.get(ancestorId)?.contact.reportsToContactId
    }
    if (cycle) {
      node.dataQuality = 'cycle'
      roots.push(node)
      return
    }
    parent.children.push(node)
  })
  return roots
}
