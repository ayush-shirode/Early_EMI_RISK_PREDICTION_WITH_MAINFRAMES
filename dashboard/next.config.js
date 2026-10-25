/** @type {import('next').NextConfig} */
// The browser only talks to Next.js; /api/backend/* is proxied to the FastAPI
// backend on localhost, which is the only process that talks to the mainframe.
const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

const nextConfig = {
  reactStrictMode: true,
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [{ source: '/api/backend/:path*', destination: `${BACKEND_URL}/:path*` }];
  },
};

module.exports = nextConfig;
