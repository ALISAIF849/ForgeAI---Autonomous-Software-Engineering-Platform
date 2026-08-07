// Next.js's own build-time lint step looks for a config local to this directory
// and doesn't know to look at the workspace root — this just points it there
// rather than duplicating rules. The real, authoritative config is the root one;
// this file exists only so `next build`'s internal linter can find it.
import rootConfig from "../../eslint.config.mjs";

export default rootConfig;
