import path from "node:path";
import type { NextConfig } from "next";

// `output: "standalone"` was tried here for future container builds and reverted:
// its file-tracing step relies on symlinks, which fail with EPERM on Windows dev
// machines without Developer Mode or admin rights (confirmed by actually running
// `next build`, not assumed) — a real dev-environment cost for an optimization
// nothing in Sprint 1 uses. Revisit when a production Dockerfile is actually built.
const nextConfig: NextConfig = {
  // Pins the monorepo root explicitly — without this, Next's workspace-root
  // inference can latch onto an unrelated lockfile elsewhere on the machine
  // (e.g. one sitting in the user's home directory) instead of this repo's own
  // pnpm-lock.yaml, which is exactly what happened in local testing.
  outputFileTracingRoot: path.join(__dirname, "../.."),
};

export default nextConfig;
