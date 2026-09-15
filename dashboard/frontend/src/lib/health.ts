/**
 * Client-side health score: a single 0-100 number, computed only from fields the API already
 * returns (`OverviewResponse` + `ConfigView`) — never a backend-computed or fabricated value.
 * Weights and thresholds below are named constants so the formula stays auditable, not buried
 * in arithmetic.
 */
import type { ConfigView, HealthStatus, OverviewResponse } from "../api/types";
import type { Severity } from "../components/StatusBadge";
import { formatRelative } from "./format";

export interface HealthComponent {
  id: "dns" | "latency" | "blocklist" | "system" | "backup";
  label: string;
  score: number;
  severity: Severity;
  detail: string;
}

export type HealthBand = "ottimo" | "buono" | "attenzione" | "critico";

export interface HealthScore {
  score: number;
  band: HealthBand;
  bandLabel: string;
  components: HealthComponent[];
}

const WEIGHTS: Record<HealthComponent["id"], number> = {
  dns: 30,
  latency: 15,
  blocklist: 20,
  system: 20,
  backup: 15,
};

// No backend "expected backup interval" setting exists (out of scope for this phase's backend
// additions), so this stays a named constant here rather than invented backend state.
const EXPECTED_BACKUP_INTERVAL_HOURS = 26; // 24h daily cadence + 2h grace
const OPEN_INCIDENT_PENALTY = 5;
const MAX_INCIDENT_PENALTY = 15;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function severityFor(score: number): Severity {
  if (score >= 80) return "ok";
  if (score >= 40) return "warning";
  return "critical";
}

function dnsComponent(status: HealthStatus): HealthComponent {
  const score = status === "ok" ? 100 : status === "degraded" ? 50 : 0;
  const detail =
    status === "ok" ? "operativo" : status === "degraded" ? "degradato" : "non risponde";
  return { id: "dns", label: "DNS", score, severity: severityFor(score), detail };
}

function latencyComponent(p95Ms: number | null): HealthComponent | null {
  if (p95Ms === null) return null;
  let score: number;
  if (p95Ms <= 40) score = 100;
  else if (p95Ms <= 120) score = 100 - ((p95Ms - 40) / 80) * 50;
  else if (p95Ms <= 300) score = 50 - ((p95Ms - 120) / 180) * 40;
  else score = 10;
  score = clamp(score, 10, 100); // slow is never scored as down — that's the DNS component's job
  return {
    id: "latency",
    label: "Risoluzione",
    score,
    severity: severityFor(score),
    detail: `p95 ${Math.round(p95Ms)}ms`,
  };
}

/** 100 within the expected interval, degrading to 0 by 4x the expected interval. */
function freshnessRatioScore(hoursSince: number, expectedHours: number): number {
  const ratio = hoursSince / expectedHours;
  if (ratio <= 1) return 100;
  if (ratio <= 2) return 100 - (ratio - 1) * 50;
  if (ratio <= 4) return 50 - ((ratio - 2) / 2) * 50;
  return 0;
}

function blocklistComponent(config: ConfigView | null, now: Date): HealthComponent | null {
  if (config === null || config.blocklist_sources.length === 0) return null;
  let worst: { score: number; name: string; lastActivatedAt: string | null } | null = null;
  for (const source of config.blocklist_sources) {
    const score =
      source.last_activated_at === null
        ? 0
        : freshnessRatioScore(
            (now.getTime() - new Date(source.last_activated_at).getTime()) / 3_600_000,
            source.update_interval_hours
          );
    if (worst === null || score < worst.score) {
      worst = { score, name: source.name, lastActivatedAt: source.last_activated_at };
    }
  }
  const picked = worst as { score: number; name: string; lastActivatedAt: string | null };
  return {
    id: "blocklist",
    label: "Blocklist",
    score: picked.score,
    severity: severityFor(picked.score),
    detail: `${picked.name}: ${formatRelative(picked.lastActivatedAt, now)}`,
  };
}

function systemComponent(system: OverviewResponse["system"]): HealthComponent | null {
  if (system === null) return null;
  const cpuScore = system.cpu_percent <= 50 ? 100 : system.cpu_percent <= 85 ? 40 : 0;
  const memPercent = (system.memory_used_bytes / system.memory_total_bytes) * 100;
  const memScore = memPercent <= 50 ? 100 : memPercent <= 85 ? 40 : 0;
  const temp = system.temperature_celsius ?? null;
  const tempScore = temp === null ? 100 : temp <= 60 ? 100 : temp <= 75 ? 40 : 0;
  const score = Math.round((cpuScore + memScore + tempScore) / 3);
  const details = [`CPU ${Math.round(system.cpu_percent)}%`, `RAM ${Math.round(memPercent)}%`];
  if (temp !== null) details.push(`${Math.round(temp)}°C`);
  return {
    id: "system",
    label: "Sistema",
    score,
    severity: severityFor(score),
    detail: details.join(" · "),
  };
}

function backupComponent(lastBackupAt: string | null, now: Date): HealthComponent {
  const score =
    lastBackupAt === null
      ? 0
      : freshnessRatioScore(
          (now.getTime() - new Date(lastBackupAt).getTime()) / 3_600_000,
          EXPECTED_BACKUP_INTERVAL_HOURS
        );
  return {
    id: "backup",
    label: "Backup",
    score,
    severity: severityFor(score),
    detail: formatRelative(lastBackupAt, now),
  };
}

function bandFor(score: number): { band: HealthBand; label: string } {
  if (score >= 90) return { band: "ottimo", label: "Ottimo" };
  if (score >= 75) return { band: "buono", label: "Buono" };
  if (score >= 50) return { band: "attenzione", label: "Attenzione" };
  return { band: "critico", label: "Critico" };
}

export function computeHealth(
  overview: OverviewResponse,
  config: ConfigView | null,
  now: Date = new Date()
): HealthScore {
  const components = [
    dnsComponent(overview.provider.status),
    latencyComponent(overview.last_24h.latency_p95_ms),
    blocklistComponent(config, now),
    systemComponent(overview.system),
    backupComponent(overview.last_backup_at, now),
  ].filter((c): c is HealthComponent => c !== null);

  // A component with no data is excluded and its weight redistributed — absence of data never
  // masquerades as a specific score.
  const totalWeight = components.reduce((sum, c) => sum + WEIGHTS[c.id], 0);
  const weighted =
    totalWeight === 0
      ? 100
      : components.reduce((sum, c) => sum + c.score * (WEIGHTS[c.id] / totalWeight), 0);

  const penalty = Math.min(overview.open_incidents, 3) * OPEN_INCIDENT_PENALTY;
  const score = Math.round(clamp(weighted - Math.min(penalty, MAX_INCIDENT_PENALTY), 0, 100));
  const { band, label } = bandFor(score);

  return { score, band, bandLabel: label, components };
}
