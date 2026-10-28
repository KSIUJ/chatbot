// Height of the auto-growing chat input. scrollHeight leaves the border out,
// and the textarea is border-box (Tailwind preflight), so without the border
// the box with text was 2px lower than the empty one (height: auto) and the
// field jumped while typing and deleting. Empty or not - the same formula.
export function inputHeight(scrollHeight: number, borders: number): number {
  return scrollHeight + Math.max(0, borders);
}
