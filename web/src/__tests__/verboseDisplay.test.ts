import { describe, expect, it } from "vitest";
import {
  activityForVerbose,
  shouldRenderBubbleKind,
  toolUseDetailLevel,
} from "@/lib/verboseDisplay";

describe("verboseDisplay", () => {
  it("toolUseDetailLevel по уровням 0–3", () => {
    expect(toolUseDetailLevel(0)).toBe("hidden");
    expect(toolUseDetailLevel(1)).toBe("compact");
    expect(toolUseDetailLevel(2)).toBe("full");
    expect(toolUseDetailLevel(3)).toBe("full");
  });

  it("shouldRenderBubbleKind: tool_use и субагенты", () => {
    expect(shouldRenderBubbleKind("tool_use", 0, "Read")).toBe(false);
    expect(shouldRenderBubbleKind("tool_use", 1, "Read")).toBe(true);
    expect(shouldRenderBubbleKind("tool_use", 0, "AskUserQuestion")).toBe(true);
    expect(shouldRenderBubbleKind("subagent_log", 1)).toBe(false);
    expect(shouldRenderBubbleKind("subagent_log", 2)).toBe(true);
    expect(shouldRenderBubbleKind("log", 2)).toBe(false);
    expect(shouldRenderBubbleKind("log", 3)).toBe(true);
  });

  it("activityForVerbose обнуляет context при verbose < 2", () => {
    const act = { phase: "tool" as const, context: "/secret/path", toolName: "Read" };
    expect(activityForVerbose(act, 1).context).toBe("");
    expect(activityForVerbose(act, 2).context).toBe("/secret/path");
  });
});
