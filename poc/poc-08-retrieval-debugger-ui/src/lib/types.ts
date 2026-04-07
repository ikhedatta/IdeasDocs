/* TypeScript interfaces for retrieval debug API */

export interface RetrievalConfig {
  top_k: number;
  final_k: number;
  similarity_threshold: number;
  dense_weight: number;
  sparse_weight: number;
  rerank_model: string | null;
}

export interface DebugChunkResult {
  rank: number;
  chunk_id: string;
  content_preview: string;
  document_name: string;
  dense_score: number;
  sparse_score: number;
  combined_score: number;
  rerank_score: number | null;
  final_score: number;
}

export interface Timings {
  embed_ms: number;
  search_ms: number;
  rerank_ms: number;
  total_ms: number;
}

export interface DebugSearchResponse {
  query: string;
  config: RetrievalConfig;
  timings_ms: Timings;
  total_candidates: number;
  after_threshold: number;
  final_count: number;
  results: DebugChunkResult[];
}

export interface RankChange {
  chunk_id: string;
  rank_a: number;
  rank_b: number;
  change: number;
}

export interface CompareResponse {
  query: string;
  config_a: DebugSearchResponse;
  config_b: DebugSearchResponse;
  comparison: {
    shared_chunks: number;
    only_in_a: number;
    only_in_b: number;
    jaccard_similarity: number;
    rank_changes: RankChange[];
  };
}

export interface TestCase {
  query: string;
  expected_chunk_ids?: string[];
  expected_keywords?: string[];
}

export interface BatchTestResult {
  query: string;
  recall_at_k: number;
  keyword_hit_rate: number;
  expected_ids: string[];
  found_ids: string[];
  missing_ids: string[];
  expected_keywords: string[];
  retrieved_count: number;
  timings_ms: Timings;
}

export interface BatchResponse {
  summary: {
    total_tests: number;
    avg_recall_at_k: number;
    avg_keyword_hit_rate: number;
    config: Partial<RetrievalConfig>;
  };
  test_results: BatchTestResult[];
}
