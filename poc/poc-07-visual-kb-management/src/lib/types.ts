/* --- TypeScript interfaces matching backend API models --- */

export interface ParserConfig {
  chunk_token_size: number;
  chunk_overlap_percent: number;
  delimiter: string;
  pdf_parser: string;
  extract_tables: boolean;
  extract_images: boolean;
  language: string;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  parser_config: ParserConfig;
  tags: string[];
  created_at: string;
  updated_at: string;
  document_count: number;
  chunk_count: number;
}

export interface KBStats {
  kb_id: string;
  kb_name: string;
  document_count: number;
  documents_by_status: Record<string, number>;
  chunk_count: number;
  active_chunks: number;
  inactive_chunks: number;
  estimated_tokens: number;
}

export type DocumentStatus =
  | 'queued'
  | 'parsing'
  | 'chunking'
  | 'embedding'
  | 'ready'
  | 'error';

export interface Document {
  id: string;
  kb_id: string;
  name: string;
  file_type: string;
  file_size: number;
  status: DocumentStatus;
  chunk_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface Chunk {
  chunk_id: string;
  content: string;
  document_id: string;
  document_name: string;
  kb_id: string;
  chunk_order: number;
  is_active: boolean;
  token_count: number;
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface ChunkListResponse {
  total: number;
  page: number;
  page_size: number;
  chunks: Chunk[];
}
