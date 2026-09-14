export function EmptyState({ label = "Nessun dato ancora disponibile." }: { label?: string }) {
  return <div className="state state--empty">{label}</div>;
}
