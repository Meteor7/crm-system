import { CrmApiError } from '@/api/contracts'
import type { UserId } from '@/types/crm'
import { isPersonnelId } from './personnel'

export interface LegacyInternalUserMapping {
  legacyValue: string
  userId: UserId
}

export const LEGACY_INTERNAL_USER_MAPPINGS: readonly LegacyInternalUserMapping[] = [
  { legacyValue: '演示员工24', userId: 'person029@crm.example.invalid' },
  { legacyValue: 'Demo Staff 04', userId: 'person029@crm.example.invalid' },
  { legacyValue: 'Boss', userId: 'person029@crm.example.invalid' },
  { legacyValue: 'Demo Staff 03', userId: 'person029@crm.example.invalid' },
  { legacyValue: '演示经理01', userId: 'person073@crm.example.invalid' },
  { legacyValue: 'Demo Staff 09', userId: 'person073@crm.example.invalid' },
  { legacyValue: 'Demo Staff 06', userId: 'person015@crm.example.invalid' },
  { legacyValue: 'Demo Staff 01', userId: 'person002@crm.example.invalid' },
  { legacyValue: 'Demo Staff 02', userId: 'person005@crm.example.invalid' },
  { legacyValue: 'Demo Staff 08', userId: 'person034@crm.example.invalid' },
  { legacyValue: 'Demo Staff 07', userId: 'person025@crm.example.invalid' },
  { legacyValue: 'Demo Staff 05', userId: 'person012@crm.example.invalid' },
  { legacyValue: '演示员工14', userId: 'person077@crm.example.invalid' },
  { legacyValue: '演示员工15', userId: 'person053@crm.example.invalid' },
  { legacyValue: '演示员工23', userId: 'person028@crm.example.invalid' },
] as const

const legacyUserIds = new Map(LEGACY_INTERNAL_USER_MAPPINGS.map((row) => [row.legacyValue, row.userId]))

export function migrateLegacyUserId(value: string, field: string): UserId {
  if (isPersonnelId(value)) return value
  const userId = legacyUserIds.get(value)
  if (userId) return userId
  throw new CrmApiError(
    'INVALID_OWNER',
    `Unmapped legacy internal identity in ${field}`,
    'req_identity_migration',
    false,
    { [field]: 'Map this value to a valid Frappe User before migration' },
  )
}

export function migrateOptionalLegacyUserId(value: string | undefined, field: string): UserId | undefined {
  return value ? migrateLegacyUserId(value, field) : value
}
