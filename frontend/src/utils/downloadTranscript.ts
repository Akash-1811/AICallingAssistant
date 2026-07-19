import { authHeaders } from "../api/conversations";

type TranscriptSegment = {
  speaker_id: number;
  role: string;
  text: string;
  start_ms: number | null;
  end_ms: number | null;
};

function formatMmSs(ms: number | null | undefined): string {
  if (ms == null || ms < 0) return "";
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function roleLabel(seg: TranscriptSegment): string {
  const role = (seg.role || "").toLowerCase();
  if (role === "rep") return "Rep";
  if (role === "prospect") return "Customer";
  return `Speaker ${seg.speaker_id}`;
}

export async function downloadTranscriptTxt(conversationId: string): Promise<void> {
  const res = await fetch(`/api/v1/conversations/${conversationId}/transcript`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = (body as { detail?: string }).detail;
    throw new Error(detail || res.statusText || "Could not download transcript");
  }
  const data = (await res.json()) as { segments?: TranscriptSegment[] };
  const segments = Array.isArray(data.segments) ? data.segments : [];
  const lines = segments.map((seg) => {
    const t = formatMmSs(seg.start_ms);
    const who = roleLabel(seg);
    const text = (seg.text || "").trim();
    return [t ? `[${t}]` : "", `${who}:`, text].filter(Boolean).join(" ");
  });

  const content = lines.length ? lines.join("\n") : "No transcript segments saved for this call.";
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = `call_${conversationId.slice(0, 8)}_transcript.txt`;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

