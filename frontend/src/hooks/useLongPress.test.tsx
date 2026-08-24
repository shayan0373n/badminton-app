/**
 * The gesture rules, which are what decide whether the check-in screen feels
 * right: a tap must never fire a challenge, and a drag must never fire either.
 */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { LONG_PRESS_MS, useLongPress } from "./useLongPress";

function Probe({ onTap, onLongPress }: { onTap: () => void; onLongPress: () => void }) {
  const { pressing, handlers } = useLongPress({ onTap, onLongPress });
  return (
    <button {...handlers} data-testid="target">
      {pressing ? "pressing" : "idle"}
    </button>
  );
}

const down = (el: Element, x = 0, y = 0) =>
  fireEvent.pointerDown(el, { button: 0, clientX: x, clientY: y });
const move = (el: Element, x: number, y: number) =>
  fireEvent.pointerMove(el, { clientX: x, clientY: y });

describe("useLongPress", () => {
  let onTap: ReturnType<typeof vi.fn>;
  let onLongPress: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    onTap = vi.fn();
    onLongPress = vi.fn();
  });

  afterEach(() => vi.useRealTimers());

  it("treats a quick press and release as a tap", () => {
    render(<Probe onTap={onTap} onLongPress={onLongPress} />);
    const target = screen.getByTestId("target");

    down(target);
    act(() => void vi.advanceTimersByTime(100));
    fireEvent.pointerUp(target);

    expect(onTap).toHaveBeenCalledTimes(1);
    expect(onLongPress).not.toHaveBeenCalled();
  });

  it("fires a long press once the timer elapses, without a tap", () => {
    render(<Probe onTap={onTap} onLongPress={onLongPress} />);
    const target = screen.getByTestId("target");

    down(target);
    act(() => void vi.advanceTimersByTime(LONG_PRESS_MS));

    expect(onLongPress).toHaveBeenCalledTimes(1);

    // Releasing afterwards must not also register a tap.
    fireEvent.pointerUp(target);
    expect(onTap).not.toHaveBeenCalled();
  });

  it("cancels both gestures once the pointer moves past the slop radius", () => {
    render(<Probe onTap={onTap} onLongPress={onLongPress} />);
    const target = screen.getByTestId("target");

    down(target, 0, 0);
    move(target, 40, 0);
    act(() => void vi.advanceTimersByTime(LONG_PRESS_MS * 2));
    fireEvent.pointerUp(target);

    expect(onTap).not.toHaveBeenCalled();
    expect(onLongPress).not.toHaveBeenCalled();
  });

  it("tolerates a small wobble during a press", () => {
    render(<Probe onTap={onTap} onLongPress={onLongPress} />);
    const target = screen.getByTestId("target");

    down(target, 0, 0);
    move(target, 4, 3); // 5px, inside the 10px slop
    act(() => void vi.advanceTimersByTime(LONG_PRESS_MS));

    expect(onLongPress).toHaveBeenCalledTimes(1);
  });

  it("reports pressing state so the fill can animate", () => {
    render(<Probe onTap={onTap} onLongPress={onLongPress} />);
    const target = screen.getByTestId("target");

    expect(target).toHaveTextContent("idle");
    down(target);
    expect(target).toHaveTextContent("pressing");

    act(() => void vi.advanceTimersByTime(LONG_PRESS_MS));
    expect(target).toHaveTextContent("idle");
  });

  it("cancels when the pointer leaves the box", () => {
    render(<Probe onTap={onTap} onLongPress={onLongPress} />);
    const target = screen.getByTestId("target");

    down(target);
    fireEvent.pointerLeave(target);
    act(() => void vi.advanceTimersByTime(LONG_PRESS_MS * 2));

    expect(onLongPress).not.toHaveBeenCalled();
    expect(onTap).not.toHaveBeenCalled();
  });

  it("ignores non-primary buttons", () => {
    render(<Probe onTap={onTap} onLongPress={onLongPress} />);
    const target = screen.getByTestId("target");

    fireEvent.pointerDown(target, { button: 2, clientX: 0, clientY: 0 });
    act(() => void vi.advanceTimersByTime(LONG_PRESS_MS * 2));
    fireEvent.pointerUp(target);

    expect(onTap).not.toHaveBeenCalled();
    expect(onLongPress).not.toHaveBeenCalled();
  });
});
