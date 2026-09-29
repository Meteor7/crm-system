// Captured backend responses, used only by tests.
import sample from '../../../docs/opportunity-board/api-sample.json'
import type { ApiResponse } from '@/types/crm'
import type { BoardFilters, BoardResult, SavedBoardQuery } from './types'
const copy = <T>(value: unknown): T => JSON.parse(JSON.stringify(value))
export const boardFiltersFixture = () => copy<BoardFilters>(sample.samples[1].response.data)
export const boardResultFixture = () => copy<ApiResponse<BoardResult>>(sample.samples[2].response)
export const boardGroupedFixture = () => copy<ApiResponse<BoardResult>>(sample.samples[3].response)
export const savedQueryFixture = () => copy<SavedBoardQuery>(sample.samples[8].response.data)

