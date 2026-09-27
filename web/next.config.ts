import type { NextConfig } from "next";

// Browser calls /api/* on the Next server, which forwards them to FastAPI.
// One origin in the browser, so no CORS setup is needed in development.
const API_URL = process.env.API_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
