/** Avni logo component using the real PNG assets.
 *
 * `variant="icon"` — just the circles icon (favicon.png)
 * `variant="full"` — icon + "Avni" wordmark (avni-logo.png)
 */

interface AvniLogoProps {
  size?: number;
  className?: string;
  variant?: 'icon' | 'full';
}

export function AvniLogo({ size = 36, className = '', variant = 'icon' }: AvniLogoProps) {
  const src = variant === 'full' ? '/avni-logo.png' : '/favicon.png';
  return (
    <img
      src={src}
      alt="Avni"
      height={size}
      style={{ height: `${size}px`, width: 'auto' }}
      className={className}
    />
  );
}
