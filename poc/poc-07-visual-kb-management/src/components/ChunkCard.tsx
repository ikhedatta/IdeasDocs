'use client';

import type { Chunk } from '@/lib/types';
import { ActiveBadge } from './StatusBadge';
import { Hash, FileText, Pencil } from 'lucide-react';
import clsx from 'clsx';

interface ChunkCardProps {
  chunk: Chunk;
  onToggle: (chunkId: string, active: boolean) => void;
  onEdit: (chunk: Chunk) => void;
  onSelect: (chunk: Chunk) => void;
}

export function ChunkCard({ chunk, onToggle, onEdit, onSelect }: ChunkCardProps) {
  return (
    <div
      className={clsx(
        'group rounded-lg border bg-white transition',
        chunk.is_active
          ? 'border-gray-200 hover:border-blue-200'
          : 'border-orange-200 bg-orange-50/30',
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-gray-400">
            #{chunk.chunk_order}
          </span>
          <ActiveBadge active={chunk.is_active} />
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onEdit(chunk)}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            title="Edit chunk"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => onToggle(chunk.chunk_id, !chunk.is_active)}
            className={clsx(
              'rounded px-2 py-0.5 text-xs font-medium transition',
              chunk.is_active
                ? 'bg-orange-50 text-orange-600 hover:bg-orange-100'
                : 'bg-green-50 text-green-600 hover:bg-green-100',
            )}
          >
            {chunk.is_active ? 'Disable' : 'Enable'}
          </button>
        </div>
      </div>

      {/* Content preview */}
      <button
        onClick={() => onSelect(chunk)}
        className="w-full px-4 py-3 text-left"
      >
        <p className="line-clamp-4 text-sm text-gray-700 whitespace-pre-wrap">
          {chunk.content}
        </p>
      </button>

      {/* Footer */}
      <div className="flex items-center gap-4 border-t border-gray-100 px-4 py-2 text-xs text-gray-400">
        <span className="flex items-center gap-1">
          <Hash className="h-3 w-3" />
          {chunk.token_count} tokens
        </span>
        <span className="flex items-center gap-1">
          <FileText className="h-3 w-3" />
          {chunk.document_name}
        </span>
        <span className="ml-auto font-mono text-[10px]">
          {chunk.chunk_id.slice(0, 8)}
        </span>
      </div>
    </div>
  );
}
