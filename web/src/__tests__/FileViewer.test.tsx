import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import FileViewer, { MAX_RICH_BYTES } from "@/components/files/FileViewer";
import type { FileContent } from "@/lib/types";

function file(rel: string, extra: Partial<FileContent> = {}): FileContent {
  return {
    rel,
    content: extra.content ?? "",
    size_bytes: extra.size_bytes ?? 100,
    mtime_ns: "0",
    binary: extra.binary ?? true,
    too_large: extra.too_large ?? false,
  };
}

describe("FileViewer", () => {
  it("PDF: iframe с inline-URL и ссылка в новой вкладке", () => {
    render(
      <FileViewer
        file={file("docs/report.pdf")}
        inlineUrl="/api/sessions/s/file?path=docs%2Freport.pdf&inline=1"
        downloadUrl="/api/sessions/s/file?path=docs%2Freport.pdf"
        onDownload={() => {}}
      />,
    );
    const frame = screen.getByTitle("docs/report.pdf");
    expect(frame.tagName).toBe("IFRAME");
    expect(frame.getAttribute("src")).toContain("inline=1");
    const tab = screen.getByText("Открыть в новой вкладке");
    expect(tab.getAttribute("href")).toContain("inline=1");
  });

  it("огромный DOCX: кнопка скачать, без iframe документа", () => {
    render(
      <FileViewer
        file={file("big.docx", { size_bytes: MAX_RICH_BYTES + 10 })}
        inlineUrl="/i"
        downloadUrl="/d"
        onDownload={() => {}}
      />,
    );
    expect(screen.getByText("Документ слишком большой для просмотра")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Скачать" })).toBeTruthy();
  });

  it("огромный XLSX: кнопка скачать", () => {
    render(
      <FileViewer
        file={file("big.xlsx", { size_bytes: MAX_RICH_BYTES + 10 })}
        inlineUrl="/i"
        downloadUrl="/d"
        onDownload={() => {}}
      />,
    );
    expect(screen.getByText("Таблица слишком большая для просмотра")).toBeTruthy();
  });

  it("огромный DOC: кнопка скачать", () => {
    render(
      <FileViewer
        file={file("big.doc", { size_bytes: MAX_RICH_BYTES + 10 })}
        inlineUrl="/i"
        downloadUrl="/d"
        onDownload={() => {}}
      />,
    );
    expect(screen.getByText("Документ слишком большой для просмотра")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Скачать" })).toBeTruthy();
  });

  it("DOC: открывает превью, не «бинарный файл»", () => {
    render(
      <FileViewer
        file={file("note.doc")}
        inlineUrl="/i"
        downloadUrl="/d"
        htmlPreviewUrl="/api/files/doc-preview?rel=note.doc"
        onDownload={() => {}}
      />,
    );
    expect(screen.getByText("Открываем документ…")).toBeTruthy();
    expect(screen.queryByText("Бинарный файл")).toBeNull();
  });
});
