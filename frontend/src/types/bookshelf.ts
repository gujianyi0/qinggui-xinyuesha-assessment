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
}
