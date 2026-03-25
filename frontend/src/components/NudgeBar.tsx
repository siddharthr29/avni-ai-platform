import { useEffect, useState } from 'react';
import { X, Volume2, VolumeX, Smartphone, Bell, BellOff, Sparkles } from 'lucide-react';
import type { Nudge } from '../hooks/useFeedback';

// ── Nudge Toast ──────────────────────────────────────────────────────────

interface NudgeToastProps {
  nudge: Nudge;
  onDismiss: (id: string) => void;
}

function NudgeToast({ nudge, onDismiss }: NudgeToastProps) {
  const [show, setShow] = useState(false);

  useEffect(() => {
    // Animate in
    requestAnimationFrame(() => setShow(true));
  }, []);

  const style = {
    tip: 'bg-blue-900 border-blue-700 text-blue-100',
    progress: 'bg-emerald-900 border-emerald-700 text-emerald-100',
    celebration: 'bg-amber-900 border-amber-700 text-amber-100',
    suggestion: 'bg-gray-900 border-gray-700 text-gray-100',
  }[nudge.type];

  return (
    <div
      className={`
        flex items-center gap-2 px-4 py-2.5 rounded-lg border shadow-lg
        transition-all duration-300 ease-out max-w-sm
        ${style}
        ${show ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'}
      `}
    >
      <span className="text-sm flex-1">{nudge.message}</span>
      <button
        onClick={() => onDismiss(nudge.id)}
        className="text-gray-400 hover:text-white flex-shrink-0"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

// ── Nudge Bar (floating container for all nudges) ────────────────────────

interface NudgeBarProps {
  nudges: Nudge[];
  onDismiss: (id: string) => void;
}

export function NudgeBar({ nudges, onDismiss }: NudgeBarProps) {
  if (nudges.length === 0) return null;

  return (
    <div className="fixed bottom-20 right-4 z-50 flex flex-col gap-2 items-end pointer-events-none">
      {nudges.map(nudge => (
        <div key={nudge.id} className="pointer-events-auto">
          <NudgeToast nudge={nudge} onDismiss={onDismiss} />
        </div>
      ))}
    </div>
  );
}

// ── Celebration Overlay ──────────────────────────────────────────────────

interface CelebrationOverlayProps {
  show: boolean;
  message?: string;
}

export function CelebrationOverlay({ show, message = 'Bundle Ready!' }: CelebrationOverlayProps) {
  const [particles, setParticles] = useState<Array<{ id: number; x: number; y: number; color: string; delay: number }>>([]);

  useEffect(() => {
    if (!show) {
      setParticles([]);
      return;
    }

    // Generate confetti particles
    const colors = ['#10B981', '#3B82F6', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#14B8A6'];
    const newParticles = Array.from({ length: 50 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      color: colors[Math.floor(Math.random() * colors.length)],
      delay: Math.random() * 0.5,
    }));
    setParticles(newParticles);
  }, [show]);

  if (!show) return null;

  return (
    <div className="fixed inset-0 z-[100] pointer-events-none flex items-center justify-center">
      {/* Confetti particles */}
      {particles.map(p => (
        <div
          key={p.id}
          className="absolute w-2 h-2 rounded-full animate-confetti"
          style={{
            left: `${p.x}%`,
            top: `-5%`,
            backgroundColor: p.color,
            animationDelay: `${p.delay}s`,
            animationDuration: `${1.5 + Math.random()}s`,
          }}
        />
      ))}

      {/* Center message */}
      <div className="animate-bounce-in bg-white rounded-2xl shadow-2xl px-8 py-6 flex flex-col items-center gap-3 pointer-events-auto">
        <Sparkles className="w-10 h-10 text-amber-500 animate-spin-slow" />
        <h2 className="text-2xl font-bold text-gray-900">{message}</h2>
        <p className="text-gray-500 text-sm">Your Avni implementation bundle is ready to download</p>
      </div>
    </div>
  );
}

// ── Feedback Settings Toggle (small icon bar) ────────────────────────────

interface FeedbackSettingsProps {
  soundEnabled: boolean;
  hapticEnabled: boolean;
  nudgesEnabled: boolean;
  onToggleSound: () => void;
  onToggleHaptic: () => void;
  onToggleNudges: () => void;
}

export function FeedbackSettings({
  soundEnabled, hapticEnabled, nudgesEnabled,
  onToggleSound, onToggleHaptic, onToggleNudges,
}: FeedbackSettingsProps) {
  return (
    <div className="flex items-center gap-1">
      <button
        onClick={onToggleSound}
        className={`p-1.5 rounded-md transition-colors ${
          soundEnabled
            ? 'text-emerald-600 bg-emerald-50'
            : 'text-gray-400 hover:text-gray-600'
        }`}
        title={soundEnabled ? 'Sound ON' : 'Sound OFF'}
      >
        {soundEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
      </button>
      <button
        onClick={onToggleHaptic}
        className={`p-1.5 rounded-md transition-colors ${
          hapticEnabled
            ? 'text-emerald-600 bg-emerald-50'
            : 'text-gray-400 hover:text-gray-600'
        }`}
        title={hapticEnabled ? 'Haptics ON' : 'Haptics OFF'}
      >
        <Smartphone className="w-4 h-4" />
      </button>
      <button
        onClick={onToggleNudges}
        className={`p-1.5 rounded-md transition-colors ${
          nudgesEnabled
            ? 'text-emerald-600 bg-emerald-50'
            : 'text-gray-400 hover:text-gray-600'
        }`}
        title={nudgesEnabled ? 'Nudges ON' : 'Nudges OFF'}
      >
        {nudgesEnabled ? <Bell className="w-4 h-4" /> : <BellOff className="w-4 h-4" />}
      </button>
    </div>
  );
}
