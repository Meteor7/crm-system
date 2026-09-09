import { describe, expect, it } from 'vitest'
import { contactStatusLabel, meetingRecordParseLabel, salesEnumLabel, salesUnits } from './sales-i18n'

describe('sales display enum boundaries', () => {
  it('localizes known values while preserving unknown backend values', () => {
    expect(salesEnumLabel('Confirmed', 'zh-CN')).toBe('已确认')
    expect(salesEnumLabel('Confirmed', 'en-US')).toBe('Confirmed')
    expect(salesEnumLabel('Best Case', 'zh-CN')).toBe('最佳情况')
    expect(salesEnumLabel('new-backend-status', 'zh-CN')).toBe('new-backend-status')
  })

  it('keeps quantity units tied to the active locale', () => {
    expect(salesUnits('zh-CN')).toBe('台 / 项')
    expect(salesUnits('en-US')).toBe('units / items')
  })

  it('keeps installed-tool and contract Active separate from contact Active', () => {
    expect(salesEnumLabel('Active', 'zh-CN')).toBe('启用')
    expect(contactStatusLabel('Active', 'zh-CN')).toBe('在职')
    expect(salesEnumLabel('Active', 'en-US')).toBe('Active')
    expect(contactStatusLabel('Active', 'en-US')).toBe('Active')
  })

  it('scopes Failed to meeting-record parsing', () => {
    expect(salesEnumLabel('Failed', 'zh-CN')).toBe('Failed')
    expect(meetingRecordParseLabel('Failed', 'zh-CN')).toBe('解析失败')
    expect(meetingRecordParseLabel('Failed', 'en-US')).toBe('Parsing failed')
  })
})
