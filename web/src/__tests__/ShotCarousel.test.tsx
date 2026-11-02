import { describe, it, expect, vi } from "vitest";
import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import ShotCarousel, { type Shot } from "@/components/runs/ShotCarousel";

const shots: Shot[] = [
  { src: "/a.png", doc: "ФТТ1", page: 4, quote: "цитата" },
  { src: "/b.png", doc: "ПМИ1" },
  { src: "/c.png", doc: "ПМИ2", page: 9 },
];

function Host({ onClose = () => {} }: { onClose?: () => void }) {
  const [i, setI] = useState(0);
  return <ShotCarousel shots={shots} index={i} onIndex={setI} onClose={onClose} />;
}

describe("ShotCarousel", () => {
  it("заголовок и счётчик меняются при переходе", () => {
    render(<Host />);
    expect(screen.getByTestId("shot-title")).toHaveTextContent("ФТТ1, стр. 4");
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Следующий снимок" }));
    expect(screen.getByTestId("shot-title")).toHaveTextContent("ПМИ1");
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Предыдущий снимок" }));
    expect(screen.getByTestId("shot-title")).toHaveTextContent("ФТТ1, стр. 4");
  });

  it("точек столько же, сколько снимков, клик по точке переходит", () => {
    render(<Host />);
    const dots = screen.getAllByRole("button", { name: /^Снимок \d из 3/ });
    expect(dots).toHaveLength(3);
    fireEvent.click(dots[2]);
    expect(screen.getByTestId("shot-title")).toHaveTextContent("ПМИ2, стр. 9");
    expect(dots[2]).toHaveAttribute("aria-current", "true");
  });

  it("стрелки клавиатуры листают, на краях стоп, Esc закрывает", () => {
    const close = vi.fn();
    render(<Host onClose={close} />);
    expect(screen.getByRole("button", { name: "Предыдущий снимок" })).toBeDisabled();
    fireEvent.keyDown(window, { key: "ArrowRight" });
    fireEvent.keyDown(window, { key: "ArrowRight" });
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(screen.getByText("3 / 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Следующий снимок" })).toBeDisabled();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(close).toHaveBeenCalled();
  });

  it("у одного снимка нет стрелок и точек", () => {
    render(<ShotCarousel shots={[shots[0]]} index={0} onIndex={() => {}} onClose={() => {}} />);
    expect(screen.queryByRole("button", { name: "Следующий снимок" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Снимок/ })).toBeNull();
  });
});
