export interface EventInput {
  title: string; owner: string; startDate: string; endDate: string; status: 'Planned' | 'Done' | 'Cancelled'
  accountId: string; opportunityId: string; region: string; market: string; equipment: string; note: string
}
export interface EventDto extends EventInput { id: string; modified: string; completedAt: string | null }
