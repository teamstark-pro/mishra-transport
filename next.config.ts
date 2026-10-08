import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Fully static export — deployable by drag-and-drop (Vercel Drop, Netlify, any host)
  output: "export",
  trailingSlash: true,
  /* disabled for export mode: cacheComponents, partialPrefetching */
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
