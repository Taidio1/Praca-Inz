/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Obraz dockera (frontend/Dockerfile) uruchamia samodzielny serwer z .next/standalone
  output: 'standalone',
  experimental: {
    // Analiza spółek (SEC EDGAR) potrafi trwać dłużej niż domyślne 30 s proxy
    proxyTimeout: 120_000,
  },
  async rewrites() {
    // W dockerze API jest w sieci wewnętrznej; lokalnie (npm run dev) frontend woła je bezpośrednio
    const api = process.env.API_INTERNAL_URL;
    return api
      ? [
          { source: '/api/:path*', destination: `${api}/api/:path*` },
          // /health jest poza prefiksem /api, a frontend sprawdza nim, czy API żyje
          { source: '/health', destination: `${api}/health` },
        ]
      : [];
  },
};

export default nextConfig;
