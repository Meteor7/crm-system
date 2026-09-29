import type { CrmApi } from '@/api'
import { EQUIPMENT_PRESETS } from '@/domain/equipment'

/** The equipment type options, or the presets when the list cannot be read. */
export async function loadEquipmentTypes(api: Pick<CrmApi, 'listEquipmentTypes'>): Promise<string[]> {
  try {
    return (await api.listEquipmentTypes()).data
  } catch {
    return [...EQUIPMENT_PRESETS]
  }
}
