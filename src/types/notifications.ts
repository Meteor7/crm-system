export type NotificationCategory =
  | 'Account'
  | 'Contact'
  | 'Requirement'
  | 'Lead'
  | 'Opportunity'
  | 'Action'
  | 'Visit'
  | 'Booking'
  | 'Demo'
  | 'Evaluation'
  | 'InstalledTool'
  | 'Quotation'
  | 'RFQ'
  | 'Document'

export interface NotificationInput {
  generatedLocally?: boolean
  category: NotificationCategory
  title: string
  message: string
  route: string
  recipientId?: string
  recipient?: string
}

export interface AppNotification extends NotificationInput {
  id: string
  createdAt: string
  read: boolean
}

export interface NotificationDto {
  id: string
  category: NotificationCategory
  title: string
  message: string
  route: string
  recipientId: string
  actorId: string
  createdAt: string
  readAt?: string
  read: boolean
}

export interface NotificationListQuery {
  page?: number
  pageSize?: number
  unreadOnly?: boolean
}
