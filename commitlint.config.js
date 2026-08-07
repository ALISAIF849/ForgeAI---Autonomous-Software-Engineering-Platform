// Conventional Commits, enforced by Husky's commit-msg hook.
// Scope-enum is tied to actual package/service names so a commit's scope always
// answers "which folder changed" — see docs/engineering/04-git-strategy.md.
export default {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "scope-enum": [
      2,
      "always",
      [
        "web",
        "api",
        "worker",
        "ui",
        "sdk",
        "types",
        "config",
        "workflow-engine",
        "capability-registry",
        "model-router",
        "memory-engine",
        "prompts",
        "integrations",
        "docs",
        "ci",
        "deps",
        "repo",
      ],
    ],
  },
};
