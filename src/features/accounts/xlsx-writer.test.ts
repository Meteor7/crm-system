import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { buildCustomerReportModel } from './customer-report-model'
import { buildXlsxFile, downloadCustomerReport } from './xlsx-writer'

const downloadMocks = vi.hoisted(() => ({ downloadBlob: vi.fn() }))
vi.mock('@/features/shared/download-blob', () => downloadMocks)

beforeEach(() => downloadMocks.downloadBlob.mockReset())

function readStoredZip(bytes: Uint8Array) {
  const decoder = new TextDecoder()
  const files = new Map<string, Uint8Array>()
  let offset = 0
  while (offset + 30 <= bytes.length) {
    const view = new DataView(bytes.buffer, bytes.byteOffset + offset)
    if (view.getUint32(0, true) !== 0x04034b50) break
    const size = view.getUint32(18, true)
    const nameLength = view.getUint16(26, true)
    const extraLength = view.getUint16(28, true)
    const nameStart = offset + 30
    const dataStart = nameStart + nameLength + extraLength
    const name = decoder.decode(bytes.slice(nameStart, nameStart + nameLength))
    files.set(name, bytes.slice(dataStart, dataStart + size))
    offset = dataStart + size
  }
  return files
}

function readCentralDirectory(bytes: Uint8Array) {
  const decoder = new TextDecoder()
  let endOffset = bytes.length - 22
  while (endOffset >= 0 && new DataView(bytes.buffer, bytes.byteOffset + endOffset).getUint32(0, true) !== 0x06054b50) endOffset -= 1
  if (endOffset < 0) throw new Error('ZIP end-of-central-directory record is missing')
  const end = new DataView(bytes.buffer, bytes.byteOffset + endOffset)
  const entryCount = end.getUint16(10, true)
  let offset = end.getUint32(16, true)
  const entries: Array<{ name: string; localOffset: number }> = []
  for (let index = 0; index < entryCount; index += 1) {
    const view = new DataView(bytes.buffer, bytes.byteOffset + offset)
    if (view.getUint32(0, true) !== 0x02014b50) throw new Error('Invalid ZIP central-directory entry')
    const nameLength = view.getUint16(28, true)
    const extraLength = view.getUint16(30, true)
    const commentLength = view.getUint16(32, true)
    const name = decoder.decode(bytes.slice(offset + 46, offset + 46 + nameLength))
    entries.push({ name, localOffset: view.getUint32(42, true) })
    offset += 46 + nameLength + extraLength + commentLength
  }
  return entries
}

describe('xlsx writer', () => {
  it('uses the shared mounted-link download lifecycle', async () => {
    const detail = (await createMockApi({ latency: 0 }).getAccount360('ACC-001')).data
    const report = buildCustomerReportModel(detail, '2026-07-17')

    downloadCustomerReport(report)

    expect(downloadMocks.downloadBlob).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
      report.fileName,
    )
  })

  it('creates an OpenXML ZIP containing the five named worksheets', async () => {
    const detail = (await createMockApi({ latency: 0 }).getAccount360('ACC-001')).data
    const bytes = buildXlsxFile(buildCustomerReportModel(detail, '2026-07-17'))
    const files = readStoredZip(bytes)
    const centralEntries = readCentralDirectory(bytes)
    const decoder = new TextDecoder()
    const workbook = decoder.decode(files.get('xl/workbook.xml'))
    const relationships = decoder.decode(files.get('xl/_rels/workbook.xml.rels'))
    const overview = decoder.decode(files.get('xl/worksheets/sheet1.xml'))
    const styles = decoder.decode(files.get('xl/styles.xml'))

    expect([...bytes.slice(0, 4)]).toEqual([0x50, 0x4b, 0x03, 0x04])
    expect([...files.keys()]).toEqual([
      '[Content_Types].xml', '_rels/.rels', 'xl/workbook.xml', 'xl/_rels/workbook.xml.rels', 'xl/styles.xml',
      'xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml', 'xl/worksheets/sheet3.xml', 'xl/worksheets/sheet4.xml', 'xl/worksheets/sheet5.xml',
    ])
    expect(centralEntries.map((entry) => entry.name)).toEqual([...files.keys()])
    centralEntries.forEach((entry) => expect(new DataView(bytes.buffer, bytes.byteOffset + entry.localOffset).getUint32(0, true)).toBe(0x04034b50))
    files.forEach((contents, name) => {
      if (!name.endsWith('.xml') && !name.endsWith('.rels')) return
      const parsed = new DOMParser().parseFromString(decoder.decode(contents), 'application/xml')
      expect(parsed.querySelector('parsererror'), `${name} must be valid XML`).toBeNull()
    })
    expect(new DOMParser().parseFromString(relationships, 'application/xml').getElementsByTagName('Relationship')).toHaveLength(6)
    expect(workbook).toContain('客户全貌 Overview')
    expect(workbook).toContain('Demo与合同 Demo')
    expect(styles).toContain('formatCode="¥#,##0"')
    expect(overview).toContain('<pane ySplit="3"')
    expect(overview).toContain('<mergeCell ref="A1:H2"/>')
    expect(overview).toMatch(/<c r="[A-Z]+\d+" s="12"><v>\d+<\/v><\/c>/)
  })
})
