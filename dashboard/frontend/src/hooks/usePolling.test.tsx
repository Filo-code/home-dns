import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { usePolling } from "./usePolling";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  Object.defineProperty(document, "hidden", { value: false, configurable: true });
});

function Probe({ fetcher, intervalMs }: { fetcher: () => Promise<number>; intervalMs: number }) {
  const { data, error, loading } = usePolling(fetcher, intervalMs);
  return (
    <div>
      <span data-testid="data">{data ?? ""}</span>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="error">{error ? "error" : ""}</span>
    </div>
  );
}

describe("usePolling", () => {
  it("fetches once immediately on mount", async () => {
    const fetcher = vi.fn().mockResolvedValue(1);
    render(<Probe fetcher={fetcher} intervalMs={60_000} />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("data").textContent).toBe("1");
    expect(screen.getByTestId("loading").textContent).toBe("false");
  });

  it("polls again after intervalMs elapses", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockResolvedValue(1);
    render(<Probe fetcher={fetcher} intervalMs={1000} />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("does not poll while the tab is hidden", async () => {
    vi.useFakeTimers();
    Object.defineProperty(document, "hidden", { value: true, configurable: true });
    const fetcher = vi.fn().mockResolvedValue(1);
    render(<Probe fetcher={fetcher} intervalMs={1000} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("resumes immediately when the tab becomes visible again", async () => {
    Object.defineProperty(document, "hidden", { value: true, configurable: true });
    const fetcher = vi.fn().mockResolvedValue(1);
    render(<Probe fetcher={fetcher} intervalMs={60_000} />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(fetcher).not.toHaveBeenCalled();

    Object.defineProperty(document, "hidden", { value: false, configurable: true });
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
      await Promise.resolve();
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("never runs two overlapping requests at once", async () => {
    vi.useFakeTimers();
    let resolveFirst: (value: number) => void = () => {};
    const fetcher = vi
      .fn()
      .mockImplementationOnce(() => new Promise<number>((resolve) => (resolveFirst = resolve)))
      .mockResolvedValue(2);
    render(<Probe fetcher={fetcher} intervalMs={100} />);
    await act(async () => {
      await Promise.resolve();
    });
    // The interval fires again while the first call is still pending.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(fetcher).toHaveBeenCalledTimes(1); // still only the first, in-flight call

    await act(async () => {
      resolveFirst(1);
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("reports an error without discarding the last good data", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockResolvedValueOnce(1).mockRejectedValueOnce(new Error("boom"));
    render(<Probe fetcher={fetcher} intervalMs={1000} />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByTestId("data").textContent).toBe("1");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(screen.getByTestId("error").textContent).toBe("error");
    expect(screen.getByTestId("data").textContent).toBe("1"); // unchanged
  });

  it("restarts the cycle when a dependency changes", async () => {
    const fetcher = vi.fn((_id: number) => Promise.resolve(1));
    function Wrapper({ id }: { id: number }) {
      const fn = () => fetcher(id);
      const { data } = usePolling(fn, 60_000, [id]);
      return <span data-testid="data">{data ?? ""}</span>;
    }
    const { rerender } = render(<Wrapper id={1} />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(fetcher).toHaveBeenCalledWith(1);
    rerender(<Wrapper id={2} />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(fetcher).toHaveBeenCalledWith(2);
  });
});
