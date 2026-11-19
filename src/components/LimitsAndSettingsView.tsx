import { useState } from 'react';
import { Bell, CheckCircle2, Database, Download, Shield, Trash2 } from 'lucide-react';
import type { DashboardPayload } from '../types';
import { formatBytes, formatDateTime } from '../utils/format';

export function DataLimitsView({
  data,
  onCreateLimit,
  onDeleteLimit,
  onAckAlerts,
}: {
  data: DashboardPayload;
  onCreateLimit: (payload: {
    name: string;
    period_type: 'daily' | 'weekly' | 'monthly' | 'custom';
    limit_bytes: number;
    custom_days: number;
    notify_desktop: boolean;
  }) => Promise<void>;
  onDeleteLimit: (id: number) => Promise<void>;
  onAckAlerts: () => Promise<void>;
}) {
  const [name, setName] = useState('Monthly ISP Allowance');
  const [periodType, setPeriodType] = useState<'daily' | 'weekly' | 'monthly' | 'custom'>('monthly');
  const [amountGb, setAmountGb] = useState('100');
  const [customDays, setCustomDays] = useState('30');
  const [notifyDesktop, setNotifyDesktop] = useState(true);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const gb = parseFloat(amountGb);
    if (!Number.isFinite(gb) || gb <= 0) return;
    setSaving(true);
    try {
      await onCreateLimit({
        name,
        period_type: periodType,
        limit_bytes: Math.round(gb * 1024 * 1024 * 1024),
        custom_days: Math.max(1, parseInt(customDays, 10) || 30),
        notify_desktop: notifyDesktop,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
          Configure Data Allowance &amp; Threshold Alerts
        </h2>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 mb-5">
          Triggers warnings at 50%, 75%, 90%, and 100% consumption. NETSCOPE monitors and alerts locally; it does not claim to throttle or enforce ISP carrier caps.
        </p>

        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              Allowance Name
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-slate-100"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              Period
            </label>
            <select
              value={periodType}
              onChange={(e) =>
                setPeriodType(e.target.value as 'daily' | 'weekly' | 'monthly' | 'custom')
              }
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-slate-100"
            >
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
              <option value="custom">Custom Days</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              {periodType === 'custom' ? 'Limit (GB) / Days' : 'Limit (GB)'}
            </label>
            <div className="flex gap-2">
              <input
                type="number"
                step="0.1"
                min="0.01"
                required
                value={amountGb}
                onChange={(e) => setAmountGb(e.target.value)}
                className="w-full px-3 py-2 text-xs font-mono rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              />
              {periodType === 'custom' && (
                <input
                  type="number"
                  min="1"
                  value={customDays}
                  onChange={(e) => setCustomDays(e.target.value)}
                  className="w-20 px-2 py-2 text-xs font-mono rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800"
                  title="Custom window days"
                />
              )}
            </div>
          </div>

          <div className="flex items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={notifyDesktop}
                onChange={(e) => setNotifyDesktop(e.target.checked)}
              />
              Desktop notify
            </label>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-sky-600 hover:bg-sky-700 text-white transition-colors whitespace-nowrap"
            >
              Add Limit
            </button>
          </div>
        </form>
      </div>

      {/* Configured Limits */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-4">
          Active Limits ({data.limits.length})
        </h3>
        {data.limits.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            No data limits configured yet. Add one above to enable 50% / 75% / 90% / 100% threshold tracking.
          </p>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {data.limits.map((lim) => (
              <div key={lim.id} className="py-4 flex flex-wrap items-center justify-between gap-4">
                <div className="flex-1 min-w-[260px]">
                  <div className="flex items-center justify-between text-sm mb-1.5">
                    <span className="font-medium text-slate-900 dark:text-slate-100">
                      {lim.name} · <span className="text-xs text-slate-500">{lim.period_type}</span>
                    </span>
                    <span className="font-mono text-xs text-slate-600 dark:text-slate-300">
                      {formatBytes(lim.consumed_bytes)} / {formatBytes(lim.limit_bytes)} ({lim.percent_used}%)
                    </span>
                  </div>
                  <div className="h-2.5 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden relative">
                    <div
                      className={`h-full ${
                        lim.percent_used >= 100
                          ? 'bg-red-600'
                          : lim.percent_used >= 90
                          ? 'bg-red-500'
                          : lim.percent_used >= 75
                          ? 'bg-amber-500'
                          : 'bg-sky-600'
                      }`}
                      style={{ width: `${Math.min(100, lim.percent_used)}%` }}
                    />
                  </div>
                </div>
                <button
                  onClick={() => onDeleteLimit(lim.id)}
                  className="p-2 text-slate-400 hover:text-red-600 rounded-lg transition-colors"
                  aria-label={`Delete limit ${lim.name}`}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Alert History */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Triggered Threshold Notifications
          </h3>
          {data.alerts.some((a) => !a.acknowledged) && (
            <button
              onClick={onAckAlerts}
              className="text-xs font-medium text-sky-600 dark:text-sky-400 hover:underline"
            >
              Mark all read
            </button>
          )}
        </div>
        {data.alerts.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            No data threshold alerts have fired.
          </p>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
            {data.alerts.map((al) => (
              <div key={al.id} className="py-3 flex items-center justify-between gap-4">
                <div className="flex items-center gap-2.5">
                  <Bell className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                  <span className="text-slate-800 dark:text-slate-200">{al.message}</span>
                </div>
                <span className="font-mono text-slate-500 shrink-0">
                  {formatDateTime(al.created_at)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function SettingsView({
  data,
  theme,
  onThemeChange,
  onUpdateSetting,
  onBackup,
}: {
  data: DashboardPayload;
  theme: 'light' | 'dark';
  onThemeChange: (t: 'light' | 'dark') => void;
  onUpdateSetting: (patch: Record<string, string | boolean>) => Promise<void>;
  onBackup: () => Promise<void>;
}) {
  const [backupMsg, setBackupMsg] = useState<string | null>(null);
  const s = data.settings;

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-5">
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
          Monitoring &amp; Privacy Settings
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-slate-800">
            <div>
              <div className="text-sm font-medium text-slate-900 dark:text-slate-100">
                Refresh Interval
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400">
                Background daemon sampling cadence
              </div>
            </div>
            <select
              value={s.refresh_interval_sec || '1'}
              onChange={(e) => onUpdateSetting({ refresh_interval_sec: e.target.value })}
              className="px-3 py-1.5 text-xs font-mono rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800"
            >
              <option value="1">1 second</option>
              <option value="2">2 seconds</option>
              <option value="5">5 seconds</option>
              <option value="10">10 seconds</option>
            </select>
          </div>

          <div className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-slate-800">
            <div>
              <div className="text-sm font-medium text-slate-900 dark:text-slate-100">
                Appearance Mode
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400">
                Light or Dark desktop theme
              </div>
            </div>
            <div className="flex items-center gap-1 p-1 rounded-lg bg-slate-100 dark:bg-slate-800">
              {(['light', 'dark'] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => onThemeChange(m)}
                  className={`px-3 py-1 text-xs font-medium rounded-md capitalize ${
                    theme === m
                      ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 shadow-sm'
                      : 'text-slate-600 dark:text-slate-400'
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-slate-800">
            <div>
              <div className="text-sm font-medium text-slate-900 dark:text-slate-100">
                Exclude Loopback (lo)
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400">
                Omit 127.0.0.1 local traffic from internet usage totals
              </div>
            </div>
            <input
              type="checkbox"
              checked={s.exclude_loopback !== 'false'}
              onChange={(e) => onUpdateSetting({ exclude_loopback: e.target.checked })}
              className="w-4 h-4 accent-sky-600"
            />
          </div>

          <div className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-slate-800">
            <div>
              <div className="text-sm font-medium text-slate-900 dark:text-slate-100">
                Privacy Mode
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400">
                Suspend per-process socket &amp; browser tab recording
              </div>
            </div>
            <input
              type="checkbox"
              checked={s.privacy_mode === 'true'}
              onChange={(e) => onUpdateSetting({ privacy_mode: e.target.checked })}
              className="w-4 h-4 accent-sky-600"
            />
          </div>

          <div className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-slate-800">
            <div>
              <div className="text-sm font-medium text-slate-900 dark:text-slate-100">
                Browser Tab Telemetry
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400">
                Accept local WebExtension / Native Messaging tab metrics
              </div>
            </div>
            <input
              type="checkbox"
              checked={s.browser_telemetry_enabled !== 'false'}
              onChange={(e) => onUpdateSetting({ browser_telemetry_enabled: e.target.checked })}
              className="w-4 h-4 accent-sky-600"
            />
          </div>

          <div className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-slate-800">
            <div>
              <div className="text-sm font-medium text-slate-900 dark:text-slate-100">
                Data Retention (Days)
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400">
                Daily summary retention in local SQLite
              </div>
            </div>
            <select
              value={s.retention_days || '365'}
              onChange={(e) => onUpdateSetting({ retention_days: e.target.value })}
              className="px-3 py-1.5 text-xs font-mono rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800"
            >
              <option value="90">90 days</option>
              <option value="180">180 days</option>
              <option value="365">365 days</option>
              <option value="730">2 years</option>
              <option value="0">Unlimited</option>
            </select>
          </div>
        </div>
      </div>

      {/* Database Integrity, Backup & Linux Package */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
          <div className="flex items-center gap-2 mb-3">
            <Database className="w-4 h-4 text-sky-600" />
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              SQLite Storage &amp; Integrity
            </h3>
          </div>
          <div className="space-y-2 text-xs font-mono text-slate-600 dark:text-slate-300">
            <div>Integrity Check: {data.db_integrity.status.toUpperCase()}</div>
            <div className="truncate">Database Path: {data.db_integrity.db_path}</div>
            <div>Database Size: {formatBytes(data.db_integrity.size_bytes)}</div>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={async () => {
                await onBackup();
                setBackupMsg('Local SQLite backup snapshot created.');
              }}
              className="px-3.5 py-2 text-xs font-medium rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800"
            >
              Create Backup Now
            </button>
            {backupMsg && (
              <span className="text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> {backupMsg}
              </span>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
          <div className="flex items-center gap-2 mb-3">
            <Shield className="w-4 h-4 text-emerald-600" />
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Native Linux Desktop Package (.deb)
            </h3>
          </div>
          <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed mb-4">
            Install NETSCOPE natively on Ubuntu, Zorin OS, Linux Mint, or Debian with the PySide6 desktop app, system tray indicator, systemd user service, Polkit minimal-privilege helper, and browser extension.
          </p>
          <a
            href="/api/deb/download"
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium rounded-lg bg-sky-600 hover:bg-sky-700 text-white transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            Download netscope_1.0.0_amd64.deb
          </a>
        </div>
      </div>
    </div>
  );
}

export function AboutView({ data }: { data: DashboardPayload }) {
  const c = data.capabilities;

  const capRows: Array<[string, boolean | string, string]> = [
    ['Kernel /proc/net/dev Counters', c.proc_net_dev, 'Exact RX/TX interface byte and packet totals'],
    ['Kernel /proc/net/{tcp,udp} Tables', c.proc_net_sockets, 'Active IPv4/IPv6 TCP & UDP sockets'],
    ['Per-Process /proc/[PID]/fd Mapping', c.proc_pid_fd, 'Maps socket inodes to PIDs, executables, and owners'],
    ['Netlink SOCK_DIAG (ss -tin)', c.netlink_sock_diag, 'Required for per-socket kernel tcp_info byte counters'],
    ['Kernel tcp_info Byte Counters', c.ss_tcp_info_bytes, 'Exact per-socket bytes_received / bytes_acked'],
    ['eBPF BTF & python3-bcc', c.ebpf_btf && c.ebpf_bcc, 'Kernel probe per-process accounting on BTF Linux hosts'],
    ['nftables Privileged Accounting', c.nftables_available, 'Root/Polkit helper packet/byte rules'],
    ['vnStat Historical Database', c.vnstat_db_available, 'Pre-existing /var/lib/vnstat/vnstat.db import'],
    ['Desktop Notifications (notify-send)', c.notify_send_available, 'Native Linux threshold alerts'],
    ['PySide6 Native Desktop UI', c.pyside6_available, 'Qt6 desktop window & system tray integration'],
  ];

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          NETSCOPE — Complete Network Intelligence for Linux
        </h2>
        <p className="text-sm text-slate-600 dark:text-slate-300 mt-1.5 max-w-3xl leading-relaxed">
          Privacy-first, local-only Linux network monitoring platform. All telemetry is sampled directly from Linux kernel interfaces, stored in local SQLite, and never transmitted to external servers.
        </p>
        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono pt-4 border-t border-slate-100 dark:border-slate-800">
          <div>
            <span className="text-slate-500 block">Host</span>
            <span className="text-slate-900 dark:text-slate-100">{c.hostname}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Distribution</span>
            <span className="text-slate-900 dark:text-slate-100">{c.distro_name}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Kernel</span>
            <span className="text-slate-900 dark:text-slate-100">{c.kernel_release} ({c.architecture})</span>
          </div>
          <div>
            <span className="text-slate-500 block">Per-Process Mode</span>
            <span className="text-slate-900 dark:text-slate-100">{c.per_process_byte_method}</span>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-3">
          Detected Linux System Capabilities
        </h3>
        <div className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
          {capRows.map(([label, supported, desc]) => (
            <div key={label} className="py-2.5 flex items-center justify-between gap-4">
              <div>
                <div className="font-medium text-slate-900 dark:text-slate-100">{label}</div>
                <div className="text-slate-500 dark:text-slate-400">{desc}</div>
              </div>
              <span
                className={`font-mono font-medium shrink-0 ${
                  supported
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-amber-600 dark:text-amber-400'
                }`}
              >
                {supported ? 'Available' : 'Unavailable'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {c.limitations.length > 0 && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-2">
            Disclosed Measurement Limitations on Current Host
          </h3>
          <ul className="list-disc pl-5 space-y-1.5 text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
            {c.limitations.map((lim, i) => (
              <li key={i}>{lim}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
