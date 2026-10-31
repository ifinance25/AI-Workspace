import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ChatEmptyState from "@/components/ChatEmptyState";
import { PRODUCT_NAME } from "@/lib/branding";

describe("ChatEmptyState", () => {
  it("на пустом чате показывает название PM Workspace", () => {
    render(<ChatEmptyState />);
    expect(screen.getByText(PRODUCT_NAME)).toBeTruthy();
    expect(screen.queryByText(/Проект не подключён/)).toBeNull();
  });
});
