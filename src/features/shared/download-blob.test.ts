import { afterEach, describe, expect, it, vi } from 'vitest'
import { downloadBlob } from './download-blob'

describe('downloadBlob', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('downloads from a mounted link and delays revoking the object URL', () => {
    vi.useFakeTimers()
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:artifact')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      expect(document.body.contains(this)).toBe(true)
    })
    const blob = new Blob(['artifact'])

    downloadBlob(blob, 'artifact.pdf')

    expect(createObjectURL).toHaveBeenCalledWith(blob)
    expect(click).toHaveBeenCalledTimes(1)
    expect(document.querySelector('a[download="artifact.pdf"]')).not.toBeNull()
    expect(revokeObjectURL).not.toHaveBeenCalled()

    vi.advanceTimersByTime(30_000)
    expect(document.querySelector('a[download="artifact.pdf"]')).toBeNull()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:artifact')
    expect(click.mock.invocationCallOrder[0]).toBeLessThan(revokeObjectURL.mock.invocationCallOrder[0])
  })

  it('revokes the object URL when the browser click throws', () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:artifact')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {
      throw new Error('click blocked')
    })

    expect(() => downloadBlob(new Blob(['artifact']), 'artifact.pdf')).toThrow('click blocked')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:artifact')
  })
})
