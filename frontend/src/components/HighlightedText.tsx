import { memo, useMemo, type ReactNode } from "react";
import styles from "./HighlightedText.module.css";

/**
 * Matches typical "value" fragments in assistant text: ranges, comma numbers,
 * decimals, 3+ digit numbers, and N BHK. Pure string scan — O(n) per render.
 */
const VALUE_RE =
  /\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:to|–|—|-)\s*\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\b\d{3,}\b|\dBHK/g;

function stripBoldMarkers(s: string): string {
  return s.replace(/\*\*/g, "");
}

function splitWithHighlights(text: string, markClassName: string): ReactNode[] {
  const plain = stripBoldMarkers(text);
  const out: React.ReactNode[] = [];
  let last = 0;
  let key = 0;
  const re = new RegExp(VALUE_RE.source, "g");
  let m: RegExpExecArray | null;
  while ((m = re.exec(plain)) !== null) {
    if (m.index > last) {
      out.push(plain.slice(last, m.index));
    }
    out.push(
      <mark key={`v-${key++}`} className={markClassName}>
        {m[0]}
      </mark>
    );
    last = m.index + m[0].length;
  }
  if (last < plain.length) {
    out.push(plain.slice(last));
  }
  return out.length ? out : [plain];
}

interface Props {
  text: string;
  className?: string;
  /** Use on accent/dark bubbles so value highlights stay readable (default marks use accent text color). */
  variant?: "default" | "onAccent";
  /** When set (e.g. Picture-in-Picture window with its own stylesheet), overrides module mark classes. */
  markClassName?: string;
}

export const HighlightedText = memo(function HighlightedText({
  text,
  className,
  variant = "default",
  markClassName,
}: Props) {
  const markClass =
    markClassName ?? (variant === "onAccent" ? styles.valueMarkOnAccent : styles.valueMark);
  const nodes = useMemo(() => splitWithHighlights(text, markClass), [text, markClass]);
  return <span className={className}>{nodes}</span>;
});
