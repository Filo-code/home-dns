/**
 * Status must never rely on color alone (docs/specs/a8-frontend-dashboard.md §14): every badge
 * carries a glyph and a text label alongside its color.
 */
export type Severity = "ok" | "warning" | "critical" | "unknown";

const GLYPH: Record<Severity, string> = {
  ok: "●",
  warning: "▲",
  critical: "✕",
  unknown: "?",
};

export function StatusBadge({ severity, label }: { severity: Severity; label: string }) {
  return (
    <span className={`status-badge status-badge--${severity}`}>
      <span aria-hidden="true" className="status-badge__glyph">
        {GLYPH[severity]}
      </span>
      {label}
    </span>
  );
}
