/** Hand-authored inline SVG icon set — no icon library, matches the rest of the codebase's
 * "no dependency for what a few lines can do" pattern (see charts/*.tsx). */
import type { SVGProps } from "react";

export interface IconProps extends SVGProps<SVGSVGElement> {
  size?: number;
}

function base({ size = 18, ...props }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none" as const,
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    ...props,
  };
}

export function IconOverview(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3" y="3" width="8" height="8" rx="1.5" />
      <rect x="13" y="3" width="8" height="8" rx="1.5" />
      <rect x="3" y="13" width="8" height="8" rx="1.5" />
      <rect x="13" y="13" width="8" height="8" rx="1.5" />
    </svg>
  );
}

export function IconDevices(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3" y="4" width="18" height="12" rx="1.5" />
      <path d="M8 20h8M12 16v4" />
    </svg>
  );
}

export function IconSecurity(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" />
    </svg>
  );
}

export function IconSystem(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="6" y="6" width="12" height="12" rx="2" />
      <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" />
    </svg>
  );
}

export function IconAlerts(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M6 10a6 6 0 1112 0c0 4 1.5 5.5 2 6H4c.5-.5 2-2 2-6z" />
      <path d="M10 20a2 2 0 004 0" />
    </svg>
  );
}

export function IconQueries(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="4.5" cy="6" r="1" />
      <circle cx="4.5" cy="12" r="1" />
      <circle cx="4.5" cy="18" r="1" />
      <path d="M9 6h11M9 12h11M9 18h11" />
    </svg>
  );
}

export function IconRefresh(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M3 12a9 9 0 0115-6.7M21 12a9 9 0 01-15 6.7" />
      <path d="M17 3v5h-5M7 21v-5h5" />
    </svg>
  );
}

export function IconSearch(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.3-4.3" />
    </svg>
  );
}

export function IconBell(props: IconProps) {
  return <IconAlerts {...props} />;
}

export function IconChevron(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}

export function IconBackup(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M7 18a4 4 0 01-.5-8 5.5 5.5 0 0110.7-1.7A4.5 4.5 0 0117 18H7z" />
      <path d="M12 12v7M9.5 16.5L12 19l2.5-2.5" />
    </svg>
  );
}

export function IconBlocklist(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

export function IconPulse(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M2 12h4l2-7 4 14 2-7h8" />
    </svg>
  );
}

export function IconLock(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="5" y="10" width="14" height="10" rx="2" />
      <path d="M8 10V7a4 4 0 018 0v3" />
    </svg>
  );
}

export function IconMenu(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M3 6h18M3 12h18M3 18h18" />
    </svg>
  );
}

export function IconX(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  );
}
