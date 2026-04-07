'use client';

import { useState } from 'react';
import type { Chunk } from '@/lib/types';
import { X, Save } from 'lucide-react';

interface ChunkEditorProps {
  chunk: Chunk;
  onSave: (chunkId: string, content: string) => Promise<void>;
  onClose: () => void;
}

export function ChunkEditor({ chunk, onSave, onClose }: ChunkEditorProps) {
  const [content, setContent] = useState(chunk.content);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (content.trim() === chunk.content) {
      onClose();
      return;
    }
    setSaving(true);
    try {
      await onSave(chunk.chunk_id, content.trim());
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-2xl rounded-xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-5 py-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-900">Edit Chunk</h3>
            <p className="text-xs text-gray-400">
              #{chunk.chunk_order} &middot; {chunk.document_name} &middot;{' '}
              <span className="font-mono">{chunk.chunk_id.slice(0, 8)}</span>
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Editor */}
        <div className="p-5">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={12}
            className="w-full rounded-lg border border-gray-200 p-3 text-sm text-gray-800 placeholder:text-gray-400 focus:border-blue-300 focus:outline-none focus:ring-1 focus:ring-blue-300"
          />
          <p className="mt-1 text-xs text-gray-400">
            Saving will re-embed this chunk automatically.
          </p>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t px-5 py-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || content.trim().length === 0}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {saving ? 'Saving...' : 'Save & Re-embed'}
          </button>
        </div>
      </div>
    </div>
  );
}
