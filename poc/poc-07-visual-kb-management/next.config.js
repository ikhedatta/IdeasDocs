/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/kb/:path*',
        destination: `${process.env.NEXT_PUBLIC_KB_API_URL || 'http://localhost:8006'}/kb/:path*`,
      },
      {
        source: '/api/chunks/:path*',
        destination: `${process.env.NEXT_PUBLIC_CHUNK_API_URL || 'http://localhost:8004'}/chunks/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
