import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { demoRequests } from '@/api/mock-data'
import { createEmptyDemoRequestFormData } from '@/domain/demo-request-form'
import type { DemoRequestDto } from '@/types/crm'
import {
  buildDemoRequestDocx,
  buildDemoRequestDocxArtifact,
  demoRequestFileName,
  extractDemoRequestLogo,
} from './demo-request-docx'

function readStoredFiles(bytes: Uint8Array) {
  const files = new Map<string, Uint8Array>()
  const decoder = new TextDecoder()
  let offset = 0
  while (offset + 30 <= bytes.length) {
    const view = new DataView(bytes.buffer, bytes.byteOffset + offset)
    if (view.getUint32(0, true) !== 0x04034b50) break
    const method = view.getUint16(8, true)
    if (method !== 0) throw new Error('Expected stored ZIP entry')
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

function findBytes(haystack: Uint8Array, needle: Uint8Array) {
  for (let offset = 0; offset <= haystack.length - needle.length; offset += 1) {
    if (needle.every((byte, index) => haystack[offset + index] === byte)) return offset
  }
  return -1
}

function requestWithTwentySixWafers(): DemoRequestDto {
  const formData = createEmptyDemoRequestFormData('person002@crm.example.invalid')
  Object.assign(formData, {
    contactPerson: 'Ada Liu, Process Director, ada@example.com, +86 21 5555 0101',
    industry: 'Frontend Fab',
    demoOwner: 'FAE Robin',
    sizeShape: '300 mm, 775 μm, notch up',
    material: 'Si(100)',
    specificRequest: 'Edge exclusion 3 mm',
    detectMeasure: 'Particle defects from 2 μm',
    expectedResults: 'Wafer map, images and KLARF',
    otherTools: 'Customer tool of record',
    primaryTool: 'Macro Inspection X9',
    complementaryTool: 'Review Station R2',
    timing: '2026-08-20',
    keySuccessFactors: 'Capture at least 96%',
    internalQuestions: 'Confirm recipe owner',
    customerQuestions: 'Confirm defect library',
  })
  formData.wafers = Array.from({ length: 26 }, (_, index) => ({
    slotId: String(index + 1),
    wid: `WAFER-${String(index + 1).padStart(3, '0')}`,
    waferSpecificity: '300 mm Si(100)',
    notchFlat: 'Notch up',
    doiMetrologyItems: `Particle DOI ${index + 1}`,
    resultFileProvided: 'KLARF and PDF',
  }))
  return {
    ...demoRequests[0],
    id: 'DR/026',
    accountName: 'Example Semiconductor Co.',
    formData,
    preparedBy: 'Demo Staff 01',
    preparedDate: '2026-07-22',
    approvedBy: 'Demo Staff 03',
    approvedDate: '2026-07-23',
  }
}

describe('Demo Request DOCX', () => {
  const template = new Uint8Array(readFileSync(resolve('public/templates/demo-request-form-v2.docx')))

  it('preserves the source package and fills every table including 26 wafer rows', () => {
    const request = { ...requestWithTwentySixWafers(), customerExpectedDate: '2099-12-31' }
    const output = buildDemoRequestDocx(request, template)
    const files = readStoredFiles(output)
    const decoder = new TextDecoder()
    const documentXml = decoder.decode(files.get('word/document.xml'))
    const textEntries = [...files].filter(([name]) => /\.(xml|rels|txt)$/i.test(name))

    expect([...output.slice(0, 4)]).toEqual([0x50, 0x4b, 0x03, 0x04])
    expect(files.has('word/document.xml')).toBe(true)
    expect(files.has('word/header1.xml')).toBe(true)
    expect(files.has('word/footer1.xml')).toBe(true)
    expect(files.has('word/media/image1.png')).toBe(true)
    expect(documentXml).toContain('Example Semiconductor Co.')
    expect(documentXml).toContain('Ada Liu, Process Director, ada@example.com, +86 21 5555 0101')
    expect(documentXml).toContain('WAFER-001')
    expect(documentXml).toContain('WAFER-026')
    expect(documentXml).toContain('Demo Staff 03')
    expect(textEntries).not.toHaveLength(0)
    textEntries.forEach(([name, bytes]) => expect(decoder.decode(bytes), name).not.toContain(request.customerExpectedDate))
    expect(documentXml).not.toContain('Name, title, email, phone')
    expect(new DOMParser().parseFromString(documentXml, 'application/xml').querySelector('parsererror')).toBeNull()
  })

  it('rejects compressed and malformed templates with explicit errors', () => {
    const compressed = template.slice()
    new DataView(compressed.buffer, compressed.byteOffset).setUint16(8, 8, true)
    expect(() => buildDemoRequestDocx(requestWithTwentySixWafers(), compressed)).toThrow(/未压缩|compression/i)
    expect(() => buildDemoRequestDocx(requestWithTwentySixWafers(), new Uint8Array([1, 2, 3]))).toThrow(/Word|ZIP/i)
  })

  it('sanitizes Windows-invalid filename characters', () => {
    const request = { ...requestWithTwentySixWafers(), accountName: 'A/B:C*D?E"F<G>H|I' }
    const name = demoRequestFileName(request)
    expect(name).toMatch(/^Demo_Request_DR-026_A-B-C-D-E-F-G-H-I_\d{4}-\d{2}-\d{2}\.docx$/)
    expect(name).not.toMatch(/[\\/:*?"<>|]/)
  })

  it('extracts the approved company Logo from the Word template', () => {
    const files = readStoredFiles(template)

    expect(extractDemoRequestLogo(template)).toEqual(files.get('word/media/image1.png'))
  })

  it('reports the exact UTF-8 error when the Word template has no company Logo', () => {
    const withoutLogo = template.slice()
    const logoName = new TextEncoder().encode('word/media/image1.png')
    const logoOffset = findBytes(withoutLogo, logoName)
    expect(logoOffset).toBeGreaterThanOrEqual(0)
    withoutLogo[logoOffset + logoName.length - 1] = 'x'.charCodeAt(0)

    expect(() => extractDemoRequestLogo(withoutLogo)).toThrow('Word 模板缺少公司 Logo')
  })

  it('builds a named DOCX artifact payload without starting a browser download', async () => {
    const request = requestWithTwentySixWafers()

    const artifact = buildDemoRequestDocxArtifact(request, template)

    expect(artifact.fileName).toBe(demoRequestFileName(request))
    expect(artifact.blob.type).toBe('application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    expect(new Uint8Array(await artifact.blob.arrayBuffer()).slice(0, 4)).toEqual(new Uint8Array([0x50, 0x4b, 0x03, 0x04]))
  })
})
