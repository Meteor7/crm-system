import type { DemoArtifactMetaDto } from '@/types/crm'

/** Browser-only multipart part. This value must never be JSON-serialized into ApiResponse. */
export interface MultipartFilePart {
  blob: Blob
  fileName: string
  mimeType: string
  size: number
}

/** Raw authorized download result. This deliberately sits outside the JSON ApiResponse envelope. */
export interface BinaryDownload {
  blob: Blob
  fileName: string
  mimeType: string
}

/** Metadata fields and the separate multipart file part used to create a Demo artifact. */
export interface DemoArtifactUploadInput {
  demoRequestId: string
  evaluationId?: string
  type: DemoArtifactMetaDto['type']
  visibility: DemoArtifactMetaDto['visibility']
  file: MultipartFilePart
}

export function appendMultipartFile(
  formData: FormData,
  fieldName: string,
  part: MultipartFilePart,
) {
  formData.append(fieldName, new File([part.blob], part.fileName, { type: part.mimeType }))
}
