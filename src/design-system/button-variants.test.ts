import { afterEach, describe, expect, it } from 'vitest'
import buttonStyles from './base.css?raw'

describe('button variants', () => {
  afterEach(() => { document.body.innerHTML = ''; document.head.innerHTML = '' })

  it('renders destructive actions with the same control geometry as other action buttons', () => {
    const style = document.createElement('style')
    style.textContent = buttonStyles
    document.head.appendChild(style)
    document.body.innerHTML = '<main class="semicrm-app"><button class="danger-button">Discard</button></main>'

    const computed = getComputedStyle(document.querySelector('button')!)
    expect(computed.display).toBe('inline-flex')
    expect(computed.minHeight).toBe('36px')
    expect(computed.borderRadius).toBe('9px')
    expect(computed.color).not.toBe('buttontext')
  })
})

describe('link default', () => {
  // jsdom does not evaluate :where(), so the rule is checked as written; a browser applies it to every link
  // that no page rule or class colours (#222).
  it('colours a link without a style of its own as a CRM link, below every page and class rule', () => {
    expect(buttonStyles).toMatch(/:where\(\.semicrm-app\) a \{\s*color: var\(--crm-link\);\s*\}/)
    expect(buttonStyles).toMatch(/:where\(\.semicrm-app\) a:where\(:hover, :focus-visible\) \{\s*color: var\(--crm-link-hover\);\s*\}/)
    // No :visited rule of its own: the colour above is the author's, so the browser's purple never applies.
    expect(buttonStyles).not.toMatch(/a:visited/)
  })
})
