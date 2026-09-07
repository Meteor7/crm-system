import type { ApiResponse } from '@/types/crm'
import { CrmApiError } from './contracts'
import { generatedErrorMessage } from './generated-error-messages'
import { localeMessage, resolveLocaleMessage, type LocaleMessage } from '@/i18n'

// Client-generated errors carry their copy pair; recognized service messages are handled below.
export class ClientRequestError extends CrmApiError {
  constructor(code: string, public readonly localizedMessage: LocaleMessage, requestId: string, retryable = false, fieldErrors: Record<string, string> = {}) {
    super(code, resolveLocaleMessage(localizedMessage), requestId, retryable, fieldErrors)
  }
}

export function requestErrorMessage(error: unknown, fallback: LocaleMessage = localeMessage('Data request failed. Please try again later.', '数据请求失败，请稍后重试。')): LocaleMessage {
  if (error instanceof ClientRequestError) return error.localizedMessage
  if (error instanceof CrmApiError) return generatedErrorMessage(error.code, error.message) ?? error.message
  return error instanceof Error ? error.message : fallback
}

export interface RequestMetaState {
  warnings: string[]
  message: string
  localizedMessage?: LocaleMessage
  requestId: string
  staleAt: string
  stale: boolean
}

export interface RequestErrorState {
  message: string
  localizedMessage?: LocaleMessage
  requestId: string
  denied: boolean
  retryable: boolean
}

export function readRequestMeta<T>(result: ApiResponse<T>, now = new Date()): RequestMetaState {
  const warnings = result.warnings ?? []
  const staleAt = result.meta?.staleAt ?? ''
  const expired = Boolean(staleAt) && new Date(staleAt).getTime() <= now.getTime()
  const localizedMessage = warnings[0] === undefined && expired ? localeMessage('This data snapshot has expired. Refresh it before making business decisions.', '当前数据快照已过期，请刷新后再用于经营判断。') : undefined
  return {
    warnings,
    message: warnings[0] ?? (localizedMessage ? resolveLocaleMessage(localizedMessage) : ''),
    localizedMessage,
    requestId: result.meta?.requestId ?? '',
    staleAt,
    stale: warnings.length > 0 || expired,
  }
}

export function mapRequestError(error: unknown): RequestErrorState {
  if (error instanceof CrmApiError) {
    return {
      message: error.message,
      localizedMessage: error instanceof ClientRequestError ? error.localizedMessage : generatedErrorMessage(error.code, error.message),
      requestId: error.requestId,
      // denied 家族：角色级权限（PERMISSION_DENIED）与数据范围越权（SCOPE_DENIED）。
      // NOT_PERMITTED / '403' 为 Frappe HTTP 翻译预留；归一层应把它们映射到上述两者。
      denied: ['UNAUTHENTICATED', 'PERMISSION_DENIED', 'SCOPE_DENIED'].includes(error.code),
      retryable: error.retryable,
    }
  }
  return {
    message: resolveLocaleMessage(requestErrorMessage(error)),
    localizedMessage: error instanceof Error ? undefined : requestErrorMessage(error),
    requestId: 'req_unknown',
    denied: false,
    retryable: true,
  }
}
