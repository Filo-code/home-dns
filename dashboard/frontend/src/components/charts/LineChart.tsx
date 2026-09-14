import { EmptyState } from "../EmptyState";

export interface LineChartPoint {
  x: string;
  y: number;
}

/** A labelled trend line for the small aggregated datasets `/metrics/history` returns (at
 * most ~48 points) — plain SVG, no zoom/pan, no library. */
export function LineChart({
  points,
  width = 320,
  height = 96,
  formatValue = (y: number) => String(y),
}: {
  points: LineChartPoint[];
  width?: number;
  height?: number;
  formatValue?: (y: number) => string;
}) {
  if (points.length === 0) {
    return <EmptyState label="Nessun dato nel periodo selezionato." />;
  }
  const values = points.map((p) => p.y);
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const stepX = points.length > 1 ? width / (points.length - 1) : 0;
  const polylinePoints = points
    .map((point, index) => `${index * stepX},${height - ((point.y - min) / range) * height}`)
    .join(" ");
  const first = points[0]!;
  const last = points[points.length - 1]!;

  return (
    <figure className="line-chart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-label={`andamento nel tempo, da ${formatValue(first.y)} a ${formatValue(last.y)}, massimo ${formatValue(max)}`}
      >
        <line
          x1={0}
          y1={height - 1}
          x2={width}
          y2={height - 1}
          className="line-chart__baseline"
        />
        <polyline points={polylinePoints} fill="none" className="line-chart__line" />
      </svg>
      <div className="line-chart__labels">
        <span>{first.x}</span>
        <span>{formatValue(max)}</span>
        <span>{last.x}</span>
      </div>
    </figure>
  );
}
