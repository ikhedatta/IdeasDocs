import type { Metadata } from 'next';
import '@/globals.css';

export const metadata: Metadata = {
  title: 'POC-10 · Data Source Management',
  description: 'Manage external data source connectors for your RAG platform.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen flex">
          {/* Sidebar */}
          <aside className="w-56 bg-white border-r border-gray-200 flex flex-col">
            <div className="p-4 border-b border-gray-200">
              <h1 className="text-lg font-bold text-brand-700">Data Sources</h1>
              <p className="text-xs text-gray-500 mt-0.5">POC-10 · Connector UI</p>
            </div>
            <nav className="flex-1 py-3">
              <NavLink href="/" label="Dashboard" icon="layout-dashboard" />
              <NavLink href="/catalog" label="Source Catalog" icon="store" />
              <NavLink href="/connections" label="My Connections" icon="plug" />
            </nav>
            <div className="p-3 border-t border-gray-200 text-xs text-gray-400">
              Connects to <span className="font-mono">:8009</span>
            </div>
          </aside>

          {/* Main */}
          <main className="flex-1 overflow-y-auto">{children}</main>
        </div>
      </body>
    </html>
  );
}

function NavLink({ href, label, icon }: { href: string; label: string; icon: string }) {
  return (
    <a
      href={href}
      className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 hover:text-brand-600 transition-colors"
    >
      <span className="w-4 h-4 text-gray-400">●</span>
      {label}
    </a>
  );
}
