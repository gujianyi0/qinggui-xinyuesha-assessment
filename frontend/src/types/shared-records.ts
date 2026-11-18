import type { DraftInput } from './domain'
export interface SharedPage<T> {
  items: T[]
  total: number
  offset: number
  limit: number
  readonly: true
}
export interface SharedFeedback {
  id: string
  revision: number
  status: string
  created_at: string
  payload: Partial<DraftInput>
}
