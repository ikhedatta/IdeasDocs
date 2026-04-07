import './globals.css';
import type { Metadata } from 'next';
import Link from 'next/link';
import { Database } from 'lucide-react';

export const metadata: Metadata = {
  title: 'KB Manager — RAG Platform',
  description: 'Visual Knowledge Base Management with chunk-level inspection',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen">
          {/* Sidebar */}
          <aside className="w-56 shrink-0 border-r border-gray-200 bg-white">
            <div className="flex h-14 items-center gap-2 border-b px-4">
              <Database className="h-5 w-5 text-blue-600" />
              <span className="text-sm font-bold text-gray-900">
                KB Manager
              </span>
            </div>
            <nav className="p-3">
              <Link
                href="/"
                className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
              >
                Knowledge Bases
              </Link>
            </nav>
          </aside>

          {/* Main */}
          <main className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-6xl p-6">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
