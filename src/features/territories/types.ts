export interface TerritoryInput {
  name: string
  parent: string | null
  isGroup: boolean
  enabled: boolean
  sortOrder: number
}
export interface Territory extends TerritoryInput { modified: string }
export interface TerritoryAssignmentInput {
  territory: string
  salesOwner: string
  validFrom: string
  validUntil: string | null
  cancelled: boolean
  note: string
}
export interface TerritoryAssignment extends TerritoryAssignmentInput { id: string; modified: string }
export interface TerritoryCatalogue {
  territories: Territory[]
  assignments: TerritoryAssignment[]
  unmappedRegions: string[]
  sales: { id: string; name: string }[]
  today: string
}
