export function statusLabel(status: string): string {
  if (status === "ready") return "Analysis ready";
  if (status === "analyzing" || status === "running") return "Analyzing…";
  if (status === "failed") return "Analysis failed";
  if (status === "live") return "Live";
  return status;
}

export function dueTone(hint: string): "urgent" | "scheduled" | "default" {
  const h = hint.toLowerCase();
  if (h.includes("today") || h.includes("asap") || h.includes("now")) return "urgent";
  if (h.includes("saturday") || h.includes("sunday") || /\d{1,2}\s*(am|pm)/i.test(h)) return "scheduled";
  return "default";
}

export function ownerKind(owner: string): "rep" | "prospect" | "other" {
  const o = owner.toLowerCase();
  if (o.includes("rep") || o.includes("sales") || o.includes("agent")) return "rep";
  if (o.includes("prospect") || o.includes("client") || o.includes("lead") || o.includes("customer")) {
    return "prospect";
  }
  return "other";
}
