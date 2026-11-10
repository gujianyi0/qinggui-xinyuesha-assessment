export interface User { id: string; username: string }
export interface Auth { access_token: string; token_type: string; user: User }
export interface Session { id: string; title: string; created_at: string }
export interface Citation {
  id: string; title: string; path: string; line_start?: number; line_end?: number;
  snapshot_id: string; evidence_type?: string; excerpt?: string;
}
export interface Message { id: string; role: string; content: string; citations: Citation[]; created_at?: string }
export interface Snapshot { id: string; label: string; active: boolean; commit?: string }
export interface Entity {
  id: string; kind: string; name: string; package: string; description: string;
  attributes: Record<string, unknown>; source?: Citation;
}
export interface Ruling {
  id: string; title: string; status: string; required_conditions: string[] | Record<string, unknown>;
  summary?: string; snapshot_id: string;
}
export interface DraftInput {
  session_id?: string; category: 'rules' | 'client'; actual: string; expected: string;
  steps: string; context: string; platform: string; client_version: string;
}
export interface Draft extends DraftInput {
  id: string; short_code: string; revision: number; status: string; missing_fields: string[];
}
export interface Feedback extends Partial<DraftInput> { id: string; draft_id: string; created_at?: string; revision?: number; payload?: Partial<DraftInput> }
export interface Job {
  id: string; status: string; attempts: number; error?: string | null;
  progress: number | Record<string, unknown>; result?: unknown; created_at: string;
}
export interface Health { status: string; model_mode?: string; snapshot_id?: string; [key: string]: unknown }
export interface StreamEvent { event: string; data: Record<string, unknown> }
