export type QuotationStatus = 'Draft' | 'Published' | 'Accepted' | 'Rejected' | 'Expired' | 'Superseded'
export type QuotationApprovalStatus = 'Not Submitted' | 'Pending' | 'Approved' | 'Rejected' | 'Not Required'
export type QuotationDiscountType = 'None' | 'Percentage' | 'Fixed Amount'
export type QuotationLineType = 'Device' | 'System' | 'Accessory'
export type QuotationCatalogLevel = QuotationLineType
export type QuotationPricingMode = 'Included' | 'Charged'
export type QuotationType = 'Device' | 'Service'

export interface QuotationListQuery {
  opportunityId?: string
  status?: QuotationStatus | 'All'
  approvalStatus?: QuotationApprovalStatus | 'All'
  quotationType?: QuotationType | 'All'
  page?: number
  pageSize?: number
}

export interface QuotationSummaryDto {
  id: string
  refNo: string
  quotationType: QuotationType
  opportunityId: string
  opportunityTitle: string
  accountId: string
  accountName: string
  owner: string
  status: Exclude<QuotationStatus, 'Superseded'>
  approvalStatus: QuotationApprovalStatus
  latestVersion: number
  currentVersionId: string
  currentPublishedVersionId: string
  modified: string
}

export interface QuotationCatalogItemDto {
  id: string
  level: QuotationCatalogLevel
  name: string
  parentId: string
}

export interface QuotationItemDto {
  lineKey: string
  lineType: QuotationLineType
  parentDeviceKey: string
  parentSystemKey?: string
  catalogItemId?: string
  name: string
  model: string
  description: string
  pricingMode: QuotationPricingMode
  quantity: number
  unitPrice: string
  lineAmount: string
}

export interface QuotationPaymentTermDto {
  percentage: string
  triggerCondition: string
  description: string
}

export interface QuotationDraftInput {
  primaryContactId: string
  addressId: string
  quoteDate: string
  validityMonths: number
  items: QuotationItemDto[]
  discountType: QuotationDiscountType
  discountValue: string
  paymentTerms: QuotationPaymentTermDto[]
  deliveryMonths: number
  warrantyMonths: number
}

export interface CreateQuotationInput extends Partial<QuotationDraftInput> {
  quotationType: QuotationType
  opportunityId?: string
  accountId?: string
}

export interface QuotationVersionDto extends QuotationDraftInput {
  id: string
  version: number
  quotationType: QuotationType
  status: QuotationStatus
  approvalStatus: QuotationApprovalStatus
  currentApprovalId: string
  modified: string
  refNo: string
  opportunityId: string
  accountId: string
  owner: string
  addressRestricted?: boolean
  customerName: string
  attentionName: string
  attentionTitle: string
  attentionPhone: string
  addressText: string
  currency: 'CNY'
  validUntil: string
  incoterm: string
  deliveryStart: string
  warrantyStart: string
  installation: string
  training: string
  documentation: string
  packing: string
  subtotal: string
  discountAmount: string
  total: string
  feedbackDate: string
  feedbackNote: string
  pdfAvailable: boolean
  publishedAt: string
}

export interface QuotationDetailDto {
  quotation: QuotationSummaryDto
  version: QuotationVersionDto
  versions: QuotationVersionDto[]
  approvals: QuotationApprovalDto[]
}

export interface QuotationApprovalDto {
  id: string
  quotationId: string
  versionId: string
  attempt: number
  status: 'Pending' | 'Approved' | 'Rejected'
  submittedBy: string
  submittedAt: string
  decidedBy: string
  decidedAt: string
  comment: string
}

export interface QuotationApprovalDecisionInput {
  decision: 'Approved' | 'Rejected'
  comment: string
  expectedModified?: string
}

export interface QuotationDecisionInput {
  decision: 'Accepted' | 'Rejected'
  feedbackDate: string
  feedbackNote: string
  expectedModified?: string
}

export interface QuotationFollowUpInput { title: string; due: string; status: 'Open' | 'Done' | 'Cancelled'; note: string }
export interface QuotationFollowUp extends QuotationFollowUpInput { id: string; completedAt: string | null; completedVersion: string | null }
export interface QuotationPlanning { quotationId: string; modified: string; plannedSendDate: string | null; followUps: QuotationFollowUp[] }
