import type { Locale } from '@/i18n'

const englishMessages: Record<string, string> = {
  'DOCX 文件结构损坏。': 'The DOCX file structure is damaged.',
  'XLSX 文件结构损坏。': 'The XLSX file structure is damaged.',
  'PDF 无法读取。': 'The PDF could not be read.',
  'PDF 没有可复制文本，扫描件暂不支持解析。': 'The PDF has no selectable text. Scanned documents cannot be parsed yet.',
  "文件已归档，此格式需手动补录。": "The file has been archived. Enter the meeting details manually for this format.",
  "会议记录解析成功。": "Meeting record parsed successfully.",
  "部分模板字段未识别，请检查并补录。": "Some template fields were not recognized. Review and complete them.",
  "未识别到会议模板字段，请手动补录。": "No meeting template fields were recognized. Enter the details manually.",
  "会议记录已人工确认。": "Meeting record confirmed manually."
}

export function meetingParseMessage(message: string, locale: Locale) {
  return locale === 'en-US' ? englishMessages[message] ?? message : message
}
