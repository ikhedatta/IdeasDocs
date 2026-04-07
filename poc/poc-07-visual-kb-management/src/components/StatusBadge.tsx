import type { DocumentStatus } from '@/lib/types';
import clsx from 'clsx';

const STATUS_CONFIG: Record<
  DocumentStatus | string,
  { label: string; color: string; dot: string }
> = {
  queued: { label: 'Queued', color: 'bg-gray-100 text-gray-700', dot: 'bg-gray-400' },
  parsing: { label: 'Parsing', color: 'bg-blue-100 text-blue-700', dot: 'bg-blue-500 animate-pulse' },
  chunking: { label: 'Chunking', color: 'bg-blue-100 text-blue-700', dot: 'bg-blue-500 animate-pulse' },
  embedding: { label: 'Embedding', color: 'bg-indigo-100 text-indigo-700', dot: 'bg-indigo-500 animate-pulse' },
  ready: { label: 'Ready', color: 'bg-green-100 text-green-700', dot: 'bg-green-500' },
  error: { label: 'Error', color: 'bg-red-100 text-red-700', dot: 'bg-red-500' },
};

export function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.queued;
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium',
        cfg.color,
      )}
    >
      <span className={clsx('h-1.5 w-1.5 rounded-full', cfg.dot)} />
      {cfg.label}
    </span>
  );
}

export function ActiveBadge({ active }: { active: boolean }) {
  return active ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
      <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
      Active
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700">
      <span className="h-1.5 w-1.5 rounded-full bg-orange-400" />
      Disabled
    </span>
  );
}
