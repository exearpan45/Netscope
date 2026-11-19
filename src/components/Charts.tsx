import { useState } from 'react';
import type { SpeedPoint } from '../types';
import { formatBytes, formatSpeed, formatTimeShort } from '../utils/format';

interface SpeedChartProps {
  series: SpeedPoint[];
  height?: number;
}

export function LiveSpeedChart({ series, height = 240 }: SpeedChartProps) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  if (series.length < 2) {
    return (
      <div
        className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-200 dark:border-slate-800 text-center px-6"
        style={{ height }}
      >
        <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
          Collecting initial kernel counter baseline
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          Real-time download and upload rates from /proc/net/dev will appear after two sampling ticks.
        </p>
      </div>
    );
  }

  const width = 760;
  const padL = 68;
  const padR = 16;
  const padT = 16;
  const padB = 28;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const maxRate = Math.max(
    1024,
    ...series.map((p) => Math.max(p.rx_rate_bps, p.tx_rate_bps))
  );

  const xFor = (i: number) =>
    padL + (i / Math.max(1, series.length - 1)) * plotW;
  const yFor = (val: number) =>
    padT + plotH - (Math.min(val, maxRate) / maxRate) * plotH;

  const rxPath = series
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${xFor(i).toFixed(1)},${yFor(p.rx_rate_bps).toFixed(1)}`)
    .join(' ');
  const rxArea = `${rxPath} L${xFor(series.length - 1).toFixed(1)},${(padT + plotH).toFixed(1)} L${padL},${(padT + plotH).toFixed(1)} Z`;

  const txPath = series
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${xFor(i).toFixed(1)},${yFor(p.tx_rate_bps).toFixed(1)}`)
    .join(' ');

  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const hovered = hoverIdx !== null ? series[hoverIdx] : null;

  return (
    <div className="relative w-full">
      {hovered && (
        <div className="mb-2 flex flex-wrap items-center gap-4 text-xs font-mono text-slate-600 dark:text-slate-300">
          <span>{formatTimeShort(hovered.ts_utc)}</span>
          <span className="text-sky-600 dark:text-sky-400">
            Download: {formatSpeed(hovered.rx_rate_bps)}
          </span>
          <span className="text-emerald-600 dark:text-emerald-400">
            Upload: {formatSpeed(hovered.tx_rate_bps)}
          </span>
        </div>
      )}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto overflow-visible select-none"
        onMouseLeave={() => setHoverIdx(null)}
      >
        <defs>
          <linearGradient id="netscopeRxGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0284c7" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#0284c7" stopOpacity="0.01" />
          </linearGradient>
        </defs>

        {ticks.map((t) => {
          const y = padT + plotH * (1 - t);
          return (
            <g key={t}>
              <line
                x1={padL}
                y1={y}
                x2={width - padR}
                y2={y}
                className="stroke-slate-200 dark:stroke-slate-800"
                strokeWidth="1"
              />
              <text
                x={padL - 8}
                y={y + 3}
                textAnchor="end"
                className="fill-slate-400 dark:fill-slate-500 text-[10px] font-mono"
              >
                {formatSpeed(maxRate * t)}
              </text>
            </g>
          );
        })}

        <path d={rxArea} fill="url(#netscopeRxGrad)" />
        <path
          d={rxPath}
          fill="none"
          stroke="#0284c7"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        <path
          d={txPath}
          fill="none"
          stroke="#059669"
          strokeWidth="1.75"
          strokeLinejoin="round"
        />

        {/* X axis labels */}
        {[0, Math.floor(series.length / 2), series.length - 1].map((idx) => (
          <text
            key={idx}
            x={xFor(idx)}
            y={height - 6}
            textAnchor={idx === 0 ? 'start' : idx === series.length - 1 ? 'end' : 'middle'}
            className="fill-slate-400 dark:fill-slate-500 text-[10px] font-mono"
          >
            {formatTimeShort(series[idx]?.ts_utc)}
          </text>
        ))}

        {/* Interactive hover vertical marker */}
        {hoverIdx !== null && (
          <>
            <line
              x1={xFor(hoverIdx)}
              y1={padT}
              x2={xFor(hoverIdx)}
              y2={padT + plotH}
              className="stroke-slate-400 dark:stroke-slate-600"
              strokeDasharray="3 3"
              strokeWidth="1"
            />
            <circle
              cx={xFor(hoverIdx)}
              cy={yFor(series[hoverIdx].rx_rate_bps)}
              r="4"
              fill="#0284c7"
            />
            <circle
              cx={xFor(hoverIdx)}
              cy={yFor(series[hoverIdx].tx_rate_bps)}
              r="3.5"
              fill="#059669"
            />
          </>
        )}

        {/* Transparent hover columns */}
        {series.map((_, i) => {
          const step = plotW / Math.max(1, series.length - 1);
          return (
            <rect
              key={i}
              x={xFor(i) - step / 2}
              y={padT}
              width={Math.max(4, step)}
              height={plotH}
              fill="transparent"
              onMouseEnter={() => setHoverIdx(i)}
            />
          );
        })}
      </svg>
    </div>
  );
}

interface PeriodBarItem {
  local_date: string;
  rx_bytes: number;
  tx_bytes: number;
  total_bytes: number;
}

export function PeriodUsageChart({
  series,
  height = 220,
}: {
  series: PeriodBarItem[];
  height?: number;
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  if (!series || series.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-200 dark:border-slate-800 text-center px-6"
        style={{ height }}
      >
        <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
          No recorded interface traffic in this period
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          NETSCOPE only charts genuine measurements stored in SQLite. Select a different range or allow live monitoring to accumulate records.
        </p>
      </div>
    );
  }

  const width = 760;
  const padL = 68;
  const padR = 16;
  const padT = 14;
  const padB = 30;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  const maxTotal = Math.max(1024, ...series.map((d) => d.total_bytes));
  const barSlot = plotW / series.length;
  const barW = Math.max(6, Math.min(34, barSlot * 0.62));
  const hovered = hoverIdx !== null ? series[hoverIdx] : null;

  return (
    <div className="w-full">
      {hovered && (
        <div className="mb-2 flex flex-wrap items-center gap-4 text-xs font-mono text-slate-600 dark:text-slate-300">
          <span>{hovered.local_date}</span>
          <span className="text-sky-600 dark:text-sky-400">
            DL: {formatBytes(hovered.rx_bytes)}
          </span>
          <span className="text-emerald-600 dark:text-emerald-400">
            UL: {formatBytes(hovered.tx_bytes)}
          </span>
          <span>Total: {formatBytes(hovered.total_bytes)}</span>
        </div>
      )}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto overflow-visible select-none"
        onMouseLeave={() => setHoverIdx(null)}
      >
        {[0, 0.5, 1].map((t) => {
          const y = padT + plotH * (1 - t);
          return (
            <g key={t}>
              <line
                x1={padL}
                y1={y}
                x2={width - padR}
                y2={y}
                className="stroke-slate-200 dark:stroke-slate-800"
                strokeWidth="1"
              />
              <text
                x={padL - 8}
                y={y + 3}
                textAnchor="end"
                className="fill-slate-400 dark:fill-slate-500 text-[10px] font-mono"
              >
                {formatBytes(maxTotal * t)}
              </text>
            </g>
          );
        })}

        {series.map((d, i) => {
          const cx = padL + i * barSlot + barSlot / 2;
          const rxH = (d.rx_bytes / maxTotal) * plotH;
          const txH = (d.tx_bytes / maxTotal) * plotH;
          const rxY = padT + plotH - rxH - txH;
          const txY = padT + plotH - txH;
          const showLabel =
            series.length <= 10 || i === 0 || i === series.length - 1 || i % Math.ceil(series.length / 6) === 0;

          return (
            <g
              key={d.local_date}
              onMouseEnter={() => setHoverIdx(i)}
              className="cursor-pointer"
            >
              <rect
                x={cx - barW / 2}
                y={rxY}
                width={barW}
                height={Math.max(1, rxH)}
                rx="2"
                fill={hoverIdx === i ? '#0369a1' : '#0284c7'}
              />
              <rect
                x={cx - barW / 2}
                y={txY}
                width={barW}
                height={Math.max(1, txH)}
                rx="2"
                fill={hoverIdx === i ? '#047857' : '#059669'}
              />
              {showLabel && (
                <text
                  x={cx}
                  y={height - 8}
                  textAnchor="middle"
                  className="fill-slate-400 dark:fill-slate-500 text-[10px] font-mono"
                >
                  {d.local_date.slice(5)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
