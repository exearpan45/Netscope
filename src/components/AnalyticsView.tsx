import { useEffect, useState } from 'react';
import { Download, RefreshCw } from 'lucide-react';
import type { DashboardPayload, PeriodAnalyticsResponse } from '../types';
import { formatBytes, formatDateTime, ifaceTypeLabel } from '../utils/format';
import { PeriodUsageChart } from './Charts';

const PERIOD_OPTIONS = [
  { id: 'today', label: 'Today' },
  { id: 'yesterday', label: 'Yesterday' },
  { id: 'last_7_days', label: 'Last 7 Days' },
  { id: 'this_week', label: 'This Week' },
  { id: 'previous_week', label: 'Previous Week' },
  { id: 'last_30_days', label: 'Last 30 Days' },
  { id: 'this_month', label: 'This Month' },
  { id: 'previous_month', label: 'Previous Month' },
  { id: 'last_3_months', label: 'Last 3 Months' },
  { id: 'last_6_months', label: 'Last 6 Months' },
  { id: 'this_year', label: 'This Year' },
  { id: 'previous_year', label: 'Previous Year' },
  { id: 'lifetime', label: 'Lifetime' },
  { id: 'custom', label: 'Custom Range' },
] as const;

export function AnalyticsView({
  mode,
  data,
  onRescanHistory,
}: {
  mode: 'daily' | 'weekly' | 'monthly' | 'historical';
  data: DashboardPayload;
  onRescanHistory: () => Promise<void>;
}) {
  const defaultPeriod =
    mode === 'daily'
      ? 'today'
      : mode === 'weekly'
      ? 'last_7_days'
      : mode === 'monthly'
      ? 'this_month'
      : 'last_30_days';

  const [period, setPeriod] = useState<string>(defaultPeriod);
  const [ifaceFilter, setIfaceFilter] = useState<string>('all');
  const [customStart, setCustomStart] = useState<string>(
    new Date(Date.now() - 6 * 86400_000).toISOString().slice(0, 10)
  );
  const [customEnd, setCustomEnd] = useState<string>(new Date().toISOString().slice(0, 10));
  const [analytics, setAnalytics] = useState<PeriodAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [scanning, setScanning] = useState<boolean>(false);

  useEffect(() => {
    setPeriod(defaultPeriod);
  }, [defaultPeriod]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    const qs = new URLSearchParams({
      period,
      iface: ifaceFilter,
    });
    if (period === 'custom') {
      qs.set('start', customStart);
      qs.set('end', customEnd);
    }
    fetch(`/api/analytics?${qs.toString()}`)
      .then((r) => r.json())
      .then((res) => {
        if (active) setAnalytics(res);
      })
      .catch(() => {})
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [period, ifaceFilter, customStart, customEnd, data.status.last_sample_ts]);

  const exportScope =
    mode === 'daily' ? 'daily' : mode === 'weekly' ? 'weekly' : mode === 'monthly' ? 'monthly' : 'complete';

  const triggerExport = (fmt: 'csv' | 'json' | 'pdf') => {
    window.location.href = `/api/export?format=${fmt}&scope=${exportScope}`;
  };

  return (
    <div className="space-y-6">
      {/* Filter & Export Bar */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <select
            aria-label="Select time period"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="px-3 py-2 text-xs font-medium rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-slate-100"
          >
            {PERIOD_OPTIONS.map((opt) => (
              <option key={opt.id} value={opt.id}>
                {opt.label}
              </option>
            ))}
          </select>

          {period === 'custom' && (
            <div className="flex items-center gap-2 text-xs">
              <input
                type="date"
                value={customStart}
                onChange={(e) => setCustomStart(e.target.value)}
                className="px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono"
              />
              <span className="text-slate-400">to</span>
              <input
                type="date"
                value={customEnd}
                onChange={(e) => setCustomEnd(e.target.value)}
                className="px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono"
              />
            </div>
          )}

          <select
            aria-label="Filter by interface"
            value={ifaceFilter}
            onChange={(e) => setIfaceFilter(e.target.value)}
            className="px-3 py-2 text-xs font-medium rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-slate-100"
          >
            <option value="all">All Interfaces</option>
            {data.interfaces.map((i) => (
              <option key={i.iface} value={i.iface}>
                {i.iface} ({ifaceTypeLabel(i.iface_type)})
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          {(['csv', 'json', 'pdf'] as const).map((fmt) => (
            <button
              key={fmt}
              onClick={() => triggerExport(fmt)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 transition-colors whitespace-nowrap"
            >
              <Download className="w-3.5 h-3.5" />
              Export {fmt.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Period Summary KPIs */}
      {loading && !analytics ? (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 text-sm text-slate-500">
          Querying SQLite analytics...
        </div>
      ) : analytics ? (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
              <div className="text-xs text-slate-500 dark:text-slate-400">
                {analytics.label} Total
              </div>
              <div className="mt-2 text-2xl font-semibold font-mono text-slate-900 dark:text-slate-100">
                {formatBytes(analytics.summary.total_bytes)}
              </div>
              <div className="mt-2 text-xs font-mono text-slate-500 dark:text-slate-400">
                DL {formatBytes(analytics.summary.total_rx_bytes)} · UL {formatBytes(analytics.summary.total_tx_bytes)}
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
              <div className="text-xs text-slate-500 dark:text-slate-400">Daily Average</div>
              <div className="mt-2 text-2xl font-semibold font-mono text-slate-900 dark:text-slate-100">
                {formatBytes(analytics.summary.daily_average_bytes)}
              </div>
              <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                Across {analytics.summary.active_days} recorded day(s)
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
              <div className="text-xs text-slate-500 dark:text-slate-400">Highest Usage Day</div>
              <div className="mt-2 text-xl font-semibold font-mono text-slate-900 dark:text-slate-100">
                {analytics.summary.highest_day
                  ? formatBytes(analytics.summary.highest_day.total_bytes)
                  : 'No data'}
              </div>
              <div className="mt-2 text-xs font-mono text-slate-500 dark:text-slate-400">
                {analytics.summary.highest_day?.local_date || '—'}
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
              <div className="text-xs text-slate-500 dark:text-slate-400">
                Period Comparison &amp; Top App
              </div>
              <div className="mt-2 text-base font-semibold text-slate-900 dark:text-slate-100 truncate">
                {analytics.summary.most_consuming_app?.app_name || 'No app activity'}
              </div>
              <div className="mt-2 text-xs font-mono text-slate-500 dark:text-slate-400">
                {analytics.summary.percent_change_vs_previous !== null
                  ? `${analytics.summary.percent_change_vs_previous > 0 ? '+' : ''}${analytics.summary.percent_change_vs_previous}% vs prior period`
                  : 'No prior-period baseline'}
              </div>
            </div>
          </div>

          {/* Consumption Chart */}
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                  Data Consumption Timeline ({analytics.start_date} to {analytics.end_date})
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Download (sky) vs Upload (emerald) from SQLite daily_interface_usage
                </p>
              </div>
            </div>
            <PeriodUsageChart series={analytics.daily_series} height={240} />
          </div>

          {/* Interface & Application Breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-3">
                Breakdown by Interface
              </h3>
              {analytics.by_interface.length === 0 ? (
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  No interface usage recorded in this period.
                </p>
              ) : (
                <div className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
                  {analytics.by_interface.map((row) => (
                    <div key={row.iface} className="py-2.5 flex items-center justify-between font-mono">
                      <div>
                        <span className="font-semibold text-slate-900 dark:text-slate-100">
                          {row.iface}
                        </span>{' '}
                        <span className="text-slate-500">({ifaceTypeLabel(row.iface_type)})</span>
                      </div>
                      <div className="text-right">
                        <span className="text-sky-600 dark:text-sky-400">
                          DL {formatBytes(row.rx_bytes)}
                        </span>{' '}
                        ·{' '}
                        <span className="text-emerald-600 dark:text-emerald-400">
                          UL {formatBytes(row.tx_bytes)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-3">
                Application Ranking ({analytics.label})
              </h3>
              {analytics.by_application.length === 0 ? (
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  No application records in this period.
                </p>
              ) : (
                <div className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
                  {analytics.by_application.slice(0, 10).map((app) => (
                    <div key={app.app_id} className="py-2.5 flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-medium text-slate-900 dark:text-slate-100 truncate">
                          {app.app_name}
                        </div>
                        <div className="font-mono text-slate-500 truncate">{app.exe_path}</div>
                      </div>
                      <div className="text-right font-mono shrink-0">
                        {app.bytes_available ? (
                          <span>
                            {formatBytes((app.rx_bytes || 0) + (app.tx_bytes || 0))}
                          </span>
                        ) : (
                          <span className="text-slate-500">
                            Peak {app.peak_sockets} sockets (bytes unavailable)
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      ) : null}

      {/* Historical Data Recovery Audit (shown prominently in Historical Analytics) */}
      {mode === 'historical' && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
          <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
            <div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                Historical Data Recovery Audit
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                Genuine pre-installation sources checked on this Linux host (vnStat, NetworkManager, kernel boot counters)
              </p>
            </div>
            <button
              disabled={scanning}
              onClick={async () => {
                setScanning(true);
                try {
                  await onRescanHistory();
                } finally {
                  setScanning(false);
                }
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
              Re-scan Historical Sources
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400">
                  <th className="py-2 pr-4 font-medium">Source</th>
                  <th className="py-2 px-3 font-medium">Period / Scope</th>
                  <th className="py-2 px-3 font-medium">Interface</th>
                  <th className="py-2 px-3 font-medium text-right">Download</th>
                  <th className="py-2 px-3 font-medium text-right">Upload</th>
                  <th className="py-2 px-3 font-medium">Type &amp; Status</th>
                  <th className="py-2 pl-3 font-medium">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
                {data.historical_imports.map((rec) => (
                  <tr key={rec.id}>
                    <td className="py-2.5 pr-4 font-medium text-slate-900 dark:text-slate-100">
                      {rec.source}
                    </td>
                    <td className="py-2.5 px-3 font-mono text-slate-600 dark:text-slate-300">
                      {rec.period_label}
                      {rec.start_ts && (
                        <div className="text-[11px] text-slate-400">
                          {formatDateTime(rec.start_ts)}
                        </div>
                      )}
                    </td>
                    <td className="py-2.5 px-3 font-mono">{rec.iface || '—'}</td>
                    <td className="py-2.5 px-3 font-mono text-right">
                      {rec.rx_bytes !== null ? formatBytes(rec.rx_bytes) : 'Unavailable'}
                    </td>
                    <td className="py-2.5 px-3 font-mono text-right">
                      {rec.tx_bytes !== null ? formatBytes(rec.tx_bytes) : 'Unavailable'}
                    </td>
                    <td className="py-2.5 px-3 font-mono">
                      {rec.measurement_type} · {rec.import_status}
                    </td>
                    <td className="py-2.5 pl-3 text-slate-600 dark:text-slate-300 max-w-md">
                      {rec.notes}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
