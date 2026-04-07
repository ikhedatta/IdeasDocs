import Link from 'next/link';
import type { KnowledgeBase } from '@/lib/types';
import { Database, FileText, Layers } from 'lucide-react';

export function KBCard({ kb }: { kb: KnowledgeBase }) {
  return (
    <Link
      href={`/kb/${kb.id}`}
      className="group block rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition hover:border-blue-300 hover:shadow-md"
    >
      <div className="flex items-start justify-between">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
          <Database className="h-5 w-5" />
        </div>
        {kb.tags.length > 0 && (
          <div className="flex gap-1">
            {kb.tags.slice(0, 2).map((t) => (
              <span
                key={t}
                className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500"
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </div>

      <h3 className="mt-3 text-base font-semibold text-gray-900 group-hover:text-blue-600">
        {kb.name}
      </h3>
      {kb.description && (
        <p className="mt-1 line-clamp-2 text-sm text-gray-500">
          {kb.description}
        </p>
      )}

      <div className="mt-4 flex items-center gap-4 text-xs text-gray-400">
        <span className="flex items-center gap-1">
          <FileText className="h-3.5 w-3.5" />
          {kb.document_count} docs
        </span>
        <span className="flex items-center gap-1">
          <Layers className="h-3.5 w-3.5" />
          {kb.chunk_count.toLocaleString()} chunks
        </span>
      </div>
    </Link>
  );
}
