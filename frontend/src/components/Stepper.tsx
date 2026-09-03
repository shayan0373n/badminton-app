/**
 * A small numeric control with big minus and plus targets.
 *
 * Setup happens with people waiting, so the values that move by a notch or two
 * are faster to nudge than to select-and-retype on a tablet keyboard.
 */

interface Props {
  value: number;
  onChange: (next: number) => void;
  min: number;
  max: number;
  step?: number;
  /** Names the value for the button labels, e.g. "courts". */
  label: string;
}

export function Stepper({ value, onChange, min, max, step = 1, label }: Props) {
  // Rounded because a half-step run would otherwise accumulate float dust.
  const nudge = (by: number) =>
    onChange(Number(Math.min(max, Math.max(min, value + by)).toFixed(2)));

  return (
    <div className="stepper">
      <button
        type="button"
        className="btn btn-icon"
        disabled={value <= min}
        onClick={() => nudge(-step)}
        aria-label={`Decrease ${label}`}
      >
        −
      </button>
      <output className="stepper-value">{value}</output>
      <button
        type="button"
        className="btn btn-icon"
        disabled={value >= max}
        onClick={() => nudge(step)}
        aria-label={`Increase ${label}`}
      >
        +
      </button>
    </div>
  );
}
