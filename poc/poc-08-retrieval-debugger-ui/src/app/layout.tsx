import './globals.css';
import type { Metadata } from 'next';
import Link from 'next/link';
import { Bug } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Retrieval Debugger — RAG Platform',
  description: 'Interactive retrieval testing, score decomposition, and A/B comparison',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          {/* Top nav */}
          <header className="border-b border-gray-200 bg-white">
            <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3">
              <div className="flex items-center gap-2">
                <Bug className="h-5 w-5 text-purple-600" />
                <span className="text-sm font-bold text-gray-900">
                  Retrieval Debugger
                </span>
              </div>
              <nav className="flex gap-1">
                <Link
                  href="/"
                  className="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                >
                  Search
                </Link>
                <Link
                  href="/compare"
                  className="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                >
                  A/B Compare
                </Link>
                <Link
                  href="/batch"
                  className="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                >
                  Batch Test
                </Link>
              </nav>
            </div>
          </header>

          <main className="mx-auto max-w-6xl p-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
