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