import { describe, expect, it } from 'vitest'
import { usesFrappeRuntime } from './runtime-mode'

describe('usesFrappeRuntime', () => {
  it.each([
    ['frappe', true],
    ['development', true],
    ['production', true],
    ['test', false],
  ])('maps %s mode to %s', (mode, expected) => {
    expect(usesFrappeRuntime(mode)).toBe(expected)
  })
})
