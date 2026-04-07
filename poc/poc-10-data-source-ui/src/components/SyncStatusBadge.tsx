interface SyncStatusBadgeProps {
  status: string;
}

const STATUS_STYLES: Record<string, string> = {
  active: 'bg-green-100 text-green-700',
  idle: 'bg-gray-100 text-gray-600',
  scheduled: 'bg-yellow-100 text-yellow-700',
  running: 'bg-blue-100 text-blue-700',
  done: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  cancelled: 'bg-gray-100 text-gray-500',
  paused: 'bg-yellow-100 text-yellow-700',
  error: 'bg-red-100 text-red-700',
  disconnected: 'bg-gray-100 text-gray-400',
};

export function SyncStatusBadge({ status }: SyncStatusBadgeProps) {
  const style = STATUS_STYLES[status] || 'bg-gray-100 text-gray-500';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${style}`}>
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          status === 'running'
            ? 'bg-blue-500 animate-pulse'
            : status === 'active' || status === 'done'
              ? 'bg-green-500'
              : status === 'failed' || status === 'error'
                ? 'bg-red-500'
                : 'bg-gray-400'
        }`}
      />
      {status}
    </span>
  );
}
