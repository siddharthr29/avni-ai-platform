import { cn } from '../lib/utils';

// ── Types ────────────────────────────────────────────────────────────────────

export interface ProviderBadgeProps {
  provider: string;
  model: string;
  latencyMs: number;
  costUsd: number;
  className?: string;
}

// ── Component ────────────────────────────────────────────────────────────────

export function ProviderBadge({
  provider,
  model,
  latencyMs,
  costUsd,
  className,
}: ProviderBadgeProps) {
  const latencyFormatted = latencyMs >= 1000
    ? `${(latencyMs / 1000).toFixed(1)}s`
    : `${Math.round(latencyMs)}ms`;

  const costFormatted = costUsd >= 0.01
    ? `$${costUsd.toFixed(2)}`
    : `$${costUsd.toFixed(3)}`;

  const displayModel = model || provider;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600',
        className
      )}
      title={`${provider} ${model} - ${latencyFormatted} - ${costFormatted}`}
    >
      <span className="font-medium">{displayModel}</span>
      <Separator />
      <span className="tabular-nums">{latencyFormatted}</span>
      <Separator />
      <span className="tabular-nums">{costFormatted}</span>
    </span>
  );
}

function Separator() {
  return <span className="text-gray-400" aria-hidden="true">&middot;</span>;
}
