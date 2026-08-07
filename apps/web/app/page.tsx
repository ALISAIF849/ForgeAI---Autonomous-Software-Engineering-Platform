// Placeholder shell — proves the Next.js + Tailwind + Docker pipeline works end to
// end. The real landing/dashboard pages land in sub-sprints 1.6-1.8; nothing here
// is meant to be a finished screen.
export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-2 bg-neutral-950 text-neutral-50">
      <h1 className="text-3xl font-semibold tracking-tight">ForgeAI</h1>
      <p className="text-sm text-neutral-400">Workspace foundation — Sprint 1 in progress.</p>
    </main>
  );
}
