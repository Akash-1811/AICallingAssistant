import styles from "../CallReviewPage.module.css";
import { asString } from "./json";
import { dueTone, ownerKind } from "./utils";

// ── SVG geometry (rendering only — data series come from the server) ─────────

const PHASE_CHART_LABELS = ["Start", "Early", "Mid", "Late", "End"] as const;

type PhasePoint = { label: string; score: number };

function buildPhaseSeries(values: number[]): PhasePoint[] {
  return PHASE_CHART_LABELS.map((label, index) => ({
    label,
    score: values[Math.min(index, Math.max(values.length - 1, 0))] ?? 0,
  }));
}

function buildSmoothLinePath(points: { x: number; y: number }[], tension = 0.38): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  if (points.length === 2) {
    return `M ${points[0].x} ${points[0].y} L ${points[1].x} ${points[1].y}`;
  }
  let path = `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`;
  for (let index = 0; index < points.length - 1; index += 1) {
    const p0 = points[Math.max(0, index - 1)];
    const p1 = points[index];
    const p2 = points[index + 1];
    const p3 = points[Math.min(points.length - 1, index + 2)];
    const cp1x = p1.x + ((p2.x - p0.x) / 6) * tension;
    const cp1y = p1.y + ((p2.y - p0.y) / 6) * tension;
    const cp2x = p2.x - ((p3.x - p1.x) / 6) * tension;
    const cp2y = p2.y - ((p3.y - p1.y) / 6) * tension;
    path += ` C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`;
  }
  return path;
}

type ScoreRingProps = {
  value: number;
  label: string;
  sublabel?: string;
  size?: number;
  tone?: "accent" | "teal" | "amber";
};

export function ScoreRing({ value, label, sublabel, size = 120, tone = "accent" }: ScoreRingProps) {
  const clamped = Math.min(100, Math.max(0, value));
  const stroke = 10;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (clamped / 100) * circumference;
  const toneClass =
    tone === "teal" ? styles.ringTeal : tone === "amber" ? styles.ringAmber : styles.ringAccent;

  return (
    <div className={styles.scoreRingWrap}>
      <svg width={size} height={size} className={styles.scoreRingSvg} aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--surface-3)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          className={toneClass}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className={styles.scoreRingCenter}>
        <span className={styles.scoreRingValue}>{Math.round(clamped)}</span>
        <span className={styles.scoreRingUnit}>%</span>
      </div>
      <p className={styles.scoreRingLabel}>{label}</p>
      {sublabel ? <p className={styles.scoreRingSub}>{sublabel}</p> : null}
    </div>
  );
}

export function TalkListenDonut({ repPct, prospectPct }: { repPct: number; prospectPct: number }) {
  const total = Math.max(repPct + prospectPct, 1);
  const rep = (repPct / total) * 100;
  const prospect = (prospectPct / total) * 100;
  const size = 140;
  const stroke = 22;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const repLen = (rep / 100) * circumference;
  const prospectLen = (prospect / 100) * circumference;

  return (
    <div className={styles.donutWrap}>
      <svg width={size} height={size} aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--surface-3)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={stroke}
          strokeDasharray={`${repLen} ${circumference}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--teal)"
          strokeWidth={stroke}
          strokeDasharray={`${prospectLen} ${circumference}`}
          strokeDashoffset={-repLen}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className={styles.donutLegend}>
        <span>
          <i className={styles.legendDotAccent} /> Rep {Math.round(rep)}%
        </span>
        <span>
          <i className={styles.legendDotTeal} /> Prospect {Math.round(prospect)}%
        </span>
      </div>
    </div>
  );
}

export function CallPhaseList({
  phases,
}: {
  phases: { label: string; score: number; note: string; quote: string }[];
}) {
  return (
    <div className={styles.callPhaseList}>
      {phases.map((phase) => (
        <article key={phase.label} className={styles.callPhaseCard}>
          <div className={styles.callPhaseHead}>
            <span className={styles.callPhaseLabel}>{phase.label}</span>
            <strong className={styles.callPhaseScore}>{phase.score}/100</strong>
          </div>
          <div className={styles.callPhaseTrack}>
            <div
              className={styles.callPhaseFill}
              style={{ width: `${Math.min(100, Math.max(0, phase.score))}%` }}
            />
          </div>
          {phase.note ? <p className={styles.callPhaseNote}>{phase.note}</p> : null}
          {phase.quote ? (
            <p className={styles.callPhaseNote}>
              <em>“{phase.quote}”</em>
            </p>
          ) : null}
        </article>
      ))}
    </div>
  );
}

export function MiniTrendChart({
  values,
  color = "accent",
  label,
  spikeIndices = [],
  variant = "default",
}: {
  values: number[];
  color?: "accent" | "teal" | "amber";
  label?: string;
  spikeIndices?: number[];
  variant?: "default" | "kpi";
}) {
  const w = 280;
  const h = 112;
  const padX = variant === "kpi" ? 4 : 8;
  const padY = variant === "kpi" ? 6 : 12;
  const colorVar = color === "teal" ? "var(--teal)" : color === "amber" ? "var(--amber)" : "var(--accent)";
  const gradId = `trend-${color}-${values.join("-").slice(0, 12)}`;
  const fillTop = variant === "kpi" ? 0.22 : 0.35;
  const fillBottom = variant === "kpi" ? 0.02 : 0.03;
  const strokeWidth = variant === "kpi" ? 2 : 2.25;

  const pts = values.map((v, i) => {
    const x = padX + (i / Math.max(values.length - 1, 1)) * (w - padX * 2);
    const y = padY + (1 - v / 100) * (h - padY * 2);
    return { x, y, v };
  });
  if (pts.length < 2) return null;

  const linePath = buildSmoothLinePath(pts);
  const areaPath = `${linePath} L ${pts[pts.length - 1].x} ${h - padY} L ${pts[0].x} ${h - padY} Z`;

  return (
    <div className={styles.trendChartWrap}>
      <svg viewBox={`0 0 ${w} ${h}`} className={styles.trendChart} preserveAspectRatio="none" aria-hidden>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colorVar} stopOpacity={fillTop} />
            <stop offset="100%" stopColor={colorVar} stopOpacity={fillBottom} />
          </linearGradient>
        </defs>
        {[25, 50, 75].map((g) => (
          <line
            key={g}
            x1={padX}
            x2={w - padX}
            y1={padY + (1 - g / 100) * (h - padY * 2)}
            y2={padY + (1 - g / 100) * (h - padY * 2)}
            stroke="var(--sep)"
            strokeWidth="1"
            strokeDasharray={variant === "kpi" ? "2 5" : "3 4"}
            opacity={variant === "kpi" ? 0.45 : 0.7}
          />
        ))}
        <path d={areaPath} fill={`url(#${gradId})`} />
        <path
          d={linePath}
          fill="none"
          stroke={colorVar}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {variant !== "kpi"
          ? pts.map((p, i) => {
              const isSpike = spikeIndices.includes(i);
              const show = isSpike || i === 0 || i === pts.length - 1 || i === Math.floor(pts.length / 2);
              if (!show) return null;
              return (
                <circle
                  key={i}
                  cx={p.x}
                  cy={p.y}
                  r={isSpike ? 4.5 : 3.5}
                  fill={isSpike ? "var(--red)" : "var(--surface)"}
                  stroke={isSpike ? "var(--red)" : colorVar}
                  strokeWidth="2"
                />
              );
            })
          : spikeIndices.map((i) => {
              const p = pts[i];
              if (!p) return null;
              return (
                <circle
                  key={i}
                  cx={p.x}
                  cy={p.y}
                  r={3.5}
                  fill="var(--red)"
                  stroke="var(--red)"
                  strokeWidth="1.5"
                />
              );
            })}
      </svg>
      {label ? <span className={styles.trendChartCaption}>{label}</span> : null}
    </div>
  );
}

export function KpiPhaseChart({
  values,
  color = "accent",
  label,
  spikePhases = [],
}: {
  values: number[];
  color?: "accent" | "teal" | "amber";
  label?: string;
  spikePhases?: number[];
}) {
  const phases = buildPhaseSeries(values);
  const w = 300;
  const plotH = 96;
  const padX = 10;
  const padTop = 10;
  const labelY = plotH + 18;
  const barGap = 10;
  const barWidth = (w - padX * 2 - barGap * (phases.length - 1)) / phases.length;
  const colorVar = color === "teal" ? "var(--teal)" : color === "amber" ? "var(--amber)" : "var(--accent)";
  const gradId = `phase-${color}-${phases.map((phase) => phase.score).join("-")}`;

  return (
    <div className={styles.phaseChartWrap}>
      <svg viewBox={`0 0 ${w} ${plotH + 24}`} className={styles.phaseChart} aria-hidden>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colorVar} stopOpacity="0.95" />
            <stop offset="100%" stopColor={colorVar} stopOpacity="0.28" />
          </linearGradient>
        </defs>
        {[25, 50, 75].map((grid) => {
          const y = padTop + (1 - grid / 100) * (plotH - padTop);
          return (
            <line
              key={grid}
              x1={padX}
              x2={w - padX}
              y1={y}
              y2={y}
              stroke="var(--sep)"
              strokeWidth="1"
              strokeDasharray="3 5"
              opacity="0.55"
            />
          );
        })}
        <line x1={padX} x2={w - padX} y1={plotH} y2={plotH} stroke="var(--border)" strokeWidth="1" opacity="0.8" />
        {phases.map((phase, index) => {
          const height = Math.max(6, ((phase.score / 100) * (plotH - padTop)));
          const x = padX + index * (barWidth + barGap);
          const y = plotH - height;
          const isSpike = spikePhases.includes(index);
          return (
            <g key={phase.label}>
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={height}
                rx={5}
                fill={`url(#${gradId})`}
                opacity={isSpike ? 0.72 : 0.92}
              />
              {isSpike ? (
                <circle cx={x + barWidth / 2} cy={y - 4} r={3.5} fill="var(--red)" stroke="var(--surface)" strokeWidth="1.5" />
              ) : null}
              <text
                x={x + barWidth / 2}
                y={labelY}
                textAnchor="middle"
                className={styles.phaseChartLabelSvg}
              >
                {phase.label}
              </text>
            </g>
          );
        })}
      </svg>
      {label ? <span className={styles.phaseChartCaption}>{label}</span> : null}
    </div>
  );
}

export function KpiCard({
  label,
  value,
  unit = "",
  badge,
  badgeTone = "mid",
  timeline,
  chartColor = "accent",
  chartCaption,
  spikeIndices,
}: {
  label: string;
  value: number;
  unit?: string;
  badge?: string;
  badgeTone?: "high" | "mid" | "low";
  timeline: number[];
  chartColor?: "accent" | "teal" | "amber";
  chartCaption?: string;
  spikeIndices?: number[];
}) {
  const tone =
    badgeTone === "high" ? styles.kpiBadgeGood : badgeTone === "low" ? styles.kpiBadgeLow : styles.kpiBadgeMid;
  const strokeTone =
    chartColor === "teal" ? styles.kpiAccentTeal : chartColor === "amber" ? styles.kpiAccentAmber : styles.kpiAccentOrange;

  return (
    <article className={`${styles.kpiCard} ${strokeTone}`}>
      <div className={styles.kpiHeader}>
        <div className={styles.kpiHeaderMain}>
          <span className={styles.kpiLabel}>{label}</span>
          <div className={styles.kpiScoreRow}>
            <span className={styles.kpiValue}>{Math.round(value)}</span>
            {unit ? <span className={styles.kpiOf}>{unit}</span> : null}
          </div>
        </div>
        {badge ? <span className={`${styles.kpiBadge} ${tone}`}>{badge}</span> : null}
      </div>
      <div className={styles.kpiChartZone}>
        <KpiPhaseChart
          values={timeline}
          color={chartColor}
          label={chartCaption}
          spikePhases={spikeIndices ?? []}
        />
      </div>
    </article>
  );
}

type NextStepRow = { owner: string; action: string; due_hint: string };

export function NextStepsPanel({ steps }: { steps: Array<Record<string, unknown>> }) {
  const parsed: NextStepRow[] = steps.map((s) => ({
    owner: asString(s.owner, "team"),
    action: asString(s.action),
    due_hint: asString(s.due_hint),
  }));

  const repSteps = parsed.filter((s) => ownerKind(s.owner) === "rep");
  const prospectSteps = parsed.filter((s) => ownerKind(s.owner) === "prospect");
  const otherSteps = parsed.filter((s) => ownerKind(s.owner) === "other");

  function renderColumn(title: string, subtitle: string, items: NextStepRow[], kind: "rep" | "prospect" | "other") {
    if (items.length === 0) return null;
    const colClass =
      kind === "rep" ? styles.nextColRep : kind === "prospect" ? styles.nextColProspect : styles.nextColOther;

    return (
      <div className={`${styles.nextColumn} ${colClass}`}>
        <div className={styles.nextColumnHead}>
          <div className={styles.nextColumnTitle}>
            <h3>{title}</h3>
            <p>{subtitle}</p>
          </div>
          <span className={styles.nextColumnCount}>
            {items.length} {items.length === 1 ? "task" : "tasks"}
          </span>
        </div>
        <ul className={styles.nextList}>
          {items.map((step, i) => (
            <li key={`${kind}-${i}`} className={styles.nextStepItem}>
              <span className={styles.nextStepCheck} aria-hidden />
              <div className={styles.nextStepBody}>
                <p>{step.action}</p>
                {step.due_hint ? (
                  <span className={`${styles.nextDuePill} ${styles[`due_${dueTone(step.due_hint)}`]}`}>
                    {step.due_hint}
                  </span>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  const repShare = parsed.length > 0 ? Math.round((repSteps.length / parsed.length) * 100) : 0;
  const prospectShare = parsed.length > 0 ? Math.round((prospectSteps.length / parsed.length) * 100) : 0;

  return (
    <section className={styles.nextStepsSection} aria-label="Next steps">
      <header className={styles.nextStepsHeader}>
        <div className={styles.nextStepsHeaderText}>
          <h2>Next steps</h2>
          <p>Follow-ups to move this deal forward</p>
        </div>
        <div className={styles.nextStepsMeta}>
          <span className={styles.nextMetaChip}>
            <strong>{parsed.length}</strong> action items
          </span>
        </div>
      </header>

      <div className={styles.nextProgressTrack} aria-hidden>
        {repShare > 0 ? (
          <div className={styles.nextProgressRep} style={{ width: `${repShare}%` }} title={`${repShare}% rep`} />
        ) : null}
        {prospectShare > 0 ? (
          <div
            className={styles.nextProgressProspect}
            style={{ width: `${prospectShare}%` }}
            title={`${prospectShare}% prospect`}
          />
        ) : null}
      </div>
      <div className={styles.nextProgressLegend}>
        {repSteps.length > 0 ? <span className={styles.nextLegendRep}>Rep · {repSteps.length}</span> : null}
        {prospectSteps.length > 0 ? (
          <span className={styles.nextLegendProspect}>Prospect · {prospectSteps.length}</span>
        ) : null}
      </div>

      <div className={styles.nextStepsBoard}>
        {renderColumn("Sales rep", "Your follow-ups", repSteps, "rep")}
        {renderColumn("Prospect", "Client commitments", prospectSteps, "prospect")}
        {renderColumn("Shared", "Other actions", otherSteps, "other")}
      </div>
    </section>
  );
}
