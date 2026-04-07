import type { BatchTestResult } from '@/lib/types';
import clsx from 'clsx';

interface BatchResultsProps {
  summary: {
    total_tests: number;
    avg_recall_at_k: number;
    avg_keyword_hit_rate: number;
  };
  results: BatchTestResult[];
}

export function BatchResults({ summary, results }: BatchResultsProps) {
  return (
    <div>
      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-gray-200 bg-white p-4 text-center">
          <p className="text-2xl font-bold text-gray-900">{summary.total_tests}</p>
          <p className="text-xs text-gray-500">Total Tests</p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-4 text-center">
          <p
            className={clsx(
              'text-2xl font-bold',
              summary.avg_recall_at_k >= 0.7
                ? 'text-green-600'
                : summary.avg_recall_at_k >= 0.4
                  ? 'text-yellow-600'
                  : 'text-red-600',
            )}
          >
            {(summary.avg_recall_at_k * 100).toFixed(1)}%
          </p>
          <p className="text-xs text-gray-500">Avg Recall@K</p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-4 text-center">
          <p
            className={clsx(
              'text-2xl font-bold',
              summary.avg_keyword_hit_rate >= 0.7
                ? 'text-green-600'
                : summary.avg_keyword_hit_rate >= 0.4
                  ? 'text-yellow-600'
                  : 'text-red-600',
            )}
          >
            {(summary.avg_keyword_hit_rate * 100).toFixed(1)}%
          </p>
          <p className="text-xs text-gray-500">Avg Keyword Hit Rate</p>
        </div>
      </div>

      {/* Results Table */}
      <div className="mt-4 overflow-hidden rounded-lg border border-gray-200 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase">
              <th className="px-4 py-2">Query</th>
              <th className="px-4 py-2 text-right">Recall@K</th>
              <th className="px-4 py-2 text-right">Keyword Hit</th>
              <th className="px-4 py-2 text-right">Retrieved</th>
              <th className="px-4 py-2 text-right">Missing</th>
              <th className="px-4 py-2 text-right">Time</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {results.map((r, i) => (
              <tr key={i} className="hover:bg-gray-50">
                <td className="max-w-xs truncate px-4 py-2 text-gray-700">
                  {r.query}
                </td>
                <td className="px-4 py-2 text-right">
                  <span
                    className={clsx(
                      'font-mono',
                      r.recall_at_k >= 0.7
                        ? 'text-green-600'
                        : r.recall_at_k >= 0.4
                          ? 'text-yellow-600'
                          : 'text-red-600',
                    )}
                  >
                    {(r.recall_at_k * 100).toFixed(0)}%
                  </span>
                </td>
                <td className="px-4 py-2 text-right font-mono text-gray-600">
                  {(r.keyword_hit_rate * 100).toFixed(0)}%
                </td>
                <td className="px-4 py-2 text-right text-gray-600">
                  {r.retrieved_count}
                </td>
                <td className="px-4 py-2 text-right">
                  {r.missing_ids.length > 0 ? (
                    <span className="text-red-600">{r.missing_ids.length}</span>
                  ) : (
                    <span className="text-green-600">0</span>
                  )}
                </td>
                <td className="px-4 py-2 text-right font-mono text-gray-500">
                  {r.timings_ms.total_ms}ms
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
