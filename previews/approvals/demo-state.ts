import { reactive } from 'vue'
import { visibleApprovals, type ApprovalViewer } from '@/features/approvals/approval-queue'
import { demoApprovals } from './demo-fixtures'

// Read receipts for the isolated preview, scoped to its current identity. No business approval is performed.
const viewed = reactive<Record<string, string[]>>({})
export function previewApprovalItems(viewer: ApprovalViewer) {
  return visibleApprovals(demoApprovals(), viewer).map(item => ({ ...item, unread: item.unread && !(viewed[viewer.id] ?? []).includes(item.id) }))
}
export function markPreviewViewed(viewer: ApprovalViewer, id: string) {
  if (!visibleApprovals(demoApprovals(), viewer).some(item => item.id === id)) return
  viewed[viewer.id] = [...new Set([...(viewed[viewer.id] ?? []), id])]
}
