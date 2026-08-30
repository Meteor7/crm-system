import { describe, expectTypeOf, it } from 'vitest'
import type { CrmApi } from './contracts'
import type {
  BinaryDownload,
  DemoArtifactUploadInput,
  MultipartFilePart,
} from './binary-transport'
import type { DemoTestReportUploadInput } from '@/types/crm'

describe('CrmApi binary boundary', () => {
  it('returns authorized downloads outside ApiResponse JSON', () => {
    expectTypeOf<ReturnType<CrmApi['getContactFile']>>().toEqualTypeOf<Promise<BinaryDownload>>()
    expectTypeOf<ReturnType<CrmApi['getDemoArtifact']>>().toEqualTypeOf<Promise<BinaryDownload>>()
  })

  it('accepts explicit multipart inputs for all uploads', () => {
    expectTypeOf<Parameters<CrmApi['uploadContactFiles']>[1]>().toEqualTypeOf<MultipartFilePart[]>()
    expectTypeOf<Parameters<CrmApi['saveDemoArtifact']>[0]>().toEqualTypeOf<DemoArtifactUploadInput>()
    expectTypeOf<Parameters<CrmApi['releaseDemoTestReport']>[1]>().toEqualTypeOf<DemoTestReportUploadInput>()
  })
})
