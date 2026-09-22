/** @type {import('next').NextConfig} */
const backendOrigin =
  process.env.DEEPCLAW_DEV_BACKEND_ORIGIN || 'http://127.0.0.1:7869'
const isDevelopment = process.env.NODE_ENV === 'development'

const nextConfig = {
  reactStrictMode: true,
  ...(isDevelopment
    ? {
        async rewrites() {
          return [
            {
              source: '/api/:path*',
              destination: `${backendOrigin}/api/:path*`,
            },
            {
              source: '/charts/:path*',
              destination: `${backendOrigin}/charts/:path*`,
            },
          ]
        },
      }
    : {
        output: 'export',
      }),
}

module.exports = nextConfig
