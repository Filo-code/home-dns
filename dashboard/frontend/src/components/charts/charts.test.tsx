import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BarGauge } from "./BarGauge";
import { LineChart } from "./LineChart";
import { Sparkline } from "./Sparkline";

afterEach(cleanup);

describe("Sparkline", () => {
  it("renders nothing for an empty series", () => {
    const { container } = render(<Sparkline values={[]} />);
    expect(container.querySelector("svg")).toBeNull();
  });

  it("renders one point per value plus a descriptive label", () => {
    render(<Sparkline values={[1, 5, 3]} />);
    const svg = screen.getByRole("img");
    expect(svg.getAttribute("aria-label")).toBe("andamento da 1 a 3");
    expect(svg.querySelector("polyline")?.getAttribute("points")?.split(" ")).toHaveLength(3);
  });
});

describe("LineChart", () => {
  it("shows the empty state when there are no points", () => {
    render(<LineChart points={[]} />);
    expect(screen.getByText("Nessun dato nel periodo selezionato.")).toBeTruthy();
  });

  it("labels the first, max and last values", () => {
    render(
      <LineChart
        points={[
          { x: "10:00", y: 1 },
          { x: "11:00", y: 9 },
          { x: "12:00", y: 4 },
        ]}
        formatValue={(y) => `${y}!`}
      />,
    );
    expect(screen.getByText("10:00")).toBeTruthy();
    expect(screen.getByText("12:00")).toBeTruthy();
    expect(screen.getByText("9!")).toBeTruthy(); // the max
  });
});

describe("BarGauge", () => {
  it("clamps the fill width to [0, 100]% and exposes an ARIA meter", () => {
    render(<BarGauge value={150} max={100} label="CPU: 150%" severity="critical" />);
    const meter = screen.getByRole("meter");
    expect(meter.getAttribute("aria-valuenow")).toBe("150");
    const fill = meter.querySelector(".bar-gauge__fill") as HTMLElement;
    expect(fill.style.width).toBe("100%");
    expect(screen.getByText("CPU: 150%")).toBeTruthy();
  });

  it("never relies on color alone: severity is also in the CSS class and the text label", () => {
    render(<BarGauge value={10} label="RAM: 10%" severity="warning" />);
    expect(document.querySelector(".bar-gauge--warning")).toBeTruthy();
    expect(screen.getByText("RAM: 10%")).toBeTruthy();
  });
});
