/**
 * Persistent "DEMO MODE" marker, shown only when NEXT_PUBLIC_DEMO_MODE=1.
 * Keeps the no-key demo from ever being mistaken for a live production instance.
 * Floats over the empty center of the header so it never disturbs the app's
 * full-height layout. Server component — no client JS.
 */
export function DemoBanner() {
  if (process.env.NEXT_PUBLIC_DEMO_MODE !== "1") return null;

  return (
    <div className="pointer-events-none fixed top-3 left-1/2 -translate-x-1/2 z-50">
      <div className="pointer-events-auto flex items-center gap-2 rounded-full border border-primary/40 bg-primary/10 px-3 py-1 text-[11px] font-mono font-semibold text-primary shadow-sm backdrop-blur-sm">
        <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
        DEMO MODE
        <span className="font-normal text-primary/70">· canned answers, no live AI</span>
      </div>
    </div>
  );
}
