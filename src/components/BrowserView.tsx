import { Globe, Info } from 'lucide-react';
import type { DashboardPayload } from '../types';
import { formatBytes, formatDateTime, formatSpeed } from '../utils/format';

const BROWSER_IDS = new Set([
  'brave',
  'firefox',
  'google-chrome',
  'chromium',
  'msedge',
]);

export function BrowserView({ data }: { data: DashboardPayload }) {
  const detectedBrowsers = data.applications.filter((a) => BROWSER_IDS.has(a.app_id));
  const tabs = data.browser_tabs;

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 flex items-start gap-3">
        <Info className="w-4 h-4 text-sky-600 dark:text-sky-400 mt-0.5 shrink-0" />
        <div className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
          <span className="font-semibold text-slate-900 dark:text-slate-100">
            Measurement Honesty &amp; Double-Counting Prevention:
          </span>{' '}
          Browser tab measurements come from the included WebExtension &amp; Native Messaging Host (
          <span className="font-mono">netscope/browser_extension</span>) using <span className="font-mono">webRequest</span>{' '}
          <span className="font-mono">Content-Length</span> and request payload telemetry. They are strictly labeled as{' '}
          <span className="font-medium">Browser-reported estimates</span> and are never added onto kernel{' '}
          <span className="font-mono">/proc/net/dev</span> system totals.
        </div>
      </div>

      {/* Detected Browser Processes on Linux Host */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-3">
          Detected Browser Processes (Linux /proc)
        </h2>
        {detectedBrowsers.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            No desktop browser processes (Brave, Chrome, Chromium, Firefox, Microsoft Edge) are currently running on this Linux host.
          </p>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {detectedBrowsers.map((b) => (
              <div key={b.app_id} className="py-3 flex items-center justify-between gap-4">
                <div>
                  <div className="text-sm font-medium text-slate-900 dark:text-slate-100">
                    {b.app_name}
                  </div>
                  <div className="text-xs font-mono text-slate-500 dark:text-slate-400">
                    PIDs: {b.pids.join(', ') || '—'} · {b.active_sockets} sockets · {b.status}
                  </div>
                </div>
                <div className="text-right text-xs font-mono">
                  {b.bytes_available ? (
                    <span>
                      DL {formatBytes(b.total_rx_bytes)} · UL {formatBytes(b.total_tx_bytes)}
                    </span>
                  ) : (
                    <span className="text-slate-500 dark:text-slate-400">
                      Shared browser process sockets tracked
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Per-Tab Telemetry Table */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              Per-Tab Browser Telemetry
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Brave · Google Chrome · Chromium · Firefox · Microsoft Edge
            </p>
          </div>
          <span className="text-xs font-mono text-slate-500 dark:text-slate-400">
            {tabs.length} recorded tabs
          </span>
        </div>

        {tabs.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-200 dark:border-slate-800 p-8 text-center">
            <Globe className="w-8 h-8 text-slate-400 mx-auto mb-3" />
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200">
              No browser tab telemetry received yet
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400 max-w-lg mx-auto mt-1.5 leading-relaxed">
              NETSCOPE never fabricates YouTube or GitHub tab metrics. Load the included extension from{' '}
              <span className="font-mono">netscope/browser_extension</span> in Brave, Chrome, Chromium, Edge, or Firefox
              to stream real tab titles, domains, and Content-Length estimates via Native Messaging.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400">
                  <th className="py-2.5 pr-4 font-medium">Browser</th>
                  <th className="py-2.5 px-3 font-medium">Tab Title</th>
                  <th className="py-2.5 px-3 font-medium">Website</th>
                  <th className="py-2.5 px-3 font-medium">Status</th>
                  <th className="py-2.5 px-3 font-medium text-right">Download (Est.)</th>
                  <th className="py-2.5 px-3 font-medium text-right">Upload (Est.)</th>
                  <th className="py-2.5 px-3 font-medium text-right">Activity</th>
                  <th className="py-2.5 pl-3 font-medium text-right">Accuracy</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800 text-sm">
                {tabs.map((t) => (
                  <tr key={t.tab_key}>
                    <td className="py-3 pr-4 text-xs font-medium text-slate-800 dark:text-slate-200">
                      {t.browser_name}
                    </td>
                    <td className="py-3 px-3 text-xs text-slate-900 dark:text-slate-100 max-w-xs truncate">
                      {t.tab_title}
                    </td>
                    <td className="py-3 px-3 text-xs font-mono text-slate-600 dark:text-slate-300">
                      {t.domain}
                    </td>
                    <td className="py-3 px-3 text-xs">
                      {t.is_active ? 'Active' : 'Background'}
                    </td>
                    <td className="py-3 px-3 text-xs font-mono text-right text-sky-600 dark:text-sky-400">
                      {formatBytes(t.rx_bytes)}
                    </td>
                    <td className="py-3 px-3 text-xs font-mono text-right text-emerald-600 dark:text-emerald-400">
                      {formatBytes(t.tx_bytes)}
                    </td>
                    <td className="py-3 px-3 text-xs font-mono text-right text-slate-500 dark:text-slate-400">
                      {formatSpeed(t.rx_rate_bps + t.tx_rate_bps)} · {formatDateTime(t.last_active_ts)}
                    </td>
                    <td className="py-3 pl-3 text-xs text-right text-amber-600 dark:text-amber-400">
                      Browser-reported estimate
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
