// Single source of truth for what the Demo Test report uploads accept.
// The backend gate (file_security.py) already validates these exact types.
export const REPORT_UPLOAD_MAX_BYTES = 100 * 1024 * 1024

export const REPORT_UPLOAD_MIME_TYPES = new Set([
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'text/csv',
  'text/plain',
  'image/png',
  'image/jpeg',
])

export const REPORT_UPLOAD_ACCEPT = '.pdf,.docx,.xlsx,.pptx,.csv,.txt,.png,.jpg,.jpeg'
