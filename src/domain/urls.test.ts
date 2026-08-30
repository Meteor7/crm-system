import { describe, expect, it } from 'vitest'
import { safeExternalUrl } from './urls'

describe('safeExternalUrl', () => {
  it('allows HTTP reports and rejects executable or malformed links', () => {
    expect(safeExternalUrl('https://example.com/report.pdf')).toBe('https://example.com/report.pdf')
    expect(safeExternalUrl('http://127.0.0.1/report')).toBe('http://127.0.0.1/report')
    expect(safeExternalUrl('javascript:alert(1)')).toBe('')
    expect(safeExternalUrl('data:text/html,unsafe')).toBe('')
    expect(safeExternalUrl('/relative/report')).toBe('')
  })
})
