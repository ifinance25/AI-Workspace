import type { LiveActivity } from "@/lib/liveActivity";

export type ToolUseDetail = "hidden" | "compact" | "full";

export function toolUseDetailLevel(verbose: number): ToolUseDetail {
  if (verbose <= 0) return "hidden";
  if (verbose === 1) return "compact";
  return "full";
}

const ASK_TOOLS = new Set(["AskUserQuestion", "ask_user_question"]);

/** Показывать ли бабл данного kind с учётом verbose (кроме tool_use — там отдельно). */
export function shouldRenderBubbleKind(
  kind: string,
  verbose: number,
  toolName?: string,
): boolean {
  if (kind === "tool_use") {
    if (toolName && ASK_TOOLS.has(toolName)) return true;
    return toolUseDetailLevel(verbose) !== "hidden";
  }
  if (kind === "subagent_start" || kind === "subagent_log" || kind === "subagent_finish") {
    return verbose >= 2;
  }
  if (kind === "log" || kind === "init") {
    return verbose >= 3;
  }
  return true;
}

export function activityForVerbose(activity: LiveActivity, verbose: number): LiveActivity {
  if (verbose >= 2 || !activity.context) return activity;
  return { ...activity, context: "" };
}
