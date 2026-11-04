import { render, screen, waitFor } from "@testing-library/react";
import LoadingCenter, { UIKitTopProgress } from "@/components/uikit/LoadingCenter";

describe("LoadingCenter", () => {
  it("shows center spinner and label without top bar by default", () => {
    render(<LoadingCenter label="Ждём ответ" />);
    expect(screen.getByRole("status", { name: "Ждём ответ" })).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.getByText("Ждём ответ")).toBeInTheDocument();
    expect(document.querySelector(".uikit-spinner")).toBeTruthy();
  });

  it("can show top progress together with spinner", () => {
    render(<LoadingCenter label="Ждём ответ" topProgress />);
    expect(screen.getByRole("progressbar", { name: "Ждём ответ" })).toBeInTheDocument();
    expect(document.querySelector(".uikit-top-progress__bar")).toBeTruthy();
  });
});

describe("UIKitTopProgress", () => {
  it("hides after DOM-ready cycle", async () => {
    render(<UIKitTopProgress label="Страница" />);
    expect(screen.getByRole("progressbar", { name: "Страница" })).toBeInTheDocument();
    await waitFor(
      () => {
        expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
      },
      { timeout: 2000 },
    );
  });

  it("completes when active becomes false", async () => {
    const onFinished = vi.fn();
    const { rerender } = render(
      <UIKitTopProgress label="Синх" active onFinished={onFinished} />,
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-busy", "true");
    rerender(<UIKitTopProgress label="Синх" active={false} onFinished={onFinished} />);
    await waitFor(() => expect(onFinished).toHaveBeenCalled(), { timeout: 2000 });
  });
});
