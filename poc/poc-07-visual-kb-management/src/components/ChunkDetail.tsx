import type { Chunk } from '@/lib/types';
import { X, Hash, FileText, Clock, ToggleLeft } from 'lucide-react';
import { ActiveBadge } from './StatusBadge';

interface ChunkDetailProps {
  chunk: Chunk;
  onClose: () => void;
}

export function ChunkDetail({ chunk, onClose }: ChunkDetailProps) {
  return (
    <div className="fixed inset-y-0 right-0 z-40 w-full max-w-lg border-l border-gray-200 bg-white shadow-xl sm:w-[480px]">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-5 py-3">
        <h3 className="text-sm font-semibold text-gray-900">Chunk Detail</h3>
        <button
          onClick={onClose}
          className="rounded p-1 text-gray-400 hover:bg-gray-100"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Metadata */}
      <div className="space-y-3 border-b px-5 py-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Status</span>
          <ActiveBadge active={chunk.is_active} />
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Chunk ID</span>
          <span className="font-mono text-xs text-gray-700">{chunk.chunk_id}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Order</span>
          <span className="text-xs text-gray-700">#{chunk.chunk_order}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Document</span>
          <span className="text-xs text-gray-700">{chunk.document_name}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Tokens</span>
          <span className="text-xs text-gray-700">{chunk.token_count}</span>
        </div>
        {chunk.created_at && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Created</span>
            <span className="text-xs text-gray-700">
              {new Date(chunk.created_at).toLocaleDateString()}
            </span>
          </div>
        )}
        {chunk.updated_at && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Updated</span>
            <span className="text-xs text-gray-700">
              {new Date(chunk.updated_at).toLocaleDateString()}
            </span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="px-5 py-4">
        <h4 className="mb-2 text-xs font-medium text-gray-500 uppercase tracking-wide">
          Content
        </h4>
        <div className="max-h-[50vh] overflow-y-auto rounded-lg bg-gray-50 p-4 text-sm text-gray-800 whitespace-pre-wrap">
          {chunk.content}
        </div>
      </div>

      {/* Metadata JSON */}
      {Object.keys(chunk.metadata).length > 0 && (
        <div className="px-5 py-4">
          <h4 className="mb-2 text-xs font-medium text-gray-500 uppercase tracking-wide">
            Metadata
          </h4>
          <pre className="max-h-32 overflow-y-auto rounded-lg bg-gray-50 p-3 text-xs text-gray-600">
            {JSON.stringify(chunk.metadata, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
