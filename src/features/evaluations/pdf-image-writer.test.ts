import { describe, expect, it } from 'vitest'
import { buildImagePdf } from './pdf-image-writer'

const jpegWithBinaryBytes = new Uint8Array([
  0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46,
  0x49, 0x46, 0x00, 0x01, 0x80, 0xfe, 0x00, 0xff,
  0xd9,
])

function containsBytes(haystack: Uint8Array, needle: Uint8Array) {
  return haystack.some((_byte, start) =>
    start + needle.length <= haystack.length
    && needle.every((byte, index) => haystack[start + index] === byte),
  )
}

describe('buildImagePdf', () => {
  it('writes one A4 PDF page per JPEG without converting binary image bytes to text', () => {
    const bytes = buildImagePdf([
      { jpeg: jpegWithBinaryBytes, width: 1240, height: 1754 },
      { jpeg: jpegWithBinaryBytes, width: 1240, height: 1754 },
    ])
    const text = new TextDecoder('latin1').decode(bytes)

    expect(text.startsWith('%PDF-1.4\n')).toBe(true)
    expect((text.match(/\/Type \/Page\b/g) || [])).toHaveLength(2)
    expect((text.match(/\/MediaBox \[0 0 595 842\]/g) || [])).toHaveLength(2)
    expect(text).toContain('startxref')
    expect(text.endsWith('%%EOF\n')).toBe(true)
    expect(containsBytes(bytes, jpegWithBinaryBytes)).toBe(true)
  })

  it('calculates every xref entry from final binary byte offsets', () => {
    const bytes = buildImagePdf([
      { jpeg: jpegWithBinaryBytes, width: 1240, height: 1754 },
      { jpeg: new Uint8Array([...jpegWithBinaryBytes, 0x00, 0x81]), width: 620, height: 877 },
    ])
    const text = new TextDecoder('latin1').decode(bytes)
    const startXref = Number(text.match(/startxref\n(\d+)\n%%EOF\n$/)?.[1])

    expect(text.slice(startXref, startXref + 4)).toBe('xref')
    const xrefLines = text.slice(startXref).split('\n')
    const [, objectCountText] = xrefLines[1].split(' ')
    const objectCount = Number(objectCountText)
    expect(objectCount).toBe(9)

    xrefLines.slice(3, 3 + objectCount - 1).forEach((line, index) => {
      const offset = Number(line.slice(0, 10))
      expect(text.slice(offset, offset + `${index + 1} 0 obj`.length)).toBe(`${index + 1} 0 obj`)
    })
  })
})
