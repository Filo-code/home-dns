import { useId } from "react";

const RADIUS = 42;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export function HealthRing({
  score,
  label,
  size = "lg",
}: {
  score: number;
  label?: string;
  size?: "sm" | "lg";
}) {
  const gradientId = useId();
  const dimension = size === "lg" ? 120 : 34;
  const strokeWidth = size === "lg" ? 8 : 5;
  const offset = CIRCUMFERENCE - (CIRCUMFERENCE * score) / 100;

  return (
    <div className={`health-ring health-ring--${size}`}>
      <svg
        width={dimension}
        height={dimension}
        viewBox="0 0 100 100"
        role="img"
        aria-label={`Punteggio di salute: ${score} su 100${label ? `, ${label}` : ""}`}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--color-accent-from)" />
            <stop offset="100%" stopColor="var(--color-accent-to)" />
          </linearGradient>
        </defs>
        <circle
          cx="50"
          cy="50"
          r={RADIUS}
          fill="none"
          stroke="var(--color-border)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx="50"
          cy="50"
          r={RADIUS}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          transform="rotate(-90 50 50)"
        />
      </svg>
      {size === "lg" && (
        <div className="health-ring__center">
          <span className="health-ring__score">{score}%</span>
          {label && <span className="health-ring__label">{label}</span>}
        </div>
      )}
    </div>
  );
}
