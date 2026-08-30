import type { ContactFileMetaDto, DemoArtifactMetaDto } from '@/types/crm'

/** Mock/IndexedDB-only binary storage. Never expose this shape through CrmApi JSON responses. */
export type StoredContactFile = ContactFileMetaDto & { blob: Blob }

/** Mock repository-only artifact storage. Never expose this shape through CrmApi JSON responses. */
export type StoredDemoArtifact = DemoArtifactMetaDto & { blob: Blob }
