export type NavSection =
  | 'overview'
  | 'live'
  | 'applications'
  | 'browser'
  | 'interfaces'
  | 'daily'
  | 'weekly'
  | 'monthly'
  | 'historical'
  | 'limits'
  | 'settings'
  | 'about';

export interface SystemCapabilities {
  hostname: string;
  kernel_release: string;
  architecture: string;
  distro_name: string;
  uid: number;
  is_root: boolean;
  proc_net_dev: boolean;
  proc_net_sockets: boolean;
  proc_pid_fd: boolean;
  ip_addr_json: boolean;
  ss_available: boolean;
  ss_tcp_info_bytes: boolean;
  netlink_sock_diag: boolean;
  ebpf_btf: boolean;
  ebpf_bcc: boolean;
  nftables_available: boolean;
  conntrack_available: boolean;
  vnstat_db_available: boolean;
  networkmanager_available: boolean;
  notify_send_available: boolean;
  pyside6_available: boolean;
  per_process_byte_method: string;
  per_process_bytes_available: boolean;
  limitations: string[];
}

export interface SpeedPoint {
  ts_utc: string;
  rx_rate_bps: number;
  tx_rate_bps: number;
  rx_delta: number;
  tx_delta: number;
}

export interface IpAddressInfo {
  family: string;
  local: string;
  prefixlen: number;
  scope: string;
}

export interface NetworkInterfaceItem {
  iface: string;
  iface_type: 'wifi' | 'ethernet' | 'vpn' | 'loopback' | 'virtual' | 'other';
  status: string;
  ip_addresses: IpAddressInfo[];
  mac_address: string;
  mtu: number;
  boot_rx_bytes: number;
  boot_tx_bytes: number;
  recorded_rx_bytes: number;
  recorded_tx_bytes: number;
  rx_rate_bps: number;
  tx_rate_bps: number;
  updated_at: string;
}

export interface SocketConnection {
  proto: string;
  local: string;
  remote: string;
  state: string;
  scope: 'lan' | 'internet';
  iface: string;
  pid: number;
}

export interface ApplicationItem {
  app_id: string;
  app_name: string;
  exe_path: string;
  owner: string;
  pids: number[];
  status: 'running' | 'stopped';
  active_sockets: number;
  tcp_established: number;
  udp_active: number;
  lan_sockets: number;
  internet_sockets: number;
  rx_rate_bps: number | null;
  tx_rate_bps: number | null;
  total_rx_bytes: number | null;
  total_tx_bytes: number | null;
  bytes_available: boolean;
  measurement_source: string;
  connections: SocketConnection[];
  interfaces: string[];
  last_active_ts: string;
}

export interface BrowserTabItem {
  tab_key: string;
  browser_name: string;
  tab_id: string;
  tab_title: string;
  domain: string;
  is_active: number;
  rx_bytes: number;
  tx_bytes: number;
  rx_rate_bps: number;
  tx_rate_bps: number;
  accuracy_label: string;
  measurement_source: string;
  last_active_ts: string;
}

export interface NetworkEventItem {
  id: number;
  ts_utc: string;
  event_type: string;
  iface: string;
  details: string;
}

export interface DataLimitItem {
  id: number;
  name: string;
  period_type: 'daily' | 'weekly' | 'monthly' | 'custom';
  limit_bytes: number;
  custom_days: number;
  enabled: number;
  notify_desktop: number;
  consumed_bytes: number;
  percent_used: number;
  created_at: string;
}

export interface AlertEventItem {
  id: number;
  limit_id: number | null;
  threshold_pct: number;
  period_key: string;
  consumed_bytes: number;
  limit_bytes: number;
  message: string;
  acknowledged: number;
  created_at: string;
}

export interface HistoricalImportItem {
  id: number;
  source: string;
  period_label: string;
  start_ts: string | null;
  end_ts: string | null;
  iface: string;
  rx_bytes: number | null;
  tx_bytes: number | null;
  measurement_accuracy: string;
  measurement_type: string;
  import_status: string;
  notes: string;
  imported_at: string;
}

export interface PeriodSummary {
  total_rx_bytes: number;
  total_tx_bytes: number;
  total_bytes: number;
  active_days: number;
  daily_average_bytes: number;
  highest_day: { local_date: string; rx_bytes: number; tx_bytes: number; total_bytes: number } | null;
  most_consuming_app: {
    app_name: string;
    rx_bytes: number;
    tx_bytes: number;
    bytes_available: number;
    peak_sockets: number;
    note?: string;
  } | null;
  previous_period_bytes: number | null;
  percent_change_vs_previous: number | null;
}

export interface PeriodAnalyticsResponse {
  period: string;
  label: string;
  start_date: string;
  end_date: string;
  summary: PeriodSummary;
  daily_series: Array<{
    local_date: string;
    rx_bytes: number;
    tx_bytes: number;
    total_bytes: number;
    sources: string;
  }>;
  by_interface: Array<{
    iface: string;
    iface_type: string;
    rx_bytes: number;
    tx_bytes: number;
    total_bytes: number;
    is_vpn: number;
  }>;
  by_application: Array<{
    app_id: string;
    app_name: string;
    exe_path: string;
    owner: string;
    rx_bytes: number;
    tx_bytes: number;
    bytes_available: number;
    peak_sockets: number;
    last_active_ts: string;
    measurement_source: string;
  }>;
}

export interface DashboardPayload {
  status: {
    monitoring_paused: boolean;
    privacy_mode: boolean;
    connected: boolean;
    vpn_connected: boolean;
    active_interfaces: string[];
    current_rx_rate_bps: number;
    current_tx_rate_bps: number;
    daemon_alive: boolean;
    last_sample_ts: string | null;
  };
  capabilities: SystemCapabilities;
  settings: Record<string, string>;
  db_integrity: {
    status: string;
    ok: boolean;
    db_path: string;
    size_bytes: number;
    allocated_bytes: number;
  };
  overview: {
    today: PeriodSummary;
    last_7_days: PeriodSummary;
    this_month: PeriodSummary;
    lifetime: PeriodSummary;
    today_by_interface: Array<{
      iface: string;
      iface_type: string;
      rx_bytes: number;
      tx_bytes: number;
      total_bytes: number;
      is_vpn: number;
    }>;
  };
  speed_series: SpeedPoint[];
  interfaces: NetworkInterfaceItem[];
  applications: ApplicationItem[];
  browser_tabs: BrowserTabItem[];
  network_events: NetworkEventItem[];
  limits: DataLimitItem[];
  alerts: AlertEventItem[];
  historical_imports: HistoricalImportItem[];
}
