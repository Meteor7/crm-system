export interface ImagePdfPage {
  jpeg: Uint8Array
  width: number
  height: number
}

const encoder = new TextEncoder()

function ascii(value: string) {
  return encoder.encode(value)
}

function concatBytes(parts: readonly Uint8Array[]) {
  const result = new Uint8Array(parts.reduce((length, part) => length + part.length, 0))
  let offset = 0
  parts.forEach((part) => {
    result.set(part, offset)
    offset += part.length
  })
  return result
}

function objectBytes(number: number, body: string | Uint8Array) {
  return concatBytes([
    ascii(`${number} 0 obj\n`),
    typeof body === 'string' ? ascii(body) : body,
    ascii('\nendobj\n'),
  ])
}

function streamObject(number: number, dictionary: string, stream: Uint8Array) {
  return objectBytes(number, concatBytes([
    ascii(`<< ${dictionary} /Length ${stream.length} >>\nstream\n`),
    stream,
    ascii('\nendstream'),
  ]))
}

export function buildImagePdf(pages: readonly ImagePdfPage[]) {
  if (!pages.length) throw new Error('PDF requires at least one image page')

  const header = concatBytes([ascii('%PDF-1.4\n%'), new Uint8Array([0xe2, 0xe3, 0xcf, 0xd3]), ascii('\n')])
  const objects: Uint8Array[] = []
  const pageObjectNumbers = pages.map((_page, index) => 3 + index * 3)
  objects.push(objectBytes(1, '<< /Type /Catalog /Pages 2 0 R >>'))
  objects.push(objectBytes(2, `<< /Type /Pages /Count ${pages.length} /Kids [${pageObjectNumbers.map((number) => `${number} 0 R`).join(' ')}] >>`))

  pages.forEach((page, index) => {
    if (!Number.isFinite(page.width) || page.width <= 0 || !Number.isFinite(page.height) || page.height <= 0) {
      throw new Error('PDF image dimensions must be positive')
    }
    const pageNumber = pageObjectNumbers[index]
    const contentNumber = pageNumber + 1
    const imageNumber = pageNumber + 2
    const imageName = `Im${index + 1}`
    const content = ascii(`q 595 0 0 842 0 0 cm /${imageName} Do Q`)

    objects.push(objectBytes(pageNumber,
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /${imageName} ${imageNumber} 0 R >> >> /Contents ${contentNumber} 0 R >>`,
    ))
    objects.push(streamObject(contentNumber, '', content))
    objects.push(streamObject(imageNumber,
      `/Type /XObject /Subtype /Image /Width ${page.width} /Height ${page.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode`,
      page.jpeg,
    ))
  })

  const offsets: number[] = []
  let nextOffset = header.length
  objects.forEach((object) => {
    offsets.push(nextOffset)
    nextOffset += object.length
  })
  const xrefOffset = nextOffset
  const xref = ascii([
    'xref',
    `0 ${objects.length + 1}`,
    '0000000000 65535 f ',
    ...offsets.map((offset) => `${String(offset).padStart(10, '0')} 00000 n `),
    '',
  ].join('\n'))
  const trailer = ascii(`trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`)
  return concatBytes([header, ...objects, xref, trailer])
}
