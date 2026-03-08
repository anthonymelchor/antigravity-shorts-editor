import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Proxy API requests internally: uses BACKEND_PROXY_URL in Docker, defaults to localhost for Windows dev
  async rewrites() {
    const backendUrl = process.env.BACKEND_PROXY_URL || 'http://127.0.0.1:8000';
    return [
      {
        source: '/proxy/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
