import type { DemoRequestDto, DemoWaferDetailDto } from '@/types/crm'
import { countDemoWafers, getDemoRequestFormData } from '@/domain/demo-request-form'
import { downloadBlob } from '@/features/shared/download-blob'

const WORD_NAMESPACE = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
const XML_NAMESPACE = 'http://www.w3.org/XML/1998/namespace'
const TEMPLATE_PATH = 'templates/demo-request-form-v2.docx'
const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

const MAIN_CELLS = {
  companyName: [0, 1, 1], contactPerson: [0, 2, 1], industry: [0, 3, 1],
  salesContact: [0, 6, 1], demoOwner: [0, 7, 1], waferCount: [0, 10, 1],
  sizeShape: [0, 11, 1], material: [0, 12, 1], specificRequest: [0, 13, 1],
  detectMeasure: [0, 16, 1], expectedResults: [0, 17, 1], otherTools: [0, 18, 1],
  primaryTool: [0, 21, 1], complementaryTool: [0, 22, 1], timing: [0, 23, 1],
  keySuccessFactors: [0, 26, 1], internalQuestions: [0, 29, 1], customerQuestions: [0, 30, 1],
} as const

interface StoredZipEntry { name: string; data: Uint8Array }

function asBytes(input: Uint8Array | ArrayBuffer) {
  return input instanceof Uint8Array ? input : new Uint8Array(input)
}

function readStoredZip(input: Uint8Array | ArrayBuffer) {
  const bytes = asBytes(input)
  const entries: StoredZipEntry[] = []
  const decoder = new TextDecoder()
  let offset = 0
  while (offset + 4 <= bytes.length) {
    const signature = new DataView(bytes.buffer, bytes.byteOffset + offset, Math.min(bytes.length - offset, 30)).getUint32(0, true)
    if (signature === 0x02014b50 || signature === 0x06054b50) break
    if (signature !== 0x04034b50 || offset + 30 > bytes.length) throw new Error('Word 模板不是有效的 ZIP 文件')
    const header = new DataView(bytes.buffer, bytes.byteOffset + offset, 30)
    const flags = header.getUint16(6, true)
    const method = header.getUint16(8, true)
    const compressedSize = header.getUint32(18, true)
    const uncompressedSize = header.getUint32(22, true)
    const nameLength = header.getUint16(26, true)
    const extraLength = header.getUint16(28, true)
    if (flags & 0x08) throw new Error('Word 模板 ZIP 不支持数据描述符')
    if (method !== 0 || compressedSize !== uncompressedSize) throw new Error('Word 模板必须使用未压缩 ZIP Store 格式')
    const nameStart = offset + 30
    const dataStart = nameStart + nameLength + extraLength
    const dataEnd = dataStart + compressedSize
    if (dataEnd > bytes.length) throw new Error('Word 模板 ZIP 条目不完整')
    entries.push({ name: decoder.decode(bytes.slice(nameStart, nameStart + nameLength)), data: bytes.slice(dataStart, dataEnd) })
    offset = dataEnd
  }
  if (!entries.length) throw new Error('Word 模板不是有效的 ZIP 文件')
  return entries
}

export function extractDemoRequestLogo(templateBytes: Uint8Array | ArrayBuffer) {
  const entry = readStoredZip(templateBytes).find((item) => item.name === 'word/media/image1.png')
  if (!entry) throw new Error('Word 模板缺少公司 Logo')
  return entry.data
}

let crcTable: number[] | null = null
function crc32(bytes: Uint8Array) {
  if (!crcTable) crcTable = Array.from({ length: 256 }, (_, number) => {
    let value = number
    for (let index = 0; index < 8; index += 1) value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1
    return value >>> 0
  })
  let crc = 0xffffffff
  for (const byte of bytes) crc = crcTable[(crc ^ byte) & 255] ^ (crc >>> 8)
  return (crc ^ 0xffffffff) >>> 0
}

function concatBytes(parts: Uint8Array[]) {
  const output = new Uint8Array(parts.reduce((total, part) => total + part.length, 0))
  let offset = 0
  parts.forEach((part) => { output.set(part, offset); offset += part.length })
  return output
}

function writeStoredZip(entries: StoredZipEntry[]) {
  const encoder = new TextEncoder()
  const localParts: Uint8Array[] = []
  const centralParts: Uint8Array[] = []
  const dosTime = (12 << 11) | (30 << 5)
  const dosDate = ((2026 - 1980) << 9) | (7 << 5) | 22
  let offset = 0
  entries.forEach((entry) => {
    const name = encoder.encode(entry.name)
    const crc = crc32(entry.data)
    const local = new Uint8Array(30)
    const localView = new DataView(local.buffer)
    localView.setUint32(0, 0x04034b50, true)
    localView.setUint16(4, 20, true)
    localView.setUint16(10, dosTime, true)
    localView.setUint16(12, dosDate, true)
    localView.setUint32(14, crc, true)
    localView.setUint32(18, entry.data.length, true)
    localView.setUint32(22, entry.data.length, true)
    localView.setUint16(26, name.length, true)
    localParts.push(local, name, entry.data)

    const central = new Uint8Array(46)
    const centralView = new DataView(central.buffer)
    centralView.setUint32(0, 0x02014b50, true)
    centralView.setUint16(4, 20, true)
    centralView.setUint16(6, 20, true)
    centralView.setUint16(12, dosTime, true)
    centralView.setUint16(14, dosDate, true)
    centralView.setUint32(16, crc, true)
    centralView.setUint32(20, entry.data.length, true)
    centralView.setUint32(24, entry.data.length, true)
    centralView.setUint16(28, name.length, true)
    centralView.setUint32(42, offset, true)
    centralParts.push(central, name)
    offset += local.length + name.length + entry.data.length
  })
  const centralBytes = concatBytes(centralParts)
  const end = new Uint8Array(22)
  const endView = new DataView(end.buffer)
  endView.setUint32(0, 0x06054b50, true)
  endView.setUint16(8, entries.length, true)
  endView.setUint16(10, entries.length, true)
  endView.setUint32(12, centralBytes.length, true)
  endView.setUint32(16, offset, true)
  return concatBytes([...localParts, centralBytes, end])
}

function directChildren(parent: Element, localName: string) {
  return Array.from(parent.childNodes).filter((node): node is Element => node.nodeType === 1 && (node as Element).localName === localName)
}

function tableCell(tables: Element[], tableIndex: number, rowIndex: number, cellIndex: number) {
  const table = tables[tableIndex]
  const row = table && directChildren(table, 'tr')[rowIndex]
  const cell = row && directChildren(row, 'tc')[cellIndex]
  if (!cell) throw new Error(`Word 模板缺少表格单元格 ${tableIndex}/${rowIndex}/${cellIndex}`)
  return cell
}

function setCellText(documentXml: XMLDocument, cell: Element, value: string) {
  const paragraph = cell.getElementsByTagNameNS('*', 'p')[0]
  const run = paragraph?.getElementsByTagNameNS('*', 'r')[0]
  const paragraphProperties = paragraph?.getElementsByTagNameNS('*', 'pPr')[0]?.cloneNode(true)
  const runProperties = run?.getElementsByTagNameNS('*', 'rPr')[0]?.cloneNode(true)
  directChildren(cell, 'p').forEach((item) => item.remove())
  const nextParagraph = documentXml.createElementNS(WORD_NAMESPACE, 'w:p')
  if (paragraphProperties) nextParagraph.appendChild(paragraphProperties)
  const nextRun = documentXml.createElementNS(WORD_NAMESPACE, 'w:r')
  if (runProperties) nextRun.appendChild(runProperties)
  String(value ?? '').split(/\r?\n/).forEach((line, index) => {
    if (index) nextRun.appendChild(documentXml.createElementNS(WORD_NAMESPACE, 'w:br'))
    const text = documentXml.createElementNS(WORD_NAMESPACE, 'w:t')
    text.setAttributeNS(XML_NAMESPACE, 'xml:space', 'preserve')
    text.textContent = line
    nextRun.appendChild(text)
  })
  nextParagraph.appendChild(nextRun)
  cell.appendChild(nextParagraph)
}

function fillWaferRow(documentXml: XMLDocument, row: Element, wafer?: DemoWaferDetailDto) {
  const cells = directChildren(row, 'tc')
  const values = wafer ? [wafer.slotId, wafer.wid, wafer.waferSpecificity, wafer.notchFlat, wafer.doiMetrologyItems, wafer.resultFileProvided] : ['', '', '', '', '', '']
  if (cells.length < values.length) throw new Error('Word 模板 Wafer Details 列数量不正确')
  values.forEach((value, index) => setCellText(documentXml, cells[index], value))
}

function populateDocumentXml(request: DemoRequestDto, xml: string) {
  if (!request.formData) throw new Error('Demo Request 缺少已保存的完整表单，无法生成 Word 文件')
  const documentXml = new DOMParser().parseFromString(xml, 'application/xml')
  if (documentXml.querySelector('parsererror')) throw new Error('Word 模板 document.xml 格式错误')
  const tables = Array.from(documentXml.getElementsByTagNameNS('*', 'tbl'))
  if (tables.length < 3) throw new Error('Word 模板缺少 Demo Request 表格')
  const form = getDemoRequestFormData(request)
  const values: Record<keyof typeof MAIN_CELLS, string> = {
    companyName: request.accountName,
    contactPerson: form.contactPerson,
    industry: form.industry,
    salesContact: form.salesContact,
    demoOwner: form.demoOwner,
    waferCount: String(countDemoWafers(form)),
    sizeShape: form.sizeShape,
    material: form.material,
    specificRequest: form.specificRequest,
    detectMeasure: form.detectMeasure,
    expectedResults: form.expectedResults,
    otherTools: form.otherTools,
    primaryTool: form.primaryTool,
    complementaryTool: form.complementaryTool,
    timing: form.timing,
    keySuccessFactors: form.keySuccessFactors,
    internalQuestions: form.internalQuestions,
    customerQuestions: form.customerQuestions,
  }
  Object.entries(MAIN_CELLS).forEach(([key, location]) => {
    setCellText(documentXml, tableCell(tables, location[0], location[1], location[2]), values[key as keyof typeof MAIN_CELLS])
  })
  setCellText(documentXml, tableCell(tables, 1, 0, 0), `Prepared by:  ${request.preparedBy || request.createdBy || ''}`)
  setCellText(documentXml, tableCell(tables, 1, 0, 1), `Date:  ${request.preparedDate || request.createdAt.slice(0, 10)}`)
  setCellText(documentXml, tableCell(tables, 1, 1, 0), `Approved by:  ${request.approvedBy || ''}`)
  setCellText(documentXml, tableCell(tables, 1, 1, 1), `Date:  ${request.approvedDate || ''}`)

  const waferTable = tables[2]
  const rows = directChildren(waferTable, 'tr')
  if (rows.length < 2) throw new Error('Word 模板缺少 Wafer Details 数据行')
  const templateRow = rows[rows.length - 1]
  while (directChildren(waferTable, 'tr').length - 1 < form.wafers.length) waferTable.appendChild(templateRow.cloneNode(true))
  directChildren(waferTable, 'tr').slice(1).forEach((row, index) => fillWaferRow(documentXml, row, form.wafers[index]))
  return new XMLSerializer().serializeToString(documentXml)
}

export function buildDemoRequestDocx(request: DemoRequestDto, templateBytes: Uint8Array | ArrayBuffer) {
  const entries = readStoredZip(templateBytes)
  const documentEntry = entries.find((entry) => entry.name === 'word/document.xml')
  if (!documentEntry) throw new Error('Word 模板缺少 word/document.xml')
  const xml = new TextDecoder().decode(documentEntry.data)
  documentEntry.data = new TextEncoder().encode(populateDocumentXml(request, xml))
  return writeStoredZip(entries)
}

export async function loadDemoRequestTemplate() {
  const url = new URL(TEMPLATE_PATH, document.baseURI)
  const response = await fetch(url)
  if (!response.ok) throw new Error('Word 模板加载失败，请重试')
  return response.arrayBuffer()
}

function safeFilePart(value: string) {
  return value.replace(/[\\/:*?"<>|]/g, '-').replace(/[. ]+$/g, '').trim() || 'Demo-Request'
}

export function demoRequestFileName(request: DemoRequestDto) {
  const date = new Date().toISOString().slice(0, 10)
  return `Demo_Request_${safeFilePart(request.id)}_${safeFilePart(request.accountName)}_${date}.docx`
}

export function buildDemoRequestDocxArtifact(request: DemoRequestDto, templateBytes: Uint8Array | ArrayBuffer) {
  const bytes = buildDemoRequestDocx(request, templateBytes)
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
  return {
    fileName: demoRequestFileName(request),
    blob: new Blob([buffer], { type: DOCX_MIME }),
  }
}

export async function generateDemoRequestDocxArtifact(request: DemoRequestDto) {
  return buildDemoRequestDocxArtifact(request, await loadDemoRequestTemplate())
}

export async function downloadDemoRequestDocx(request: DemoRequestDto) {
  const artifact = await generateDemoRequestDocxArtifact(request)
  downloadBlob(artifact.blob, artifact.fileName)
}
