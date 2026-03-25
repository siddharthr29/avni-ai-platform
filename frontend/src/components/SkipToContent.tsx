/**
 * SkipToContent — WCAG 2.1 AA compliant "Skip to main content" link.
 *
 * Visually hidden by default, becomes visible when focused via keyboard (Tab).
 * Allows keyboard users and screen reader users to bypass repetitive navigation.
 */
export function SkipToContent() {
  return (
    <a
      href="#main-content"
      className="
        fixed top-0 left-0 z-[9999]
        px-6 py-3
        bg-teal-700 text-white font-semibold text-sm
        rounded-br-lg shadow-lg
        transform -translate-y-full
        focus:translate-y-0
        transition-transform duration-200
        outline-none focus:ring-2 focus:ring-teal-400 focus:ring-offset-2
      "
    >
      Skip to main content
    </a>
  );
}
