import type { ListQuery } from '@/types/crm'

export type RfqStatus = 'Engineer Review' | 'Manager Approval' | 'Sales Revision' | 'Approved'
export type RfqVersionStatus = 'Engineer Review' | 'Manager Approval' | 'Returned' | 'Approved'

export interface RfqOpportunityDto {
  id: string
  title: string
  accountId: string
  account: string
  siteId: string
  site: string
  stage: string
  owner: string
  toolType: string
  poDate: string
}

export interface RfqSummaryDto {
  id: string
  opportunity: RfqOpportunityDto
  salesOwner: string
  salesOwnerName: string
  engineerOwner: string
  engineerOwnerName: string
  status: RfqStatus
  currentVersionId: string
  latestVersion: number
  fileName: string
  note: string
  approvedBy: string
  approvedAt: string
  modified: string
}

export interface RfqVersionDto {
  id: string
  version: number
  status: RfqVersionStatus
  fileName: string
  mimeType: string
  size: number
  uploadedBy: string
  uploadedByName: string
  uploadedAt: string
  engineerComment: string
  engineerCommentedBy: string
  engineerCommentedByName: string
  engineerCommentedAt: string
  managerDecision: '' | 'Approved' | 'Returned'
  managerComment: string
  managerDecidedBy: string
  managerDecidedByName: string
  managerDecidedAt: string
}

export interface RfqDetailDto extends RfqSummaryDto {
  currentVersion: RfqVersionDto
  versions: RfqVersionDto[]
}

export interface RfqListQuery extends ListQuery {
  status?: RfqStatus | 'All'
  opportunityId?: string
}

export interface CreateRfqInput {
  opportunityId: string
  engineerId: string
  note?: string
}

export interface ReviewRfqInput {
  decision: 'Approved' | 'Returned'
  comment: string
}
