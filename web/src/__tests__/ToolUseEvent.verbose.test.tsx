import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ToolUseEvent } from "@/components/events/ToolUseEvent";

const content = "🔧 Read\n   📂 AI-Workspace/AI-Workspace.md";

describe("ToolUseEvent verbose detail", () => {
  it("compact: только имя, без пути", () => {
    render(
      <ToolUseEvent
        name={content}
        metadata={{ name: "Read" }}
        detail="compact"
      />,
    );
    expect(screen.getByText("Read")).toBeTruthy();
    expect(screen.queryByText(/AI-Workspace\.md/)).toBeNull();
  });

  it("full: превью пути в свёрнутом виде", () => {
    render(
      <ToolUseEvent
        name={content}
        metadata={{ name: "Read" }}
        detail="full"
      />,
    );
    expect(screen.getByText(/AI-Workspace/)).toBeTruthy();
  });
});
