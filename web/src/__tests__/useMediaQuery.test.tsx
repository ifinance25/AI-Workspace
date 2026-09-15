import { describe, it, expect, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { useMediaQuery } from "@/lib/useMediaQuery";

function Probe({ query }: { query: string }) {
  const matches = useMediaQuery(query);
  return <div>{matches ? "yes" : "no"}</div>;
}

describe("useMediaQuery", () => {
  afterEach(() => {
    // restore in case a test replaced matchMedia
  });

  it("читает текущее совпадение media query", () => {
    let matches = true;
    const listeners = new Set<() => void>();
    window.matchMedia = ((query: string) => ({
      get matches() {
        return matches;
      },
      media: query,
      addEventListener: (_: string, cb: () => void) => {
        listeners.add(cb);
      },
      removeEventListener: (_: string, cb: () => void) => {
        listeners.delete(cb);
      },
    })) as unknown as typeof window.matchMedia;

    render(<Probe query="(max-width: 1023px)" />);
    expect(screen.getByText("yes")).toBeInTheDocument();

    act(() => {
      matches = false;
      listeners.forEach((cb) => cb());
    });
    expect(screen.getByText("no")).toBeInTheDocument();
  });
});
