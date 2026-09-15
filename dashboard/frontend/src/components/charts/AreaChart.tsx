import { useId } from "react";
import { EmptyState } from "../EmptyState";

export interface AreaChartPoint {
  x: string;
  allowed: number;
  blocked: number;
}

/** Two-series area chart (query volume, allowed vs blocked) for `/metrics/history` data — plain
 * SVG, no library, same scale/no-zoom approach as `LineChart`. */
export function AreaChart({
  points,
  width = 640,
  height = 180,
}: {
  points: AreaChartPoint[];
  width?: number;
  height?: number;
}) {
  const allowedGradientId = useId();
  const blockedGradientId = useId();

  if (points.length === 0) {
    return <EmptyState label="Nessun dato nel periodo selezionato." />;
  }

  const max = Math.max(...points.map((p) => p.allowed + p.blocked), 1);
  const stepX = points.length > 1 ? width / (points.length - 1) : 0;
  const y = (value: number) => height - (value / max) * height;

  const linePath = (values: number[]) =>
    values.map((v, i) => `${i === 0 ? "M" : "L"}${i * stepX},${y(v)}`).join(" ");
  const areaPath = (values: number[]) =>
    `${linePath(values)} L${(values.length - 1) * stepX},${height} L0,${height} Z`;

  const allowedValues = points.map((p) => p.allowed);
  const blockedValues = points.map((p) => p.blocked);
  const first = points[0]!;
  const last = points[points.length - 1]!;

  return (
    <figure className="area-chart">
      <div className="area-chart__legend">
        <span className="area-chart__legend-item area-chart__legend-item--allowed">
          Consentite
        </span>
        <span className="area-chart__legend-item area-chart__legend-item--blocked">Bloccate</span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-label={`query consentite e bloccate da ${first.x} a ${last.x}`}
      >
        <defs>
          <linearGradient id={allowedGradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-accent-from)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--color-accent-from)" stopOpacity="0" />
          </linearGradient>
          <linearGradient id={blockedGradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-accent-to)" stopOpacity="0.38" />
            <stop offset="100%" stopColor="var(--color-accent-to)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line
          x1={0}
          y1={height - 1}
          x2={width}
          y2={height - 1}
          className="line-chart__baseline"
        />
        <path d={areaPath(allowedValues)} fill={`url(#${allowedGradientId})`} />
        <path d={areaPath(blockedValues)} fill={`url(#${blockedGradientId})`} />
        <path d={linePath(allowedValues)} className="area-chart__line area-chart__line--allowed" />
        <path d={linePath(blockedValues)} className="area-chart__line area-chart__line--blocked" />
      </svg>
      <div className="line-chart__labels">
        <span>{first.x}</span>
        <span>{last.x}</span>
      </div>
    </figure>
  );
}
