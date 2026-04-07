import clsx from 'clsx';

interface ScoreBarProps {
  label: string;
  value: number;
  max?: number;
  color: string;
}

export function ScoreBar({ label, value, max = 1, color }: ScoreBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="flex items-center gap-2">
      <span className="w-16 text-right text-[11px] text-gray-500">{label}</span>
      <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-gray-100">
        <div
          className={clsx('absolute inset-y-0 left-0 rounded-full transition-all', color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-12 text-right font-mono text-[11px] text-gray-700">
        {value.toFixed(4)}
      </span>
    </div>
  );
}

interface ScoreBreakdownProps {
  dense: number;
  sparse: number;
  combined: number;
  rerank: number | null;
  final: number;
}

export function ScoreBreakdown({ dense, sparse, combined, rerank, final: finalScore }: ScoreBreakdownProps) {
  return (
    <div className="space-y-1">
      <ScoreBar label="Dense" value={dense} color="bg-blue-500" />
      <ScoreBar label="Sparse" value={sparse} color="bg-orange-400" />
      <ScoreBar label="Combined" value={combined} color="bg-cyan-500" />
      {rerank !== null && (
        <ScoreBar label="Rerank" value={rerank} color="bg-purple-500" />
      )}
      <ScoreBar label="Final" value={finalScore} color="bg-green-500" />
    </div>
  );
}
