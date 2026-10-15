/**
 * Tap and long-press on the same element, alongside a drag sensor.
 *
 * Three gestures share one name box, so the rules have to be unambiguous:
 *   - a press released before the timer, without moving, is a tap
 *   - a press held past the timer and released without moving is a long press
 *   - movement past the slop radius cancels both: before the timer it is a
 *     scroll, after it the drag sensor has taken over
 *
 * The long press fires on release rather than when the timer elapses, because
 * holding is also how a touch drag starts and the hold alone cannot tell which
 * one is meant.
 *
 * The caller drives the fill animation from `pressing`, because a press that
 * fires with no warning feels like a misfire on a shared tablet.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export const LONG_PRESS_MS = 450;

/** Movement beyond this many pixels is a scroll or drag, not a press. Generous for sweaty hands. */
export const SLOP_PX = 10;

interface Options {
  onTap: () => void;
  onLongPress: () => void;
  disabled?: boolean;
}

export function useLongPress({ onTap, onLongPress, disabled = false }: Options) {
  const [pressing, setPressing] = useState(false);
  const timer = useRef<number | null>(null);
  const origin = useRef<{ x: number; y: number } | null>(null);
  const held = useRef(false);

  const clear = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
    origin.current = null;
    held.current = false;
    setPressing(false);
  }, []);

  // A press interrupted by unmount or by the tab going away must not fire later.
  useEffect(() => clear, [clear]);

  const onPointerDown = useCallback(
    (event: React.PointerEvent) => {
      if (disabled || event.button !== 0) return;
      held.current = false;
      origin.current = { x: event.clientX, y: event.clientY };
      setPressing(true);
      timer.current = window.setTimeout(() => {
        timer.current = null;
        held.current = true;
        // Confirm without a toast: on a propped-up tablet nobody is looking for one.
        navigator.vibrate?.(35);
      }, LONG_PRESS_MS);
    },
    [disabled],
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

  const onPointerUp = useCallback(
    (event: React.PointerEvent) => {
      const start = origin.current;
      const wasHeld = held.current;
      clear();
      if (!start) return;
      // A drag may end here without the moves having reached this element.
      if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > SLOP_PX) return;
      if (wasHeld) onLongPress();
      else onTap();
    },
    [clear, onTap, onLongPress],
  );

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
