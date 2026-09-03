/**
 * One player's box on the check-in grid.
 *
 * Carries all three gestures: tap to check in or out, long press to check in
 * wanting a harder game, drag onto someone else to pair up. It is both a drag
 * source and a drop target, which is what makes "drag my name onto yours" work
 * without a separate drop zone to aim at.
 */

import { useDraggable, useDroppable } from "@dnd-kit/core";
import { useLongPress } from "../hooks/useLongPress";
import type { Candidate } from "../types";

const GROUP_COLORS = 6;

/** Stable colour per group so a group keeps its identity across re-renders. */
export function groupColor(group: string): string {
  let hash = 0;
  for (const char of group) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return `var(--group-${(hash % GROUP_COLORS) + 1})`;
}

interface Props {
  candidate: Candidate;
  onTap: () => void;
  onLongPress: () => void;
  draggable?: boolean;
}

export function NameBox({ candidate, onTap, onLongPress, draggable = true }: Props) {
  const { pressing, handlers } = useLongPress({ onTap, onLongPress });

  const canDrag = draggable && candidate.checked_in;
  const drag = useDraggable({ id: candidate.name, disabled: !canDrag });
  const drop = useDroppable({ id: candidate.name, disabled: !canDrag });

  const isDropTarget = drop.isOver && drag.active?.id !== candidate.name;

  const className = [
    "namebox",
    candidate.checked_in && "in",
    candidate.challenging && "challenging",
    candidate.group && "grouped",
    drag.isDragging && "dragging",
    isDropTarget && "drop-target",
  ]
    .filter(Boolean)
    .join(" ");

  const label = [
    candidate.name,
    candidate.checked_in ? "checked in" : "not here yet",
    candidate.challenging && "wants a stronger match",
    candidate.group && `paired, group ${candidate.group}`,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <button
      type="button"
      ref={(node) => {
        drag.setNodeRef(node);
        drop.setNodeRef(node);
      }}
      className={className}
      {...drag.attributes}
      {...drag.listeners}
      {...handlers}
      // After the spreads: dnd-kit sets its own aria-pressed for the drag
      // handle, and checked-in state is what a screen reader should hear.
      aria-label={label}
      aria-pressed={candidate.checked_in}
      onPointerDown={(event) => {
        drag.listeners?.onPointerDown?.(event);
        handlers.onPointerDown(event);
      }}
      onKeyDown={(event) => {
        // Keyboard equivalents: Enter toggles, Shift+Enter is the long press.
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          event.shiftKey ? onLongPress() : onTap();
        }
      }}
    >
      {pressing && <span className="press-fill" aria-hidden="true" />}
      {candidate.group && (
        <span
          className="group-stripe"
          style={{ background: groupColor(candidate.group) }}
          aria-hidden="true"
        />
      )}
      <span className="nb-name">{candidate.name}</span>
      <span className="nb-meta">
        {candidate.challenging && <span className="nb-challenge">Challenge</span>}
        {candidate.group && (
          <span
            className="group-tag"
            style={{ background: groupColor(candidate.group) }}
          >
            {candidate.group}
          </span>
        )}
        {!candidate.challenging && !candidate.group && (
          <span>{candidate.checked_in ? "Checked in" : "Tap to check in"}</span>
        )}
      </span>
    </button>
  );
}
