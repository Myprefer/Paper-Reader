import { useCallback, useRef } from 'react';

/**
 * Long-press hook for mobile: triggers callback after holding for `ms` milliseconds.
 * Automatically cancels if the finger moves more than 10px (scrolling).
 *
 * Usage:
 *   const lp = useLongPress((x, y) => showContextMenu(x, y, ...));
 *   <div {...lp.bindTouchProps()} onClick={e => { if (lp.cancelClick()) return; ... }} />
 */
export function useLongPress(
  onLongPress: (x: number, y: number) => void,
  ms = 500,
) {
  const timerRef = useRef<number>(0);
  const triggeredRef = useRef(false);
  const startRef = useRef<{ x: number; y: number } | null>(null);

  const onTouchStart = useCallback(
    (e: React.TouchEvent) => {
      triggeredRef.current = false;
      const { clientX, clientY } = e.touches[0];
      startRef.current = { x: clientX, y: clientY };
      timerRef.current = window.setTimeout(() => {
        triggeredRef.current = true;
        onLongPress(clientX, clientY);
      }, ms);
    },
    [onLongPress, ms],
  );

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    if (!startRef.current) return;
    const dx = Math.abs(e.touches[0].clientX - startRef.current.x);
    const dy = Math.abs(e.touches[0].clientY - startRef.current.y);
    if (dx > 10 || dy > 10) {
      clearTimeout(timerRef.current);
      startRef.current = null;
    }
  }, []);

  const onTouchEnd = useCallback(() => {
    clearTimeout(timerRef.current);
    startRef.current = null;
  }, []);

  /** Call at the start of onClick to suppress click after long press. Returns true if click should be cancelled. */
  const cancelClick = useCallback(() => {
    if (triggeredRef.current) {
      triggeredRef.current = false;
      return true;
    }
    return false;
  }, []);

  /** Spread onto the target element: <div {...lp.bindTouchProps()} /> */
  const bindTouchProps = useCallback(
    () => ({ onTouchStart, onTouchMove, onTouchEnd }),
    [onTouchStart, onTouchMove, onTouchEnd],
  );

  return { onTouchStart, onTouchMove, onTouchEnd, cancelClick, bindTouchProps };
}
