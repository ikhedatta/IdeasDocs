'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useKBStore } from '@/store/useKBStore';
import { ChunkCard } from '@/components/ChunkCard';
import { ChunkEditor } from '@/components/ChunkEditor';
import { ChunkDetail } from '@/components/ChunkDetail';
import { SearchFilter } from '@/components/SearchFilter';
import type { Chunk } from '@/lib/types';
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';

export default function ChunkExplorerPage() {
  const params = useParams<{ kbId: string }>();
  const kbId = params.kbId;
  const searchParams = useSearchParams();

  const documentId = searchParams.get('document_id') ?? undefined;
  const keyword = searchParams.get('keyword') ?? undefined;
  const status = searchParams.get('status') ?? 'all';
  const page = Number(searchParams.get('page') ?? '1');

  const { chunks, chunkTotal, loading, fetchChunks, toggleChunk, updateChunk } =
    useKBStore();

  const [editingChunk, setEditingChunk] = useState<Chunk | null>(null);
  const [selectedChunk, setSelectedChunk] = useState<Chunk | null>(null);

  useEffect(() => {
    fetchChunks({ kb_id: kbId, document_id: documentId, keyword, status, page });
  }, [kbId, documentId, keyword, status, page, fetchChunks]);

  const handleToggle = useCallback(
    async (chunkId: string, active: boolean) => {
      await toggleChunk(kbId, chunkId, active);
    },
    [kbId, toggleChunk],
  );

  const handleSaveEdit = useCallback(
    async (chunkId: string, content: string) => {
      await updateChunk(kbId, chunkId, content);
    },
    [kbId, updateChunk],
  );

  const totalPages = Math.ceil(chunkTotal / 20);

  return (
    <div>
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Link href="/" className="hover:text-blue-600">
          Knowledge Bases
        </Link>
        <span>/</span>
        <Link href={`/kb/${kbId}`} className="hover:text-blue-600">
          {kbId}
        </Link>
        <span>/</span>
        <span className="font-medium text-gray-900">Chunks</span>
      </div>

      <h1 className="mt-4 text-xl font-bold text-gray-900">
        Chunk Explorer
        <span className="ml-2 text-sm font-normal text-gray-400">
          ({chunkTotal} chunks)
        </span>
      </h1>

      {/* Filters */}
      <div className="mt-4">
        <SearchFilter />
      </div>

      {/* Chunk Grid */}
      {loading ? (
        <div className="mt-12 flex justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
        </div>
      ) : chunks.length === 0 ? (
        <div className="mt-12 text-center text-sm text-gray-400">
          No chunks found. Try adjusting your filters.
        </div>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {chunks.map((chunk) => (
            <ChunkCard
              key={chunk.chunk_id}
              chunk={chunk}
              onToggle={handleToggle}
              onEdit={setEditingChunk}
              onSelect={setSelectedChunk}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-2">
          <Link
            href={`/kb/${kbId}/chunks?page=${Math.max(1, page - 1)}&status=${status}${keyword ? `&keyword=${keyword}` : ''}${documentId ? `&document_id=${documentId}` : ''}`}
            className="rounded border border-gray-200 p-2 text-gray-400 hover:bg-gray-50 disabled:opacity-30"
          >
            <ChevronLeft className="h-4 w-4" />
          </Link>
          <span className="text-sm text-gray-600">
            Page {page} of {totalPages}
          </span>
          <Link
            href={`/kb/${kbId}/chunks?page=${Math.min(totalPages, page + 1)}&status=${status}${keyword ? `&keyword=${keyword}` : ''}${documentId ? `&document_id=${documentId}` : ''}`}
            className="rounded border border-gray-200 p-2 text-gray-400 hover:bg-gray-50"
          >
            <ChevronRight className="h-4 w-4" />
          </Link>
        </div>
      )}

      {/* Edit Modal */}
      {editingChunk && (
        <ChunkEditor
          chunk={editingChunk}
          onSave={handleSaveEdit}
          onClose={() => setEditingChunk(null)}
        />
      )}

      {/* Detail Sidepanel */}
      {selectedChunk && (
        <ChunkDetail
          chunk={selectedChunk}
          onClose={() => setSelectedChunk(null)}
        />
      )}
    </div>
  );
}
