export interface ShelfDocument {
  id: string
  kind: 'learning' | 'assessment_reference'
  title: string
  filename: string
  sourcePath: string
  group?: number
  goal?: string
  search: string
  toc: { id: string; level: number; text: string }[]
}
export interface ShelfCatalog {
  groups: { id: number; title: string; short: string }[]
  records: ShelfDocument[]
  reviewDocuments: ShelfDocument[]
  evidenceLinks: Record<string, string>
  evidenceFiles?: Record<string, { url: string; bytes: number; sha256: string }>
}
export interface ShelfProgress {
  ids: string[]
  revision: number
  initialized: boolean
  updatedAt: string | null
  can_edit: boolean
}
export interface LearningActions {
  learned: boolean | undefined
  saved: boolean
  canEdit: boolean
  busy: boolean
  onMastery: () => void
  onSave: () => void
}
