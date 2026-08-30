import { describe, expect, it } from 'vitest'
import { validateCreateVisit } from './visits'

describe('visit workflow', () => {
  it('validates required fields for a new visit', () => {
    expect(() => validateCreateVisit({ accountId: '', subject: '', date: '', type: 'On-site', owner: '', objective: '' }))
      .toThrowError()
  })
})