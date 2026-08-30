import type { CustomerWorkbookSpec, CustomerWorksheetSpec } from './customer-report-model'
import { downloadBlob } from '@/features/shared/download-blob'

const xmlEscape = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' })[char]!)
const colName = (index: number) => { let n = index + 1; let name = ''; while (n) { const remainder = (n - 1) % 26; name = String.fromCharCode(65 + remainder) + name; n = Math.floor((n - 1) / 26) } return name }
const colIndex = (name: string) => Array.from(name).reduce((index, char) => index * 26 + char.charCodeAt(0) - 64, 0) - 1
const visualLength = (value: unknown) => Array.from(String(value ?? '')).reduce((length, char) => length + (char.charCodeAt(0) > 255 ? 2 : 1), 0)

function mergeWidth(sheet: CustomerWorksheetSpec, rowNumber: number, columnIndex: number) {
  const merge = sheet.merges.map((ref) => ({ ref, match: /^([A-Z]+)(\d+):([A-Z]+)(\d+)$/.exec(ref) }))
    .find(({ match }) => match && Number(match[2]) <= rowNumber && Number(match[4]) >= rowNumber && colIndex(match[1]) === columnIndex)
  if (!merge?.match) return Number(sheet.columns[columnIndex]?.width || 12)
  const start = colIndex(merge.match[1]), end = colIndex(merge.match[3])
  return sheet.columns.slice(start, end + 1).reduce((width, column) => width + Number(column?.width || 12), 0)
}

function adaptiveRowHeight(sheet: CustomerWorksheetSpec, row: CustomerWorksheetSpec['rows'][number], rowIndex: number) {
  const wrappedStyles = new Set([4, 9, 10, 13, 14])
  let lines = 1
  row.forEach((reportCell, columnIndex) => {
    if (!reportCell || !wrappedStyles.has(Number(reportCell.s || 0)) || reportCell.v === '') return
    const width = Math.max(8, mergeWidth(sheet, rowIndex, columnIndex))
    lines = Math.max(lines, Math.max(1, Math.ceil(visualLength(reportCell.v) / (width * .95))))
  })
  return Math.min(90, Math.max(22, lines === 1 ? 22 : 18 + lines * 15))
}

function worksheetXml(sheet: CustomerWorksheetSpec) {
  const colCount = Math.max(sheet.columns.length, ...sheet.rows.map((row) => row.length))
  const cols = sheet.columns.map((column, index) => `<col min="${index + 1}" max="${index + 1}" width="${Number(column.width || 12)}" customWidth="1"/>`).join('')
  const rows = sheet.rows.map((row, rowIndex) => {
    const cells = row.map((reportCell, columnIndex) => {
      if (!reportCell || reportCell.v === '' || reportCell.v == null) return ''
      const ref = `${colName(columnIndex)}${rowIndex + 1}`
      if (typeof reportCell.v === 'number' && Number.isFinite(reportCell.v)) return `<c r="${ref}" s="${reportCell.s}"><v>${reportCell.v}</v></c>`
      return `<c r="${ref}" s="${reportCell.s}" t="inlineStr"><is><t xml:space="preserve">${xmlEscape(reportCell.v)}</t></is></c>`
    }).join('')
    return `<row r="${rowIndex + 1}" ht="${adaptiveRowHeight(sheet, row, rowIndex + 1)}" customHeight="1">${cells}</row>`
  }).join('')
  const merges = sheet.merges.length ? `<mergeCells count="${sheet.merges.length}">${sheet.merges.map((ref) => `<mergeCell ref="${ref}"/>`).join('')}</mergeCells>` : ''
  const pane = sheet.freezeRows ? `<pane ySplit="${sheet.freezeRows}" topLeftCell="A${sheet.freezeRows + 1}" activePane="bottomLeft" state="frozen"/>` : ''
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:${colName(colCount - 1)}${sheet.rows.length}"/><sheetViews><sheetView workbookViewId="0">${pane}</sheetView></sheetViews><sheetFormatPr defaultRowHeight="18"/><cols>${cols}</cols><sheetData>${rows}</sheetData>${merges}</worksheet>`
}

function stylesXml() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="1"><numFmt numFmtId="164" formatCode="¥#,##0"/></numFmts><fonts count="8"><font><sz val="10"/><name val="Calibri"/><color rgb="FF24333A"/></font><font><b/><sz val="18"/><name val="Calibri"/><color rgb="FFFFFFFF"/></font><font><sz val="10"/><name val="Calibri"/><color rgb="FF66767C"/></font><font><b/><sz val="11"/><name val="Calibri"/><color rgb="FFFFFFFF"/></font><font><b/><sz val="9"/><name val="Calibri"/><color rgb="FF123047"/></font><font><b/><sz val="16"/><name val="Calibri"/><color rgb="FF147C72"/></font><font><b/><sz val="9"/><name val="Calibri"/><color rgb="FFB42318"/></font><font><b/><sz val="9"/><name val="Calibri"/><color rgb="FFA15C00"/></font></fonts><fills count="8"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF123047"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEEF6F4"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FF147C72"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE9E8E5"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFDECEC"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFF4DE"/></patternFill></fill></fills><borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFD5DEDB"/></left><right style="thin"><color rgb="FFD5DEDB"/></right><top style="thin"><color rgb="FFD5DEDB"/></top><bottom style="thin"><color rgb="FFD5DEDB"/></bottom><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="16"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1"/><xf numFmtId="0" fontId="3" fillId="4" borderId="0" xfId="0" applyFont="1" applyFill="1"/><xf numFmtId="0" fontId="4" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/><xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/><xf numFmtId="10" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/><xf numFmtId="0" fontId="5" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment horizontal="center" vertical="center"/></xf><xf numFmtId="0" fontId="6" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment wrapText="1"/></xf><xf numFmtId="0" fontId="7" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"><alignment wrapText="0" vertical="center"/></xf><xf numFmtId="14" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/><xf numFmtId="0" fontId="0" fillId="7" borderId="1" xfId="0" applyFill="1" applyBorder="1"><alignment wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="164" fontId="5" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1"><alignment horizontal="center" vertical="center"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles><dxfs count="0"/><tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/></styleSheet>`
}

let crcTable: number[] | null = null
function crc32(bytes: Uint8Array) {
  if (!crcTable) crcTable = Array.from({ length: 256 }, (_, number) => { let value = number; for (let index = 0; index < 8; index += 1) value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1; return value >>> 0 })
  let crc = 0xffffffff
  for (const byte of bytes) crc = crcTable[(crc ^ byte) & 255] ^ (crc >>> 8)
  return (crc ^ 0xffffffff) >>> 0
}
function concatBytes(parts: Uint8Array[]) { const total = parts.reduce((sum, part) => sum + part.length, 0); const output = new Uint8Array(total); let offset = 0; parts.forEach((part) => { output.set(part, offset); offset += part.length }); return output }

interface ZipFile { name: string; data: string | Uint8Array }
function zipStore(files: ZipFile[]) {
  const encoder = new TextEncoder(), locals: Uint8Array[] = [], centrals: Uint8Array[] = []
  let offset = 0
  const dosTime = (10 << 11) | (30 << 5), dosDate = ((2026 - 1980) << 9) | (7 << 5) | 17
  files.forEach((file) => {
    const name = encoder.encode(file.name), bytes = typeof file.data === 'string' ? encoder.encode(file.data) : file.data, crc = crc32(bytes)
    const local = new Uint8Array(30), localView = new DataView(local.buffer)
    localView.setUint32(0, 0x04034b50, true); localView.setUint16(4, 20, true); localView.setUint16(10, dosTime, true); localView.setUint16(12, dosDate, true); localView.setUint32(14, crc, true); localView.setUint32(18, bytes.length, true); localView.setUint32(22, bytes.length, true); localView.setUint16(26, name.length, true)
    locals.push(local, name, bytes)
    const central = new Uint8Array(46), centralView = new DataView(central.buffer)
    centralView.setUint32(0, 0x02014b50, true); centralView.setUint16(4, 20, true); centralView.setUint16(6, 20, true); centralView.setUint16(12, dosTime, true); centralView.setUint16(14, dosDate, true); centralView.setUint32(16, crc, true); centralView.setUint32(20, bytes.length, true); centralView.setUint32(24, bytes.length, true); centralView.setUint16(28, name.length, true); centralView.setUint32(42, offset, true)
    centrals.push(central, name); offset += local.length + name.length + bytes.length
  })
  const centralOffset = offset, centralBytes = concatBytes(centrals), end = new Uint8Array(22), endView = new DataView(end.buffer)
  endView.setUint32(0, 0x06054b50, true); endView.setUint16(8, files.length, true); endView.setUint16(10, files.length, true); endView.setUint32(12, centralBytes.length, true); endView.setUint32(16, centralOffset, true)
  return concatBytes([...locals, centralBytes, end])
}

export function buildXlsxFile(spec: CustomerWorkbookSpec) {
  const sheetOverrides = spec.sheets.map((_, index) => `<Override PartName="/xl/worksheets/sheet${index + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join('')
  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>${sheetOverrides}</Types>`
  const rootRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`
  const sheets = spec.sheets.map((sheet, index) => `<sheet name="${xmlEscape(sheet.name)}" sheetId="${index + 1}" r:id="rId${index + 1}"/>`).join('')
  const workbook = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>${sheets}</sheets></workbook>`
  const sheetRels = spec.sheets.map((_, index) => `<Relationship Id="rId${index + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${index + 1}.xml"/>`).join('')
  const workbookRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${sheetRels}<Relationship Id="rId${spec.sheets.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`
  const files: ZipFile[] = [{ name: '[Content_Types].xml', data: contentTypes }, { name: '_rels/.rels', data: rootRels }, { name: 'xl/workbook.xml', data: workbook }, { name: 'xl/_rels/workbook.xml.rels', data: workbookRels }, { name: 'xl/styles.xml', data: stylesXml() }]
  spec.sheets.forEach((sheet, index) => files.push({ name: `xl/worksheets/sheet${index + 1}.xml`, data: worksheetXml(sheet) }))
  return zipStore(files)
}

export function downloadCustomerReport(spec: CustomerWorkbookSpec) {
  const bytes = buildXlsxFile(spec)
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
  downloadBlob(new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), spec.fileName)
}
