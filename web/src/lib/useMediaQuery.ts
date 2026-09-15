import { useEffect, useState } from "react";

/** Подписка на CSS media query (например, узкий экран телефона или планшета). */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false;
    }
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** Ниже Tailwind `lg` (1024px): телефон и большинство планшетов в портрете. */
export const NARROW_VIEWPORT = "(max-width: 1023px)";
