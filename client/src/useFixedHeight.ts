import { useEffect, useRef } from "react";

/** Reserve the actual height of fixed controls, including enlarged/wrapped text. */
export function useFixedHeight(property: string, enabled = true) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node || !enabled) return;
    const measure = () => {
      document.documentElement.style.setProperty(
        property,
        `${node.getBoundingClientRect().height}px`,
      );
    };
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    measure();
    return () => {
      observer.disconnect();
      document.documentElement.style.removeProperty(property);
    };
  }, [property, enabled]);
  return ref;
}
