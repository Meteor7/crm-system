import { describe, expect, expectTypeOf, it } from 'vitest'
import {
  appendMultipartFile,
  type BinaryDownload,
  type MultipartFilePart,
} from './binary-transport'

describe('binary transport contract', () => {
  it('defines a direct browser download result', () => {
    expectTypeOf<BinaryDownload>().toEqualTypeOf<{
      blob: Blob
      fileName: string
      mimeType: string
    }>()
  })

  it('preserves multipart filename, MIME type, size, and bytes', async () => {
    const part: MultipartFilePart = {
      blob: new Blob(['abc'], { type: 'text/plain' }),
      fileName: 'a.txt',
      mimeType: 'text/plain',
      size: 3,
    }
    const formData = new FormData()

    appendMultipartFile(formData, 'file', part)

    const file = formData.get('file')
    expect(file).toBeInstanceOf(File)
    expect((file as File).name).toBe('a.txt')
    expect((file as File).type).toBe('text/plain')
    expect((file as File).size).toBe(3)
    expect(await (file as File).text()).toBe('abc')
  })
})
