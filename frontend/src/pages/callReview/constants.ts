export type ReviewTab = "intent" | "coaching" | "highlights" | "transcript";

export const REVIEW_TABS: { id: ReviewTab; label: string }[] = [
  { id: "intent", label: "Client intent" },
  { id: "coaching", label: "Coaching" },
  { id: "highlights", label: "Highlights" },
  { id: "transcript", label: "Transcript" },
];

/** Measured timeline series computed by the backend from transcript timestamps. */
export type CurveKey = "prospect_talk" | "prospect_questions" | "objections";

export const CURVE_OPTIONS: { value: CurveKey; label: string }[] = [
  { value: "prospect_talk", label: "Prospect talk share" },
  { value: "prospect_questions", label: "Prospect questions" },
  { value: "objections", label: "Objection intensity" },
];

export const PHASE_KEYS = ["opening", "middle", "closing"] as const;
export const PHASE_LABELS = ["Start of call", "Middle of call", "End of call"] as const;

export const GLANCE_ROWS = [
  { label: "Total call time", key: "durationLabel" as const },
  { label: "Talk time (Rep)", key: "repPct" as const, suffix: "%", subKey: "repTalkLabel" as const },
  { label: "Talk time (Prospect)", key: "prospectPct" as const, suffix: "%", subKey: "prospectTalkLabel" as const },
  { label: "Key questions asked", key: "questions" as const },
];
