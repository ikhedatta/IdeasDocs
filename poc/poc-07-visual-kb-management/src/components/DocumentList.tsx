import Link from 'next/link';
import type { Document } from '@/lib/types';
import { StatusBadge } from './StatusBadge';
import { FileText, Layers } from 'lucide-react';

export function DocumentList({
  documents,
  kbId,
}: {
  documents: Document[];
  kbId: string;
}) {
  if (documents.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center text-sm text-gray-400">
        No documents yet. Upload files to get started.
      </div>
    );
  }

  return (
    <div className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
      {documents.map((doc) => (
        <div
          key={doc.id}
          className="flex items-center justify-between px-4 py-3 hover:bg-gray-50"
        >
          <div className="flex items-center gap-3">
            <FileText className="h-5 w-5 text-gray-400" />
            <div>
              <p className="text-sm font-medium text-gray-900">{doc.name}</p>
              <p className="text-xs text-gray-400">
                {doc.file_type.toUpperCase()} &middot;{' '}
                {(doc.file_size / 1024).toFixed(1)} KB
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1 text-xs text-gray-400">
              <Layers className="h-3.5 w-3.5" />
              {doc.chunk_count}
            </span>
            <StatusBadge status={doc.status} />
            {doc.status === 'ready' && doc.chunk_count > 0 && (
              <Link
                href={`/kb/${kbId}/chunks?document_id=${doc.id}`}
                className="rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-600 hover:bg-blue-100"
              >
                View Chunks
              </Link>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
