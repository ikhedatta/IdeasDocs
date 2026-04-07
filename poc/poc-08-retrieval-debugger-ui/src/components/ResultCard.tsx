import type { DebugChunkResult } from '@/lib/types';
import { ScoreBreakdown } from './ScoreBar';
import { FileText } from 'lucide-react';
import clsx from 'clsx';

interface ResultCardProps {
  result: DebugChunkResult;
  highlight?: 'a-only' | 'b-only' | 'shared' | null;
}

export function ResultCard({ result, highlight }: ResultCardProps) {
  return (
    <div
      className={clsx(
        'rounded-lg border bg-white transition',
        highlight === 'a-only' && 'border-blue-300 bg-blue-50/30',
        highlight === 'b-only' && 'border-purple-300 bg-purple-50/30',
        highlight === 'shared' && 'border-green-300 bg-green-50/30',
        !highlight && 'border-gray-200',
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-gray-100 text-xs font-bold text-gray-600">
            {result.rank}
          </span>
          <span className="flex items-center gap-1 text-xs text-gray-500">
            <FileText className="h-3.5 w-3.5" />
            {result.document_name}
          </span>
        </div>
        <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-mono font-medium text-green-700">
          {result.final_score.toFixed(4)}
        </span>
      </div>

      {/* Content */}
      <div className="px-4 py-3">
        <p className="line-clamp-3 text-sm text-gray-700">
          {result.content_preview}
        </p>
      </div>

      {/* Score Breakdown */}
      <div className="border-t border-gray-100 px-4 py-3">
        <ScoreBreakdown
          dense={result.dense_score}
          sparse={result.sparse_score}
          combined={result.combined_score}
          rerank={result.rerank_score}
          final={result.final_score}
        />
      </div>

      {/* Chunk ID */}
      <div className="border-t border-gray-100 px-4 py-1.5">
        <span className="font-mono text-[10px] text-gray-400">
          {result.chunk_id}
        </span>
      </div>
    </div>
  );
}
