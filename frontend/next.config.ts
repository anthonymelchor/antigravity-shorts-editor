import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Configured to proxy API requests internally, eliminating CORS and local-IP issues
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://api:8000/api/:path*',
      },
    ];
  },
};

export default nextConfig;
