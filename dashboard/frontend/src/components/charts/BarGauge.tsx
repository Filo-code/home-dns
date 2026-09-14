import type { Severity } from "../StatusBadge";

/** A horizontal fill bar (block %, storage usage, ...) — text label + percentage, never color
 * alone (docs/specs/a8-frontend-dashboard.md §14). */
export function BarGauge({
  value,
  max = 100,
  label,
  severity,
}: {
  value: number;
  max?: number;
  label: string;
  severity: Severity;
}) {
  const percent = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className={`bar-gauge bar-gauge--${severity}`}>
      <div
        className="bar-gauge__track"
        role="meter"
        aria-valuenow={Math.round(value)}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={label}
      >
        <div className="bar-gauge__fill" style={{ width: `${percent}%` }} />
      </div>
      <span className="bar-gauge__label">{label}</span>
    </div>
  );
}
