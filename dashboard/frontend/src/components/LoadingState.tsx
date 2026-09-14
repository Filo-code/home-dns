export function LoadingState({ label = "Caricamento…" }: { label?: string }) {
  return (
    <div className="state state--loading" role="status" aria-live="polite">
      {label}
    </div>
  );
}
