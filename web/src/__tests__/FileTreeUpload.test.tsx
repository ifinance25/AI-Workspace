import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FileTree from "@/components/files/FileTree";
import { api } from "@/api/client";

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "filesTree").mockResolvedValue({
    access_level: "full",
    truncated: false,
    entries: [],
  });
});

describe("FileTree upload", () => {
  it("показывает multiple input и шлёт выбранные файлы в текущую папку", async () => {
    const upload = vi.spyOn(api, "uploadProjectFiles").mockResolvedValue({
      uploaded: [
        { name: "a.txt", rel: "a.txt", type: "file", size_bytes: 1 },
        { name: "b.txt", rel: "b.txt", type: "file", size_bytes: 1 },
      ],
      errors: [],
    });
    render(
      <FileTree
        projectPath="/proj"
        canEdit
        onOpenFile={() => {}}
        reloadToken={0}
      />,
    );
    const input = await screen.findByLabelText("Загрузить файлы");
    expect(input).toHaveAttribute("multiple");
    expect(input).toHaveAttribute("data-upload-dir", "");

    const f1 = new File(["a"], "a.txt", { type: "text/plain" });
    const f2 = new File(["b"], "b.txt", { type: "text/plain" });
    await userEvent.upload(input, [f1, f2]);

    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    const [projectPath, dir, files] = upload.mock.calls[0];
    expect(projectPath).toBe("/proj");
    expect(dir).toBe("");
    expect(files).toHaveLength(2);
    expect(files.map((f: File) => f.name)).toEqual(["a.txt", "b.txt"]);
  });

  it("в подпапке вызывает API с rel этой папки", async () => {
    vi.spyOn(api, "filesTree").mockImplementation(async (_path: string, dir = "") => {
      if (dir === "") {
        return {
          access_level: "full" as const,
          truncated: false,
          entries: [{ name: "docs", rel: "docs", type: "dir" as const, size_bytes: null }],
        };
      }
      return { access_level: "full" as const, truncated: false, entries: [] };
    });
    const upload = vi.spyOn(api, "uploadProjectFiles").mockResolvedValue({
      uploaded: [{ name: "n.md", rel: "docs/n.md", type: "file", size_bytes: 2 }],
      errors: [],
    });
    render(
      <FileTree
        projectPath="/proj"
        canEdit
        onOpenFile={() => {}}
        reloadToken={0}
      />,
    );
    const input = await screen.findByLabelText("Загрузить файлы в docs");
    const file = new File(["n"], "n.md", { type: "text/markdown" });
    await userEvent.upload(input, file);
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    expect(upload.mock.calls[0][1]).toBe("docs");
  });

  it("без права записи скрывает input загрузки", async () => {
    render(
      <FileTree
        projectPath="/proj"
        canEdit={false}
        onOpenFile={() => {}}
        reloadToken={0}
      />,
    );
    await waitFor(() => expect(api.filesTree).toHaveBeenCalled());
    expect(screen.queryByLabelText("Загрузить файлы")).toBeNull();
  });
});
