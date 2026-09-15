/** Italian-locale formatting shared across pages. */

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" });
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

export function formatNumber(n: number): string {
  return n.toLocaleString("it-IT");
}

export function formatPercent(n: number): string {
  return `${n.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`;
}

export function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toLocaleString("it-IT", { maximumFractionDigits: 1 })} ${units[unitIndex]}`;
}

export function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (days) parts.push(`${days}g`);
  if (days || hours) parts.push(`${hours}h`);
  parts.push(`${minutes}m`);
  return parts.join(" ");
}

export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  return ms < 1 ? `${(ms * 1000).toFixed(0)} µs` : `${ms.toLocaleString("it-IT")} ms`;
}

/** "4h fa" / "2g fa" style relative time, or "mai" for a null timestamp. */
export function formatRelative(iso: string | null, now: Date = new Date()): string {
  if (iso === null) return "mai";
  const hours = (now.getTime() - new Date(iso).getTime()) / 3_600_000;
  if (hours < 1) return "meno di 1h fa";
  if (hours < 24) return `${Math.floor(hours)}h fa`;
  return `${Math.floor(hours / 24)}g fa`;
}
