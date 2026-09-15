import type { HealthComponent } from "../lib/health";
import { StatusBadge } from "./StatusBadge";

const BADGE_LABEL: Record<HealthComponent["severity"], string> = {
  ok: "OK",
  warning: "Attenzione",
  critical: "Critico",
  unknown: "Sconosciuto",
};

/** Breaks the health ring's single number down into its components, so the reason behind the
 * score is immediately clear — never just a bare percentage. */
export function HealthLedger({ components }: { components: HealthComponent[] }) {
  return (
    <ul className="health-ledger">
      {components.map((component) => (
        <li key={component.id} className="health-ledger__row">
          <span
            aria-hidden="true"
            className={`health-ledger__dot health-ledger__dot--${component.severity}`}
          />
          <span className="health-ledger__label">
            {component.label}
            <span className="health-ledger__detail">{component.detail}</span>
          </span>
          <StatusBadge severity={component.severity} label={BADGE_LABEL[component.severity]} />
        </li>
      ))}
    </ul>
  );
}
