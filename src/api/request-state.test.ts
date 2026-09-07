import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { createFrappeApi } from './frappe-adapter'
import { setLocale, useLocaleMessage } from '@/i18n'
import { useDashboardStore } from '@/stores/dashboard'
import { useAppStore } from '@/stores/app'
import DataNotice from '@/design-system/DataNotice.vue'
import { describe, expect, it, vi } from 'vitest'
import { CrmApiError } from './contracts'
import { mapRequestError, readRequestMeta, requestErrorMessage } from './request-state'

describe('request state mapping', () => {
  it('marks expired or warned responses as partial/stale', () => {
    const state = readRequestMeta({
      data: [], warnings: ['上游只返回部分结果'],
      meta: { requestId: 'req_meta_1', staleAt: '2026-07-17T09:00:00+08:00' },
    }, new Date('2026-07-17T10:00:00+08:00'))

    expect(state.stale).toBe(true)
    expect(state.requestId).toBe('req_meta_1')
    expect(state.message).toContain('部分结果')
  })

  it('maps permission failures without losing the request ID', () => {
    const state = mapRequestError(new CrmApiError('PERMISSION_DENIED', '无权查看团队客户', 'req_denied_1', false))

    expect(state.denied).toBe(true)
    expect(state.requestId).toBe('req_denied_1')
    expect(state.retryable).toBe(false)
  })

  it('maps record-scope failures to the denied state', () => {
    const state = mapRequestError(new CrmApiError('SCOPE_DENIED', '无权访问该客户范围', 'req_scope_1', false))

    expect(state).toMatchObject({ denied: true, requestId: 'req_scope_1', retryable: false })
  })
})

describe('localized client failures', () => {
  it.each([
    [403, 'Your session does not have permission', '无权'],
    [409, 'changed by another user', '其他用户'],
    [422, 'failed validation', '校验'],
    [500, 'temporarily unavailable', '暂时不可用'],
    [200, 'unrecognized data format', '无法识别'],
  ])('keeps fallback HTTP %i copy reactive after a completed request', async (status, english, chinese) => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('{}', { status: Number(status) }))
    const api = createFrappeApi({ fetchImpl })
    const notice = useLocaleMessage()
    try { await api.getBootstrap() } catch (error) { notice.value = requestErrorMessage(error) }
    expect(notice.value).toContain(chinese)
    setLocale('en-US')
    expect(notice.value).toContain(english)
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })

  it('keeps same-worded backend messages and field validation opaque', async () => {
    const raw = '当前会话无权执行此操作。'
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: { error: { code: 'PERMISSION_DENIED', message: raw, fieldErrors: { name: '原始字段错误' } }, meta: { requestId: 'req_raw' } } }), { status: 403 }))
    const notice = useLocaleMessage()
    try { await createFrappeApi({ fetchImpl }).getBootstrap() } catch (error) {
      expect(error).toMatchObject({ requestId: 'req_raw', fieldErrors: { name: '原始字段错误' } })
      expect(mapRequestError(error).localizedMessage).toBeUndefined()
      notice.value = requestErrorMessage(error)
    }
    setLocale('en-US')
    expect(notice.value).toBe(raw)
  })

  it('updates cached bootstrap and dashboard network errors without retrying', async () => {
    setActivePinia(createPinia())
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    const api = createFrappeApi({ fetchImpl })
    const app = useAppStore()
    const dashboard = useDashboardStore()
    await app.loadBootstrap(api)
    await dashboard.load(api)
    expect(app.error).toContain('无法连接')
    expect(dashboard.error).toContain('无法连接')
    setLocale('en-US')
    expect(app.error).toContain('Unable to connect')
    expect(dashboard.error).toContain('Unable to connect')
    expect(fetchImpl).toHaveBeenCalledTimes(2)
  })

  it('switches an expired-snapshot notice while preserving backend warnings', async () => {
    const response = { data: [], warnings: [], meta: { requestId: 'req_stale', staleAt: '2020-01-01T00:00:00Z' } }
    const state = readRequestMeta(response)
    const wrapper = mount(DataNotice, { props: { message: state.localizedMessage ?? state.message, requestId: state.requestId } })
    expect(wrapper.text()).toContain('快照已过期')
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.text()).toContain('snapshot has expired')
    expect(wrapper.text()).toContain('req_stale')
    const raw = readRequestMeta({ ...response, warnings: ['当前数据快照已过期，请刷新后再用于经营判断。'] })
    expect(raw.localizedMessage).toBeUndefined()
    await wrapper.setProps({ message: raw.message })
    expect(wrapper.text()).toContain('当前数据快照已过期')
    wrapper.unmount()
  })
})
