import clsx from 'clsx';

interface OverlapBadgeProps {
  shared: number;
  onlyA: number;
  onlyB: number;
  jaccard: number;
}

export function OverlapBadge({ shared, onlyA, onlyB, jaccard }: OverlapBadgeProps) {
  const quality =
    jaccard >= 0.7 ? 'high' : jaccard >= 0.4 ? 'medium' : 'low';

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h4 className="mb-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
        Result Overlap
      </h4>

      <div className="flex items-center gap-6">
        {/* Venn diagram approximation */}
        <div className="relative flex items-center">
          <div className="h-16 w-16 rounded-full border-2 border-blue-300 bg-blue-50/50" />
          <div className="-ml-6 h-16 w-16 rounded-full border-2 border-purple-300 bg-purple-50/50" />
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-lg font-bold text-gray-700">{shared}</span>
          </div>
        </div>

        {/* Stats */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-blue-400" />
            <span className="text-xs text-gray-600">Only in A: {onlyA}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-purple-400" />
            <span className="text-xs text-gray-600">Only in B: {onlyB}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-green-400" />
            <span className="text-xs text-gray-600">Shared: {shared}</span>
          </div>
        </div>

        {/* Jaccard */}
        <div className="text-center">
          <span
            className={clsx(
              'text-2xl font-bold',
              quality === 'high' && 'text-green-600',
              quality === 'medium' && 'text-yellow-600',
              quality === 'low' && 'text-red-600',
            )}
          >
            {(jaccard * 100).toFixed(0)}%
          </span>
          <p className="text-[10px] text-gray-400">Jaccard Similarity</p>
        </div>
      </div>
    </div>
  );
}
