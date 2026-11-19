import { useEffect, useState } from 'react';
import { AlertCircle, Search, X } from 'lucide-react';
import type { ApplicationItem, DashboardPayload } from '../types';
import { formatBytes, formatDateTime, formatSpeed } from '../utils/format';

type SortKey = 'total' | 'download' | 'upload' | 'sockets' | 'name';

export function ApplicationsView({ data }: { data: DashboardPayload }) {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'running' | 'stopped'>('all');
  const [sortBy, setSortBy] = useState<SortKey>('total');
  const [selectedApp, setSelectedApp] = useState<ApplicationItem | null>(null);
  const [appHistory, setAppHistory] = useState<
    Array<{
      local_date: string;
      rx_bytes: number | null;
      tx_bytes: number | null;
      bytes_available: number;
      active_sockets: number;
      measurement_source: string;
    }>
  >([]);

  useEffect(() => {
    if (!selectedApp) return;
    fetch(`/api/applications/${encodeURIComponent(selectedApp.app_id)}`)
      .then((r) => r.json())
      .then((res) => {
        setAppHistory(res.history || []);
      })
      .catch(() => setAppHistory([]));
  }, [selectedApp]);

  const filtered = data.applications
    .filter((a) => {
      if (statusFilter !== 'all' && a.status !== statusFilter) return false;
      if (!search.trim()) return true;
      const q = search.toLowerCase();
      return (
        a.app_name.toLowerCase().includes(q) ||
        a.exe_path.toLowerCase().includes(q) ||
        a.owner.toLowerCase().includes(q) ||
        a.pids.some((p) => String(p).includes(q))
      );
    })
    .sort((a, b) => {
      if (sortBy === 'name') return a.app_name.localeCompare(b.app_name);
      if (sortBy === 'download') {
        return (b.total_rx_bytes ?? -1) - (a.total_rx_bytes ?? -1) || b.active_sockets - a.active_sockets;
      }
      if (sortBy === 'upload') {
        return (b.total_tx_bytes ?? -1) - (a.total_tx_bytes ?? -1) || b.active_sockets - a.active_sockets;
      }
      if (sortBy === 'sockets') return b.active_sockets - a.active_sockets;
      const totA = (a.total_rx_bytes ?? -1) + (a.total_tx_bytes ?? 0);
      const totB = (b.total_rx_bytes ?? -1) + (b.total_tx_bytes ?? 0);
      return totB - totA || b.active_sockets - a.active_sockets;
    });

  return (
    <div className="space-y-6">
      {!data.capabilities.per_process_bytes_available && (
        <div className="rounded-xl border border-amber-200 dark:border-amber-900/60 bg-amber-50/70 dark:bg-amber-950/20 p-4 flex items-start gap-3">
          <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
          <div className="text-xs text-amber-900 dark:text-amber-200 leading-relaxed">
            <span className="font-semibold">Per-Process Byte Accounting Status:</span>{' '}
            Not available with current permissions or system capabilities ({data.capabilities.per_process_byte_method}).{' '}
            Active PIDs, executables, owners, bound interfaces, and live TCP/UDP connections are measured directly from{' '}
            <span className="font-mono">/proc/[PID]/fd</span> and <span className="font-mono">/proc/net/*</span>. On standard Ubuntu/Zorin/Mint kernels with{' '}
            <span className="font-mono">CONFIG_INET_TCP_DIAG</span> or eBPF/nftables helper privileges, exact per-app byte totals populate automatically.
          </div>
        </div>
      )}

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-5">
          <div className="relative flex-1 min-w-[240px] max-w-sm">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search app, executable, owner, or PID..."
              className="w-full pl-9 pr-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1 p-1 rounded-lg bg-slate-100 dark:bg-slate-800">
              {(['all', 'running', 'stopped'] as const).map((st) => (
                <button
                  key={st}
                  onClick={() => setStatusFilter(st)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md capitalize transition-colors ${
                    statusFilter === st
                      ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 shadow-sm'
                      : 'text-slate-600 dark:text-slate-400'
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>

            <select
              aria-label="Sort applications"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortKey)}
              className="px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200"
            >
              <option value="total">Sort: Total Usage</option>
              <option value="download">Sort: Download</option>
              <option value="upload">Sort: Upload</option>
              <option value="sockets">Sort: Active Sockets</option>
              <option value="name">Sort: Name</option>
            </select>
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="py-10 text-center text-sm text-slate-500 dark:text-slate-400">
            {data.settings.privacy_mode === 'true'
              ? 'Privacy Mode is enabled; per-process inspection is suspended.'
              : 'No matching applications found.'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400">
                  <th className="py-2.5 pr-4 font-medium">Application</th>
                  <th className="py-2.5 px-3 font-medium">Owner / PID</th>
                  <th className="py-2.5 px-3 font-medium">Status</th>
                  <th className="py-2.5 px-3 font-medium text-right">Sockets (Net / LAN)</th>
                  <th className="py-2.5 px-3 font-medium text-right">Download</th>
                  <th className="py-2.5 px-3 font-medium text-right">Upload</th>
                  <th className="py-2.5 pl-3 font-medium text-right">Last Active</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800 text-sm">
                {filtered.map((app) => (
                  <tr
                    key={app.app_id}
                    onClick={() => setSelectedApp(app)}
                    className="hover:bg-slate-50 dark:hover:bg-slate-800/40 cursor-pointer transition-colors"
                  >
                    <td className="py-3 pr-4">
                      <div className="font-medium text-slate-900 dark:text-slate-100">
                        {app.app_name}
                      </div>
                      <div className="text-xs font-mono text-slate-500 dark:text-slate-400 truncate max-w-xs">
                        {app.exe_path || 'Executable path restricted'}
                      </div>
                    </td>
                    <td className="py-3 px-3 text-xs font-mono text-slate-600 dark:text-slate-300">
                      {app.owner} · {app.pids.length > 0 ? app.pids.slice(0, 3).join(', ') : '—'}
                    </td>
                    <td className="py-3 px-3 text-xs">
                      <span
                        className={
                          app.status === 'running'
                            ? 'text-emerald-600 dark:text-emerald-400 font-medium'
                            : 'text-slate-500 dark:text-slate-400'
                        }
                      >
                        {app.status === 'running' ? 'Running' : 'Stopped'}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-xs font-mono text-right text-slate-700 dark:text-slate-300">
                      {app.active_sockets} ({app.internet_sockets} / {app.lan_sockets})
                    </td>
                    <td className="py-3 px-3 text-xs font-mono text-right">
                      {app.bytes_available ? (
                        <span className="text-sky-600 dark:text-sky-400">
                          {formatBytes(app.total_rx_bytes)} ({formatSpeed(app.rx_rate_bps)})
                        </span>
                      ) : (
                        <span className="text-slate-400 dark:text-slate-500">Not available</span>
                      )}
                    </td>
                    <td className="py-3 px-3 text-xs font-mono text-right">
                      {app.bytes_available ? (
                        <span className="text-emerald-600 dark:text-emerald-400">
                          {formatBytes(app.total_tx_bytes)} ({formatSpeed(app.tx_rate_bps)})
                        </span>
                      ) : (
                        <span className="text-slate-400 dark:text-slate-500">Not available</span>
                      )}
                    </td>
                    <td className="py-3 pl-3 text-xs font-mono text-right text-slate-500 dark:text-slate-400">
                      {formatDateTime(app.last_active_ts)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Application Detail Inspection Panel */}
      {selectedApp && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                {selectedApp.app_name} — Process &amp; Socket Inspection
              </h3>
              <p className="text-xs font-mono text-slate-500 dark:text-slate-400 mt-1">
                {selectedApp.exe_path} · Owner: {selectedApp.owner} · Interfaces:{' '}
                {selectedApp.interfaces.join(', ') || 'Wildcard / Unbound'}
              </p>
            </div>
            <button
              onClick={() => setSelectedApp(null)}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
              aria-label="Close application detail"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div>
              <h4 className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2">
                Live Sockets ({selectedApp.connections.length})
              </h4>
              {selectedApp.connections.length === 0 ? (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  No open network sockets right now.
                </p>
              ) : (
                <div className="max-h-64 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800 text-xs font-mono">
                  {selectedApp.connections.map((c, idx) => (
                    <div key={idx} className="py-2 flex items-center justify-between gap-2">
                      <div className="truncate">
                        <span className="text-slate-500">{c.proto}</span> {c.local} → {c.remote}
                      </div>
                      <span className="text-slate-500 shrink-0">
                        {c.state} · {c.scope.toUpperCase()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <h4 className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2">
                Recorded Daily History
              </h4>
              {appHistory.length === 0 ? (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  No historical daily records yet.
                </p>
              ) : (
                <div className="max-h-64 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800 text-xs font-mono">
                  {appHistory.map((h) => (
                    <div key={h.local_date} className="py-2 flex items-center justify-between">
                      <span>{h.local_date}</span>
                      <span>
                        {h.bytes_available
                          ? `DL ${formatBytes(h.rx_bytes)} · UL ${formatBytes(h.tx_bytes)}`
                          : `Peak sockets: ${h.active_sockets} (bytes unavailable)`}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
