const prefix = (projectId: number, runId: number) => `office.runs.opened.${projectId}.${runId}`;

export function loadOpenedFindingIds(projectId: number, runId: number): Set<number> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = sessionStorage.getItem(prefix(projectId, runId));
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((v) => typeof v === "number"));
  } catch {
    return new Set();
  }
}

export function markFindingOpened(projectId: number, runId: number, findingId: number): Set<number> {
  const ids = loadOpenedFindingIds(projectId, runId);
  ids.add(findingId);
  try {
    sessionStorage.setItem(prefix(projectId, runId), JSON.stringify([...ids]));
  } catch {
    /* sessionStorage может быть недоступен */
  }
  return ids;
}

export function isPendingDecision(reviewStatus: string): boolean {
  return reviewStatus === "new" || reviewStatus === "needs_info";
}
