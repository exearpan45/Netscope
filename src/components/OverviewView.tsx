import { useState } from 'react';
import {
  Activity,
  ArrowDown,
  ArrowUp,
  ChevronRight,
  Network,
  ShieldCheck,
  Wifi,
} from 'lucide-react';
import type { DashboardPayload, NetworkInterfaceItem } from '../types';
import { formatBytes, formatDateTime, formatSpeed, ifaceTypeLabel } from '../utils/format';
import { LiveSpeedChart } from './Charts';

export function OverviewView({
  data,
  onNavigate,
}: {
  data: DashboardPayload;
  onNavigate: (section: 'live' | 'applications' | 'interfaces' | 'historical') => void;
}) {
  const { overview, status, speed_series, interfaces, applications, limits } = data;
  const excludeLo = data.settings.exclude_loopback !== 'false';
  const visibleInterfaces = interfaces.filter((i) => (excludeLo ? i.iface_type !== 'loopback' : true));
  const runningApps = applications.filter((a) => a.status === 'running');

  const dlPct =
    overview.today.total_bytes > 0
      ? Math.round((overview.today.total_rx_bytes / overview.today.total_bytes) * 100)
      : 0;

  return (
    <div className="space-y-6">
      {/* 4-Column KPI Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>Today&apos;s Traffic</span>
            <span>Kernel /proc/net/dev</span>
          </div>
          <div className="mt-2 text-2xl font-semibold tracking-tight font-mono text-slate-900 dark:text-slate-100">
            {formatBytes(overview.today.total_bytes)}
          </div>
          <div className="mt-2 flex items-center gap-3 text-xs font-mono text-slate-600 dark:text-slate-400">
            <span className="text-sky-600 dark:text-sky-400">
              DL {formatBytes(overview.today.total_rx_bytes)}
            </span>
            <span aria-hidden="true">·</span>
            <span className="text-emerald-600 dark:text-emerald-400">
              UL {formatBytes(overview.today.total_tx_bytes)}
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>Last 7 Days</span>
            <span>{overview.last_7_days.active_days} active days</span>
          </div>
          <div className="mt-2 text-2xl font-semibold tracking-tight font-mono text-slate-900 dark:text-slate-100">
            {formatBytes(overview.last_7_days.total_bytes)}
          </div>
          <div className="mt-2 text-xs font-mono text-slate-500 dark:text-slate-400">
            Avg {formatBytes(overview.last_7_days.daily_average_bytes)} / day
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>This Month</span>
            <span>Calendar cycle</span>
          </div>
          <div className="mt-2 text-2xl font-semibold tracking-tight font-mono text-slate-900 dark:text-slate-100">
            {formatBytes(overview.this_month.total_bytes)}
          </div>
          <div className="mt-2 text-xs font-mono text-slate-500 dark:text-slate-400">
            Lifetime recorded: {formatBytes(overview.lifetime.total_bytes)}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>Live Throughput</span>
            <span>{status.vpn_connected ? 'VPN Tunnel Active' : status.active_interfaces.join(', ') || 'No link'}</span>
          </div>
          <div className="mt-2 flex items-baseline gap-3 font-mono">
            <span className="text-xl font-semibold text-sky-600 dark:text-sky-400">
              {formatSpeed(status.current_rx_rate_bps)}
            </span>
            <span className="text-sm text-emerald-600 dark:text-emerald-400">
              {formatSpeed(status.current_tx_rate_bps)}
            </span>
          </div>
          <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
            {runningApps.length} network-active apps · {data.settings.refresh_interval_sec}s interval
          </div>
        </div>
      </div>

      {/* Primary Live Speed Graph + Download/Upload Split */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              Real-Time System Network Speed
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Exact kernel interface counters · {excludeLo ? 'Loopback excluded' : 'Including loopback'}
            </p>
          </div>
          <div className="flex items-center gap-5 text-xs">
            <span className="flex items-center gap-1.5 text-sky-600 dark:text-sky-400 font-medium">
              <ArrowDown className="w-3.5 h-3.5" />
              Download ({dlPct}%)
            </span>
            <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-medium">
              <ArrowUp className="w-3.5 h-3.5" />
              Upload ({100 - dlPct}%)
            </span>
            <button
              onClick={() => onNavigate('live')}
              className="text-xs font-medium text-sky-600 dark:text-sky-400 hover:underline flex items-center gap-1 whitespace-nowrap"
            >
              Open Live Monitor <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <LiveSpeedChart series={speed_series} height={240} />

        {/* Download vs Upload comparison bar */}
        <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800">
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 mb-1.5">
            <span>Today Download vs Upload Ratio</span>
            <span className="font-mono">
              {formatBytes(overview.today.total_rx_bytes)} down / {formatBytes(overview.today.total_tx_bytes)} up
            </span>
          </div>
          <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden flex">
            <div
              className="bg-sky-600 dark:bg-sky-500 h-full transition-all"
              style={{ width: `${overview.today.total_bytes > 0 ? dlPct : 50}%` }}
            />
            <div
              className="bg-emerald-600 dark:bg-emerald-500 h-full transition-all"
              style={{ width: `${overview.today.total_bytes > 0 ? 100 - dlPct : 50}%` }}
            />
          </div>
        </div>
      </div>

      {/* Two-column summary: Active Interfaces & Running Applications */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Active Network Interfaces
            </h3>
            <button
              onClick={() => onNavigate('interfaces')}
              className="text-xs font-medium text-sky-600 dark:text-sky-400 hover:underline"
            >
              Inspect all
            </button>
          </div>
          {visibleInterfaces.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">
              No active non-loopback interfaces detected.
            </p>
          ) : (
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {visibleInterfaces.map((iface) => (
                <div key={iface.iface} className="py-3 flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-medium text-slate-900 dark:text-slate-100">
                        {iface.iface}
                      </span>
                      <span className="text-xs text-slate-500 dark:text-slate-400">
                        {ifaceTypeLabel(iface.iface_type)} · {iface.status}
                      </span>
                    </div>
                    <div className="text-xs font-mono text-slate-500 dark:text-slate-400 truncate mt-0.5">
                      {iface.ip_addresses.map((ip) => ip.local).join(', ') || 'No IP assigned'}
                    </div>
                  </div>
                  <div className="text-right font-mono shrink-0">
                    <div className="text-xs text-slate-900 dark:text-slate-100">
                      {formatBytes(iface.recorded_rx_bytes + iface.recorded_tx_bytes)}
                    </div>
                    <div className="text-[11px] text-slate-500 dark:text-slate-400">
                      {formatSpeed(iface.rx_rate_bps)} ↓ · {formatSpeed(iface.tx_rate_bps)} ↑
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Active Network Applications
            </h3>
            <button
              onClick={() => onNavigate('applications')}
              className="text-xs font-medium text-sky-600 dark:text-sky-400 hover:underline"
            >
              View all ({applications.length})
            </button>
          </div>
          {runningApps.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">
              No active network sockets detected or privacy mode is enabled.
            </p>
          ) : (
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {runningApps.slice(0, 6).map((app) => (
                <div key={app.app_id} className="py-3 flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">
                      {app.app_name}
                    </div>
                    <div className="text-xs text-slate-500 dark:text-slate-400 font-mono truncate">
                      {app.active_sockets} sockets · PID {app.pids.slice(0, 3).join(', ')} · {app.owner}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    {app.bytes_available ? (
                      <div className="text-xs font-mono text-slate-900 dark:text-slate-100">
                        {formatBytes((app.total_rx_bytes || 0) + (app.total_tx_bytes || 0))}
                      </div>
                    ) : (
                      <div className="text-xs text-amber-600 dark:text-amber-400">
                        Sockets tracked
                      </div>
                    )}
                    <div className="text-[11px] font-mono text-slate-500 dark:text-slate-400">
                      {app.internet_sockets} internet · {app.lan_sockets} LAN
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Active Data Limits Preview if configured */}
      {limits.length > 0 && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-3">
            Active Data Allowances
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {limits.map((lim) => (
              <div key={lim.id} className="py-2">
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span className="font-medium text-slate-800 dark:text-slate-200">
                    {lim.name} ({lim.period_type})
                  </span>
                  <span className="font-mono text-slate-600 dark:text-slate-400">
                    {formatBytes(lim.consumed_bytes)} / {formatBytes(lim.limit_bytes)} ({lim.percent_used}%)
                  </span>
                </div>
                <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                  <div
                    className={`h-full ${
                      lim.percent_used >= 90
                        ? 'bg-red-600'
                        : lim.percent_used >= 75
                        ? 'bg-amber-500'
                        : 'bg-sky-600'
                    }`}
                    style={{ width: `${Math.min(100, lim.percent_used)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function LiveMonitorView({
  data,
  onIntervalChange,
}: {
  data: DashboardPayload;
  onIntervalChange: (sec: number) => void;
}) {
  const currentSec = Number(data.settings.refresh_interval_sec || '1');
  const excludeLo = data.settings.exclude_loopback !== 'false';

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-5">
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              Second-by-Second Live Telemetry
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Last sample: {formatDateTime(data.status.last_sample_ts)} · {excludeLo ? 'Loopback excluded' : 'Loopback included'}
            </p>
          </div>
          <div className="flex items-center gap-1 p-1 rounded-lg bg-slate-100 dark:bg-slate-800">
            {[1, 2, 5, 10].map((sec) => (
              <button
                key={sec}
                onClick={() => onIntervalChange(sec)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                  currentSec === sec
                    ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 shadow-sm'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                }`}
              >
                {sec}s
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6 pb-5 border-b border-slate-100 dark:border-slate-800">
          <div>
            <div className="text-xs text-slate-500 dark:text-slate-400">Current Download</div>
            <div className="text-xl font-semibold font-mono text-sky-600 dark:text-sky-400 mt-1">
              {formatSpeed(data.status.current_rx_rate_bps)}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-500 dark:text-slate-400">Current Upload</div>
            <div className="text-xl font-semibold font-mono text-emerald-600 dark:text-emerald-400 mt-1">
              {formatSpeed(data.status.current_tx_rate_bps)}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-500 dark:text-slate-400">Today Downloaded</div>
            <div className="text-xl font-semibold font-mono text-slate-900 dark:text-slate-100 mt-1">
              {formatBytes(data.overview.today.total_rx_bytes)}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-500 dark:text-slate-400">Today Uploaded</div>
            <div className="text-xl font-semibold font-mono text-slate-900 dark:text-slate-100 mt-1">
              {formatBytes(data.overview.today.total_tx_bytes)}
            </div>
          </div>
        </div>

        <LiveSpeedChart series={data.speed_series} height={280} />
      </div>

      {/* Real-time Network Events Timeline (connect, disconnect, VPN transitions) */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Network Activity &amp; Interface Transition Log
          </h3>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            Real state changes detected by daemon
          </span>
        </div>
        {data.network_events.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            No interface disconnects, reconnects, or VPN state transitions recorded since monitoring began.
          </p>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {data.network_events.slice(0, 15).map((ev) => (
              <div key={ev.id} className="py-2.5 flex items-center justify-between gap-4 text-xs">
                <div className="flex items-center gap-3 min-w-0">
                  <Activity className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400 shrink-0" />
                  <span className="font-mono font-medium text-slate-800 dark:text-slate-200">
                    {ev.iface}
                  </span>
                  <span className="text-slate-600 dark:text-slate-300 truncate">{ev.details}</span>
                </div>
                <span className="font-mono text-slate-500 dark:text-slate-400 shrink-0">
                  {formatDateTime(ev.ts_utc)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function InterfacesView({ data }: { data: DashboardPayload }) {
  const [selectedIface, setSelectedIface] = useState<string>('all');
  const selectedObj: NetworkInterfaceItem | undefined = data.interfaces.find(
    (i) => i.iface === selectedIface
  );

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-5">
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              Network Interface Intelligence
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Direct kernel interface counters from /proc/net/dev and ip addr
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1 p-1 rounded-lg bg-slate-100 dark:bg-slate-800">
            <button
              onClick={() => setSelectedIface('all')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                selectedIface === 'all'
                  ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 shadow-sm'
                  : 'text-slate-600 dark:text-slate-400'
              }`}
            >
              All ({data.interfaces.length})
            </button>
            {data.interfaces.map((iface) => (
              <button
                key={iface.iface}
                onClick={() => setSelectedIface(iface.iface)}
                className={`px-3 py-1.5 text-xs font-mono font-medium rounded-md transition-colors ${
                  selectedIface === iface.iface
                    ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 shadow-sm'
                    : 'text-slate-600 dark:text-slate-400'
                }`}
              >
                {iface.iface}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400">
                <th className="py-2.5 pr-4 font-medium">Interface</th>
                <th className="py-2.5 px-3 font-medium">Type</th>
                <th className="py-2.5 px-3 font-medium">State</th>
                <th className="py-2.5 px-3 font-medium">IP Addresses</th>
                <th className="py-2.5 px-3 font-medium text-right">RX Speed</th>
                <th className="py-2.5 px-3 font-medium text-right">TX Speed</th>
                <th className="py-2.5 px-3 font-medium text-right">Recorded Total</th>
                <th className="py-2.5 pl-3 font-medium text-right">Since Boot</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800 text-sm">
              {(selectedObj ? [selectedObj] : data.interfaces).map((iface) => (
                <tr
                  key={iface.iface}
                  onClick={() => setSelectedIface(iface.iface)}
                  className="hover:bg-slate-50 dark:hover:bg-slate-800/40 cursor-pointer transition-colors"
                >
                  <td className="py-3 pr-4 font-mono font-medium text-slate-900 dark:text-slate-100">
                    <div className="flex items-center gap-2">
                      {iface.iface_type === 'wifi' ? (
                        <Wifi className="w-4 h-4 text-sky-600" />
                      ) : iface.iface_type === 'vpn' ? (
                        <ShieldCheck className="w-4 h-4 text-emerald-600" />
                      ) : (
                        <Network className="w-4 h-4 text-slate-500" />
                      )}
                      {iface.iface}
                    </div>
                  </td>
                  <td className="py-3 px-3 text-xs text-slate-600 dark:text-slate-300">
                    {ifaceTypeLabel(iface.iface_type)}
                  </td>
                  <td className="py-3 px-3 text-xs font-mono">
                    <span
                      className={
                        iface.status === 'up'
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-slate-500 dark:text-slate-400'
                      }
                    >
                      {iface.status}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-xs font-mono text-slate-600 dark:text-slate-300 max-w-xs truncate">
                    {iface.ip_addresses.map((a) => `${a.local}/${a.prefixlen}`).join(', ') || '—'}
                  </td>
                  <td className="py-3 px-3 text-xs font-mono text-right text-sky-600 dark:text-sky-400">
                    {formatSpeed(iface.rx_rate_bps)}
                  </td>
                  <td className="py-3 px-3 text-xs font-mono text-right text-emerald-600 dark:text-emerald-400">
                    {formatSpeed(iface.tx_rate_bps)}
                  </td>
                  <td className="py-3 px-3 text-xs font-mono text-right text-slate-900 dark:text-slate-100">
                    {formatBytes(iface.recorded_rx_bytes + iface.recorded_tx_bytes)}
                  </td>
                  <td className="py-3 pl-3 text-xs font-mono text-right text-slate-500 dark:text-slate-400">
                    {formatBytes(iface.boot_rx_bytes + iface.boot_tx_bytes)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {selectedObj && (
          <div className="mt-5 pt-5 border-t border-slate-100 dark:border-slate-800 grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            <div>
              <div className="text-slate-500 dark:text-slate-400">MAC Address</div>
              <div className="font-mono text-slate-900 dark:text-slate-100 mt-1">
                {selectedObj.mac_address || 'Not exposed'}
              </div>
            </div>
            <div>
              <div className="text-slate-500 dark:text-slate-400">MTU</div>
              <div className="font-mono text-slate-900 dark:text-slate-100 mt-1">
                {selectedObj.mtu || '—'}
              </div>
            </div>
            <div>
              <div className="text-slate-500 dark:text-slate-400">Since-Boot Download</div>
              <div className="font-mono text-sky-600 dark:text-sky-400 mt-1">
                {formatBytes(selectedObj.boot_rx_bytes)}
              </div>
            </div>
            <div>
              <div className="text-slate-500 dark:text-slate-400">Since-Boot Upload</div>
              <div className="font-mono text-emerald-600 dark:text-emerald-400 mt-1">
                {formatBytes(selectedObj.boot_tx_bytes)}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
