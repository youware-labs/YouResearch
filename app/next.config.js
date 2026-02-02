/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  images: {
    unoptimized: true,
  },
  trailingSlash: true,
  // Use relative paths for Electron file:// loading
  assetPrefix: process.env.NODE_ENV === 'production' ? './' : undefined,
  // Fix for react-pdf and pdfjs-dist
  webpack: (config) => {
    config.resolve.alias.canvas = false;
    config.resolve.alias.encoding = false;
    return config;
  },
};

module.exports = nextConfig;
