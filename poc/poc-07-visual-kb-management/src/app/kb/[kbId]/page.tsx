'use client';

import { useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useKBStore } from '@/store/useKBStore';
import { StatsBar } from '@/components/StatsBar';
import { DocumentList } from '@/components/DocumentList';
import { ArrowLeft, Layers, Loader2 } from 'lucide-react';

export default function KBDetailPage() {
  const params = useParams<{ kbId: string }>();
  const kbId = params.kbId;

  const { currentKB, stats, documents, loading, fetchKB, fetchStats, fetchDocuments } =
    useKBStore();

  useEffect(() => {
    fetchKB(kbId);
    fetchStats(kbId);
    fetchDocuments(kbId);
  }, [kbId, fetchKB, fetchStats, fetchDocuments]);

  if (loading && !currentKB) {
    return (
      <div className="flex justify-center pt-20">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div>
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Link href="/" className="hover:text-blue-600">
          Knowledge Bases
        </Link>
        <span>/</span>
        <span className="font-medium text-gray-900">
          {currentKB?.name ?? kbId}
        </span>
      </div>

      {/* Header */}
      <div className="mt-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">
            {currentKB?.name}
          </h1>
          {currentKB?.description && (
            <p className="mt-1 text-sm text-gray-500">
              {currentKB.description}
            </p>
          )}
        </div>
        <Link
          href={`/kb/${kbId}/chunks`}
          className="flex items-center gap-1.5 rounded-lg bg-blue-50 px-4 py-2 text-sm font-medium text-blue-600 hover:bg-blue-100"
        >
          <Layers className="h-4 w-4" />
          Browse All Chunks
        </Link>
      </div>

      {/* Stats */}
      {stats && (
        <div className="mt-6">
          <StatsBar stats={stats} />
        </div>
      )}

      {/* Document Status Breakdown */}
      {stats && Object.keys(stats.documents_by_status).length > 0 && (
        <div className="mt-4 flex gap-2">
          {Object.entries(stats.documents_by_status).map(([status, count]) => (
            <span
              key={status}
              className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-600"
            >
              {status}: {count}
            </span>
          ))}
        </div>
      )}

      {/* Documents */}
      <div className="mt-8">
        <h2 className="mb-3 text-sm font-semibold text-gray-700 uppercase tracking-wide">
          Documents ({documents.length})
        </h2>
        <DocumentList documents={documents} kbId={kbId} />
      </div>
    </div>
  );
}
