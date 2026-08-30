import type { DemoWorkflowDto } from '@/types/workspaces'

export type DemoArchiveGroupMode = 'customer' | 'equipment'

export interface DemoArchiveGroup {
  label: string
  count: number
  items: DemoWorkflowDto[]
}

export function isConcreteEngineerOwner(value: string | null | undefined) {
  const normalized = value?.trim() ?? ''
  return Boolean(normalized && !['FAE Team', '未分配'].includes(normalized))
}

export function groupDemoArchives(
  items: DemoWorkflowDto[],
  mode: DemoArchiveGroupMode,
): DemoArchiveGroup[] {
  const grouped = new Map<string, DemoWorkflowDto[]>()
  for (const item of items) {
    const label = mode === 'customer'
      ? item.account
      : item.equipment.trim() || '未指定设备'
    grouped.set(label, [...(grouped.get(label) ?? []), item])
  }

  return [...grouped.entries()]
    .map(([label, rows]) => ({
      label,
      count: rows.length,
      items: [...rows].sort((left, right) =>
        (right.tracking?.lastProgressAt ?? '').localeCompare(left.tracking?.lastProgressAt ?? ''),
      ),
    }))
    .sort((left, right) => {
      if (left.label === '未指定设备') return 1
      if (right.label === '未指定设备') return -1
      return left.label.localeCompare(right.label, 'zh-CN')
    })
}
