import { useState } from "react";

import type { Schemas } from "../api/client";
import { useT, type StringKey } from "../strings";
import { venueHM } from "../venueTime";

type Hour = Schemas["ActivityHour"];
type Key = "received" | "requested" | "delivered";

// Validated with the dataviz palette script (light surface, all pairs): lightness, chroma, CVD and contrast pass.
const SERIES: { key: Key; color: string; label: StringKey }[] = [
  { key: "received", color: "#C2489A", label: "actReceived" },
  { key: "requested", color: "#62429B", label: "actRequested" },
  { key: "delivered", color: "#B47A1E", label: "actDelivered" },
];

const W = 640;
const H = 196;
const PAD = { top: 14, right: 40, bottom: 26, left: 30 };

/** Cars received, requests and deliveries per hour, from recorded times. A trend needs at least two hours; until
 *  then the dashboard says so instead of drawing a line. Time runs left to right in both languages. */
export function ActivityChart({ hours, zone }: { hours: Hour[]; zone: string }) {
  const { t, lang } = useT();
  const [active, setActive] = useState<number | null>(null);
  if (hours.length < 2) return <p className="empty" data-testid="activity-empty">{t("activityTooLittle")}</p>;

  const max = Math.max(1, ...hours.flatMap((h) => SERIES.map((s) => h[s.key])));
  const top = max <= 4 ? max : Math.ceil(max / 2) * 2;
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (i * plotW) / (hours.length - 1);
  const y = (v: number) => PAD.top + plotH - (v / top) * plotH;
  const label = (h: Hour) => venueHM(h.hour, lang, zone);
  const every = Math.ceil(hours.length / 8);
  const ticks = top <= 1 ? [0, 1] : [0, Math.round(top / 2), top];
  // End labels: the last value of each series, nudged apart so they never overlap.
  const ends = SERIES.map((s) => ({ ...s, value: hours[hours.length - 1][s.key], y: y(hours[hours.length - 1][s.key]) }))
    .sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i += 1) ends[i].y = Math.max(ends[i].y, ends[i - 1].y + 14);
  const shown = active ?? null;

  return (
    <figure className="activity-chart" data-testid="activity-chart">
      <ul className="legend" aria-hidden="true">
        {SERIES.map((s) => <li key={s.key}><span className="swatch" style={{ background: s.color }} /> {t(s.label)}</li>)}
      </ul>
      <div className="chart-area" onMouseLeave={() => setActive(null)}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("activityTitle")} direction="ltr">
          {ticks.map((v) => (
            <g key={v} className="grid">
              <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} />
              <text x={PAD.left - 6} y={y(v) + 4} textAnchor="end">{v}</text>
            </g>
          ))}
          {hours.map((h, i) => (i % every === 0 || i === hours.length - 1 ? (
            <text key={h.hour} className="axis" x={x(i)} y={H - 6} textAnchor="middle">{label(h)}</text>
          ) : null))}
          {shown !== null ? <line className="crosshair" x1={x(shown)} x2={x(shown)} y1={PAD.top} y2={PAD.top + plotH} /> : null}
          {SERIES.map((s) => (
            <g key={s.key}>
              <polyline fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round"
                points={hours.map((h, i) => `${x(i)},${y(h[s.key])}`).join(" ")} />
              {hours.map((h, i) => (
                <circle key={h.hour} cx={x(i)} cy={y(h[s.key])} r={shown === i ? 5 : 3.5} fill={s.color}
                  stroke="#FFFFFF" strokeWidth={2} />
              ))}
            </g>
          ))}
          {ends.map((e) => (
            <g key={e.key} className="end-label">
              <circle cx={W - PAD.right + 8} cy={e.y} r={3.5} fill={e.color} />
              <text x={W - PAD.right + 15} y={e.y + 4}>{e.value}</text>
            </g>
          ))}
          {hours.map((h, i) => (
            <rect key={h.hour} className="hit" x={x(i) - plotW / (hours.length - 1) / 2} y={PAD.top}
              width={plotW / (hours.length - 1)} height={plotH} tabIndex={0}
              aria-label={`${label(h)}: ${SERIES.map((s) => `${t(s.label)} ${h[s.key]}`).join("، ")}`}
              onMouseEnter={() => setActive(i)} onFocus={() => setActive(i)} onBlur={() => setActive(null)} />
          ))}
        </svg>
        {shown !== null ? (
          <div className="chart-tip" role="status" style={{ left: `${(x(shown) / W) * 100}%` }}>
            <strong dir="ltr">{label(hours[shown])}</strong>
            {SERIES.map((s) => (
              <span key={s.key}><span className="swatch" style={{ background: s.color }} /> {t(s.label)}{" "}
                <b className="sl-identifier">{hours[shown][s.key]}</b></span>
            ))}
          </div>
        ) : null}
      </div>
      <details className="chart-table">
        <summary>{t("showAsTable")}</summary>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th scope="col">{t("actHour")}</th>{SERIES.map((s) => <th key={s.key} scope="col">{t(s.label)}</th>)}</tr></thead>
            <tbody>{hours.map((h) => (
              <tr key={h.hour}><th scope="row" dir="ltr">{label(h)}</th>{SERIES.map((s) => <td key={s.key}>{h[s.key]}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
