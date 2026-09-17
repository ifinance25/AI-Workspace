import { describe, it, expect } from "vitest";
import {
  fileViewerKind,
  MAX_RICH_BYTES,
} from "@/components/files/FileViewer";

describe("fileViewerKind", () => {
  it("выбирает viewer по расширению", () => {
    expect(fileViewerKind("docs/a.pdf")).toBe("pdf");
    expect(fileViewerKind("docs/a.PDF")).toBe("pdf");
    expect(fileViewerKind("note.docx")).toBe("docx");
    expect(fileViewerKind("note.doc")).toBe("doc");
    expect(fileViewerKind("note.DOC")).toBe("doc");
    expect(fileViewerKind("документ.Док")).toBe("doc");
    expect(fileViewerKind("t.xlsx")).toBe("xlsx");
    expect(fileViewerKind("t.xls")).toBe("xlsx");
    expect(fileViewerKind("t.xlsm")).toBe("xlsx");
    expect(fileViewerKind("pic.png")).toBe("image");
    expect(fileViewerKind("data.csv")).toBe("csv");
    expect(fileViewerKind("readme.md")).toBe("markdown");
    expect(fileViewerKind("app.ts")).toBe("text");
  });

  it("docx/xlsx крупнее лимита — только скачивание", () => {
    const huge = MAX_RICH_BYTES + 1;
    expect(fileViewerKind("big.docx", { sizeBytes: huge })).toBe("download");
    expect(fileViewerKind("big.doc", { sizeBytes: huge })).toBe("download");
    expect(fileViewerKind("big.xlsx", { sizeBytes: huge })).toBe("download");
    expect(fileViewerKind("ok.docx", { sizeBytes: 1024, binary: true })).toBe("docx");
    expect(fileViewerKind("ok.doc", { sizeBytes: 1024, binary: true })).toBe("doc");
  });

  it("pdf открывается даже если бэкенд пометил файл бинарным/крупным", () => {
    expect(
      fileViewerKind("a.pdf", { sizeBytes: 5_000_000, binary: true, tooLarge: true }),
    ).toBe("pdf");
  });

  it("прочий бинарь и oversized-текст — скачать", () => {
    expect(fileViewerKind("a.bin", { binary: true })).toBe("download");
    expect(fileViewerKind("huge.txt", { tooLarge: true })).toBe("download");
  });
});
