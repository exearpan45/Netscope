import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AppWindow,
  Bell,
  Calendar,
  CalendarDays,
  CalendarRange,
  Gauge,
  Globe,
  History,
  Info,
  LayoutDashboard,
  Menu,
  Moon,
  Network,
  Pause,
  Play,
  Settings,
  Sun,
  X,
} from 'lucide-react';
import { AnalyticsView } from './components/AnalyticsView';
import { ApplicationsView } from './components/ApplicationsView';
import { BrowserView } from './components/BrowserView';
import { AboutView, DataLimitsView, SettingsView } from './components/LimitsAndSettingsView';
import { InterfacesView, LiveMonitorView, OverviewView } from './components/OverviewView';
import type { DashboardPayload, NavSection } from './types';
import { formatDateTime, formatSpeed } from './utils/format';

const NAV_ITEMS: Array<{ id: NavSection; label: string; icon: typeof LayoutDashboard }> = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'live', label: 'Live Monitor', icon: Activity },
  { id: 'applications', label: 'Applications', icon: AppWindow },
  { id: 'browser', label: 'Browser Tracking', icon: Globe },
  { id: 'interfaces', label: 'Network Interfaces', icon: Network },
  { id: 'daily', label: 'Daily Usage', icon: Calendar },
  { id: 'weekly', label: 'Weekly Usage', icon: CalendarDays },
  { id: 'monthly', label: 'Monthly Usage', icon: CalendarRange },
  { id: 'historical', label: 'Historical Analytics', icon: History },
  { id: 'limits', label: 'Data Limits', icon: Gauge },
  { id: 'settings', label: 'Settings', icon: Settings },
  { id: 'about', label: 'About NETSCOPE', icon: Info },
];

export default function App() {
  const [section, setSection] = useState<NavSection>('overview');
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    if (typeof window === 'undefined') return 'dark';
    const saved = window.localStorage.getItem('netscope-theme');
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    window.localStorage.setItem('netscope-theme', theme);
  }, [theme]);

  const refreshNow = useCallback(async () => {
    try {
      const res = await fetch('/api/dashboard');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as DashboardPayload;
      setData(json);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void refreshNow();
    const es = new EventSource('/api/live/stream');
    es.onmessage = (ev) => {
      try {
        const parsed = JSON.parse(ev.data) as DashboardPayload;
        setData(parsed);
        setError(null);
      } catch {
        // ignore parse error
      }
    };
    es.onerror = () => {
      // SSE auto-reconnects; keep fallback error quiet unless no data loaded
    };
    return () => {
      es.close();
    };
  }, [refreshNow]);

  const updateSetting = async (patch: Record<string, string | boolean>) => {
    await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    await refreshNow();
  };

  const unreadAlerts = data?.alerts.filter((a) => !a.acknowledged) || [];
  const activeNav = NAV_ITEMS.find((n) => n.id === section) || NAV_ITEMS[0];

  return (
    <div className="min-h-screen flex bg-slate-50 dark:bg-[#0B1120] text-slate-900 dark:text-slate-100">
      {/* Mobile Sidebar Backdrop */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-30 bg-slate-950/50 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Left Navigation Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 shrink-0 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col transition-transform duration-200 lg:static lg:translate-x-0 ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="h-16 px-5 flex items-center justify-between border-b border-slate-200 dark:border-slate-800">
          <span className="text-lg font-bold tracking-tight text-slate-900 dark:text-white whitespace-nowrap">
            NETSCOPE
          </span>
          <button
            onClick={() => setMobileMenuOpen(false)}
            className="lg:hidden p-1.5 text-slate-500 hover:text-slate-900 dark:hover:text-white"
            aria-label="Close navigation"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = section === item.id;
            return (
              <button
                key={item.id}
                onClick={() => {
                  setSection(item.id);
                  setMobileMenuOpen(false);
                }}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                  active
                    ? 'bg-sky-600 text-white'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100'
                }`}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span className="truncate">{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-200 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400">
          <div className="font-medium text-slate-700 dark:text-slate-300">
            Local Linux Telemetry
          </div>
          <div className="font-mono mt-0.5 truncate">
            {data?.capabilities.hostname || 'localhost'} · SQLite WAL
          </div>
        </div>
      </aside>

      {/* Main Workspace */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Navigation Bar */}
        <header className="h-16 px-4 sm:px-6 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-between gap-4 sticky top-0 z-20">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-2 rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
              aria-label="Open navigation"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="min-w-0">
              <h1 className="text-base font-semibold text-slate-900 dark:text-slate-100 truncate">
                {activeNav.label}
              </h1>
              <div className="text-xs text-slate-500 dark:text-slate-400 truncate">
                {data
                  ? `${data.status.connected ? 'Connected' : 'Disconnected'}${
                      data.status.vpn_connected ? ' · VPN Active' : ''
                    }${data.status.monitoring_paused ? ' · Paused' : ''}`
                  : 'Initializing kernel telemetry...'}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4 shrink-0">
            {data && (
              <div className="hidden md:flex items-center gap-4 text-xs font-mono">
                <span className="text-sky-600 dark:text-sky-400 whitespace-nowrap">
                  DL {formatSpeed(data.status.current_rx_rate_bps)}
                </span>
                <span className="text-emerald-600 dark:text-emerald-400 whitespace-nowrap">
                  UL {formatSpeed(data.status.current_tx_rate_bps)}
                </span>
              </div>
            )}

            {data && (
              <button
                onClick={() =>
                  updateSetting({ monitoring_paused: !data.status.monitoring_paused })
                }
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors whitespace-nowrap"
              >
                {data.status.monitoring_paused ? (
                  <>
                    <Play className="w-3.5 h-3.5 text-emerald-600" />
                    Resume
                  </>
                ) : (
                  <>
                    <Pause className="w-3.5 h-3.5 text-slate-500" />
                    Pause
                  </>
                )}
              </button>
            )}

            <div className="relative">
              <button
                onClick={() => setNotifOpen((v) => !v)}
                className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 relative"
                aria-label="Notifications"
              >
                <Bell className="w-4 h-4" />
                {unreadAlerts.length > 0 && (
                  <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-600 text-white text-[10px] font-mono flex items-center justify-center">
                    {unreadAlerts.length}
                  </span>
                )}
              </button>

              {notifOpen && (
                <div className="absolute right-0 mt-2 w-80 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-lg p-4 z-50">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-slate-900 dark:text-slate-100">
                      Notifications ({data?.alerts.length || 0})
                    </span>
                    {unreadAlerts.length > 0 && (
                      <button
                        onClick={async () => {
                          await fetch('/api/alerts/ack', { method: 'POST' });
                          await refreshNow();
                        }}
                        className="text-xs text-sky-600 dark:text-sky-400 hover:underline"
                      >
                        Mark read
                      </button>
                    )}
                  </div>
                  {!data || data.alerts.length === 0 ? (
                    <p className="text-xs text-slate-500 dark:text-slate-400 py-3">
                      No data limit alerts triggered.
                    </p>
                  ) : (
                    <div className="max-h-64 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800 text-xs">
                      {data.alerts.slice(0, 8).map((a) => (
                        <div key={a.id} className="py-2">
                          <div className="text-slate-800 dark:text-slate-200">{a.message}</div>
                          <div className="font-mono text-[11px] text-slate-400 mt-0.5">
                            {formatDateTime(a.created_at)}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            <button
              onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
              className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
              aria-label="Toggle color theme"
            >
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>

            <button
              onClick={() => setSection('settings')}
              className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
              aria-label="Open Settings"
            >
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Main Viewport */}
        <main className="flex-1 p-4 sm:p-6 max-w-[1440px] w-full mx-auto">
          {error && !data ? (
            <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30 p-6 text-sm text-red-700 dark:text-red-300">
              Unable to reach NETSCOPE backend daemon: {error}
            </div>
          ) : !data ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                {[1, 2, 3, 4].map((n) => (
                  <div
                    key={n}
                    className="h-28 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 animate-pulse"
                  />
                ))}
              </div>
              <div className="h-72 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 animate-pulse" />
            </div>
          ) : (
            <>
              {section === 'overview' && (
                <OverviewView data={data} onNavigate={(target) => setSection(target)} />
              )}
              {section === 'live' && (
                <LiveMonitorView
                  data={data}
                  onIntervalChange={(sec) => updateSetting({ refresh_interval_sec: String(sec) })}
                />
              )}
              {section === 'applications' && <ApplicationsView data={data} />}
              {section === 'browser' && <BrowserView data={data} />}
              {section === 'interfaces' && <InterfacesView data={data} />}
              {(section === 'daily' ||
                section === 'weekly' ||
                section === 'monthly' ||
                section === 'historical') && (
                <AnalyticsView
                  mode={section}
                  data={data}
                  onRescanHistory={async () => {
                    await fetch('/api/history/import', { method: 'POST' });
                    await refreshNow();
                  }}
                />
              )}
              {section === 'limits' && (
                <DataLimitsView
                  data={data}
                  onCreateLimit={async (payload) => {
                    await fetch('/api/limits', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify(payload),
                    });
                    await refreshNow();
                  }}
                  onDeleteLimit={async (id) => {
                    await fetch(`/api/limits/${id}`, { method: 'DELETE' });
                    await refreshNow();
                  }}
                  onAckAlerts={async () => {
                    await fetch('/api/alerts/ack', { method: 'POST' });
                    await refreshNow();
                  }}
                />
              )}
              {section === 'settings' && (
                <SettingsView
                  data={data}
                  theme={theme}
                  onThemeChange={setTheme}
                  onUpdateSetting={updateSetting}
                  onBackup={async () => {
                    await fetch('/api/backup', { method: 'POST' });
                    await refreshNow();
                  }}
                />
              )}
              {section === 'about' && <AboutView data={data} />}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
