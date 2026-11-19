export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) {
    return 'Not available';
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let val = Math.max(0, bytes);
  let idx = 0;
  while (val >= 1024 && idx < units.length - 1) {
    val /= 1024;
    idx++;
  }
  if (idx === 0) return `${Math.round(val)} B`;
  return `${val.toFixed(2)} ${units[idx]}`;
}

export function formatSpeed(bps: number | null | undefined): string {
  if (bps === null || bps === undefined || Number.isNaN(bps)) {
    return 'Unavailable';
  }
  return `${formatBytes(bps)}/s`;
}

export function formatTimeShort(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function ifaceTypeLabel(t: string): string {
  switch (t) {
    case 'wifi':
      return 'Wi-Fi';
    case 'ethernet':
      return 'Ethernet';
    case 'vpn':
      return 'VPN Tunnel';
    case 'loopback':
      return 'Loopback';
    case 'virtual':
      return 'Virtual / Bridge';
    default:
      return 'Other';
  }
}
