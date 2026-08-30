import { describe, expect, it } from 'vitest'
import tokens from './tokens.css?raw'

describe('design tokens', () => {
  it('contains the approved brand palette under the app namespace', () => {
    expect(tokens).toContain('.semicrm-app')
    expect(tokens).toContain('--crm-logo-orange: rgb(255, 142, 1)')
    expect(tokens).toContain('--crm-link: rgb(198, 91, 8)')
    expect(tokens).toContain('--crm-link-hover: rgb(163, 69, 0)')
    expect(tokens).toContain('#24272D')
    expect(tokens).toContain('#F6F4F0')
    expect(tokens).toContain('#3B9B64')
    expect(tokens).toContain('#C58A18')
  })
})
