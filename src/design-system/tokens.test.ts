import { describe, expect, it } from 'vitest'
import tokens from './tokens.css?raw'

describe('design tokens', () => {
  it('contains the approved brand palette under the app namespace', () => {
    expect(tokens).toContain('.semicrm-app')
    expect(tokens).toContain('--crm-accent: #3159CE')
    expect(tokens).toContain('--crm-link: #3159CE')
    expect(tokens).toContain('--crm-link-hover: #2448B0')
    expect(tokens).toContain('#20324C')
    expect(tokens).toContain('#F3F5FA')
    expect(tokens).toContain('#3B9B64')
    expect(tokens).toContain('#C58A18')
  })
})
