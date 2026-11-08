import type { NextConfig } from "next";
const config: NextConfig = { output: "export", trailingSlash: true, transpilePackages: ["@fetchdeck/brand-ui"] };
export default config;
