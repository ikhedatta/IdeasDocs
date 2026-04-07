/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/debug/:path*',
        destination: `${process.env.NEXT_PUBLIC_DEBUG_API_URL || 'http://localhost:8005'}/debug/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
