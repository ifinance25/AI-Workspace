import { render, screen } from "@testing-library/react";
import LoadingCenter from "@/components/uikit/LoadingCenter";

describe("LoadingCenter", () => {
  it("shows spinner and label", () => {
    render(<LoadingCenter label="Ждём ответ" />);
    expect(screen.getByRole("status", { name: "Ждём ответ" })).toBeInTheDocument();
    expect(screen.getByText("Ждём ответ")).toBeInTheDocument();
    expect(document.querySelector(".uikit-spinner")).toBeTruthy();
  });
});
