/**
 * Tap and long-press on the same element, alongside a drag sensor.
 *
 * Three gestures share one name box, so the rules have to be unambiguous:
 *   - a press that ends before the timer, without moving, is a tap
 *   - a press that survives the timer without moving is a long press
 *   - movement past the slop radius cancels both and lets dnd-kit take over
 *
 * The caller drives the fill animation from `progress`, because a press that
 * fires with no warning feels like a misfire on a shared tablet.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export const LONG_PRESS_MS = 450;

/** Movement beyond this many pixels is a drag, not a press. Generous for sweaty hands. */
const SLOP_PX = 10;

interface Options {
  onTap: () => void;
  onLongPress: () => void;
  disabled?: boolean;
}

export function useLongPress({ onTap, onLongPress, disabled = false }: Options) {
  const [pressing, setPressing] = useState(false);
  const timer = useRef<number | null>(null);
  const origin = useRef<{ x: number; y: number } | null>(null);
  const fired = useRef(false);

  const clear = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
    origin.current = null;
    setPressing(false);
  }, []);

  // A press interrupted by unmount or by the tab going away must not fire later.
  useEffect(() => clear, [clear]);

  const onPointerDown = useCallback(
    (event: React.PointerEvent) => {
      if (disabled || event.button !== 0) return;
      fired.current = false;
      origin.current = { x: event.clientX, y: event.clientY };
      setPressing(true);
      timer.current = window.setTimeout(() => {
        fired.current = true;
        clear();
        // Confirm without a toast: on a propped-up tablet nobody is looking for one.
        navigator.vibrate?.(35);
        onLongPress();
      }, LONG_PRESS_MS);
    },
    [clear, disabled, onLongPress],
  );

  const onPointerMove = useCallback(
    (event: React.PointerEvent) => {
      const start = origin.current;
      if (!start) return;
      const moved = Math.hypot(event.clientX - start.x, event.clientY - start.y);
      if (moved > SLOP_PX) clear();
    },
    [clear],
  );

  const onPointerUp = useCallback(() => {
    const wasPressing = origin.current !== null;
    clear();
    if (wasPressing && !fired.current) onTap();
  }, [clear, onTap]);

  return {
    pressing,
    handlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel: clear,
      onPointerLeave: clear,
      // The browser's own long-press menu would fight ours.
      onContextMenu: (event: React.MouseEvent) => event.preventDefault(),
    },
  };
}
