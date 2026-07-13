import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  ...(process.env.GITHUB_PAGES === "true"
    ? { output: "export", basePath: "/nasdaq-monitor" }
    : {}),
};

export default nextConfig;
