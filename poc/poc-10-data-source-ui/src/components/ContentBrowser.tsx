'use client';

import { useEffect } from 'react';
import { useDataSourceStore } from '@/lib/store';
import { Folder, File, ChevronRight } from 'lucide-react';

interface ContentBrowserProps {
  connectorId: string;
}

export function ContentBrowser({ connectorId }: ContentBrowserProps) {
  const { browseItems, browsePath, browseLoading, browseContent } = useDataSourceStore();

  useEffect(() => {
    browseContent(connectorId, '');
  }, [connectorId]);

  const pathParts = browsePath ? browsePath.split('/').filter(Boolean) : [];

  return (
    <div className="bg-white rounded-lg border border-gray-200">
      {/* Breadcrumb */}
      <div className="px-4 py-2 border-b border-gray-100 flex items-center gap-1 text-sm">
        <button
          onClick={() => browseContent(connectorId, '')}
          className="text-brand-600 hover:text-brand-700"
        >
          Root
        </button>
        {pathParts.map((part, i) => {
          const fullPath = pathParts.slice(0, i + 1).join('/');
          return (
            <span key={fullPath} className="flex items-center gap-1">
              <ChevronRight size={12} className="text-gray-400" />
              <button
                onClick={() => browseContent(connectorId, fullPath)}
                className="text-brand-600 hover:text-brand-700"
              >
                {part}
              </button>
            </span>
          );
        })}
      </div>

      {/* Content */}
      {browseLoading ? (
        <div className="p-6 text-center text-gray-400 text-sm">Loading...</div>
      ) : browseItems.length === 0 ? (
        <div className="p-6 text-center text-gray-400 text-sm">No items found.</div>
      ) : (
        <div className="divide-y divide-gray-50">
          {browseItems.map((item) => {
            const isFolder = ['folder', 'space', 'repo', 'project', 'channel'].includes(
              item.item_type,
            );
            return (
              <div
                key={item.id}
                className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 cursor-pointer"
                onClick={() => {
                  if (isFolder) {
                    browseContent(connectorId, item.path || item.id);
                  }
                }}
              >
                {isFolder ? (
                  <Folder size={16} className="text-yellow-500" />
                ) : (
                  <File size={16} className="text-gray-400" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate">{item.name}</div>
                  <div className="text-[10px] text-gray-400">
                    {item.item_type}
                    {item.size_bytes != null && ` · ${formatBytes(item.size_bytes)}`}
                    {item.updated_at && ` · ${new Date(item.updated_at).toLocaleDateString()}`}
                  </div>
                </div>
                {isFolder && <ChevronRight size={14} className="text-gray-300" />}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}
