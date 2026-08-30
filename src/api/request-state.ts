import type { ApiResponse } from '@/types/crm'
import { CrmApiError } from './contracts'

export interface RequestMetaState {
  warnings: string[]
  message: string
  requestId: string
  staleAt: string
  stale: boolean
}

export interface RequestErrorState {
  message: string
  requestId: string
  denied: boolean
  retryable: boolean
}

export function readRequestMeta<T>(result: ApiResponse<T>, now = new Date()): RequestMetaState {
  const warnings = result.warnings ?? []
  const staleAt = result.meta?.staleAt ?? ''
  const expired = Boolean(staleAt) && new Date(staleAt).getTime() <= now.getTime()
  return {
    warnings,
    message: warnings[0] ?? (expired ? '当前数据快照已过期，请刷新后再用于经营判断。' : ''),
    requestId: result.meta?.requestId ?? '',
    staleAt,
    stale: warnings.length > 0 || expired,
  }
}

export function mapRequestError(error: unknown): RequestErrorState {
  if (error instanceof CrmApiError) {
    return {
      message: error.message,
      requestId: error.requestId,
      // denied 家族：角色级权限（PERMISSION_DENIED）与数据范围越权（SCOPE_DENIED）。
      // NOT_PERMITTED / '403' 为 Frappe HTTP 翻译预留；归一层应把它们映射到上述两者。
      denied: ['UNAUTHENTICATED', 'PERMISSION_DENIED', 'SCOPE_DENIED'].includes(error.code),
      retryable: error.retryable,
    }
  }
  return {
    message: error instanceof Error ? error.message : '数据请求失败，请稍后重试。',
    requestId: 'req_unknown',
    denied: false,
    retryable: true,
  }
}
