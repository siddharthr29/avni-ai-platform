import { useCallback, useRef, useState, useEffect } from 'react';

// ── Web Audio Synthesized Sounds (no audio files needed) ──────────────────

const audioCtxRef = { current: null as AudioContext | null };

function getAudioCtx(): AudioContext {
  if (!audioCtxRef.current) {
    audioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
  }
  return audioCtxRef.current;
}

function playTone(frequency: number, duration: number, type: OscillatorType = 'sine', volume: number = 0.15) {
  try {
    const ctx = getAudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(frequency, ctx.currentTime);
    gain.gain.setValueAtTime(volume, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + duration);
  } catch {
    // Audio not available — silent fail
  }
}

// Sound presets
const sounds = {
  // Soft "ding" — SRS section updated
  sectionBuilt: () => {
    playTone(880, 0.15, 'sine', 0.12);
    setTimeout(() => playTone(1100, 0.2, 'sine', 0.08), 100);
  },

  // Level-up chime — phase advanced
  phaseAdvanced: () => {
    playTone(523, 0.12, 'sine', 0.1);
    setTimeout(() => playTone(659, 0.12, 'sine', 0.1), 120);
    setTimeout(() => playTone(784, 0.2, 'sine', 0.12), 240);
  },

  // Success fanfare — bundle ready
  bundleReady: () => {
    playTone(523, 0.15, 'sine', 0.12);
    setTimeout(() => playTone(659, 0.15, 'sine', 0.12), 150);
    setTimeout(() => playTone(784, 0.15, 'sine', 0.12), 300);
    setTimeout(() => playTone(1047, 0.3, 'sine', 0.15), 450);
  },

  // Low thud — error
  error: () => {
    playTone(150, 0.3, 'triangle', 0.2);
  },

  // Soft click — message sent
  messageSent: () => {
    playTone(600, 0.05, 'sine', 0.06);
  },

  // Subtle pop — message received
  messageReceived: () => {
    playTone(800, 0.08, 'sine', 0.05);
  },

  // Welcome chime
  welcome: () => {
    playTone(440, 0.15, 'sine', 0.08);
    setTimeout(() => playTone(554, 0.15, 'sine', 0.08), 200);
    setTimeout(() => playTone(659, 0.25, 'sine', 0.1), 400);
  },

  // Click for field/item added
  itemAdded: () => {
    playTone(1000, 0.06, 'sine', 0.08);
  },
};

// ── Haptics (Navigator.vibrate API) ───────────────────────────────────────

const haptics = {
  // Short pulse — item built
  light: () => { try { navigator.vibrate?.(10); } catch { /* not supported */ } },

  // Medium pulse — section built
  medium: () => { try { navigator.vibrate?.(25); } catch { /* not supported */ } },

  // Double pulse — phase advanced
  double: () => { try { navigator.vibrate?.([20, 50, 20]); } catch { /* not supported */ } },

  // Long vibration — bundle ready
  success: () => { try { navigator.vibrate?.([30, 50, 30, 50, 60]); } catch { /* not supported */ } },

  // Triple short — error
  error: () => { try { navigator.vibrate?.([50, 30, 50, 30, 50]); } catch { /* not supported */ } },
};

// ── Nudge System ──────────────────────────────────────────────────────────

export interface Nudge {
  id: string;
  message: string;
  type: 'tip' | 'progress' | 'celebration' | 'suggestion';
  icon?: string;
  autoDismissMs?: number;
}

// Contextual nudge suggestions per SRS phase
const PHASE_NUDGES: Record<string, string[]> = {
  start: [
    'Tell me your organization name and what sector you work in',
    'You can say something like "We are an NGO working on maternal health in Bihar"',
  ],
  org: [
    'Describe your geographic coverage — which states, districts?',
    'What location levels do you use? (State > District > Block > Village)',
  ],
  subjects: [
    'Who do you track? Individuals, households, groups?',
    'Most health programs track Individual beneficiaries',
  ],
  programs: [
    'What programs do you run? e.g., Maternal Health, Child Nutrition',
    'Each program can have its own enrollment and visit forms',
  ],
  encounters: [
    'What visits happen in each program? How often?',
    'e.g., "ANC visits happen monthly, PNC at day 1, 3, 7, 42"',
  ],
  forms: [
    'For each form, describe what fields you need to capture',
    'I\'ll suggest standard fields based on your sector',
  ],
  scheduling: [
    'How often should each visit be scheduled?',
    'Tell me the frequency and when it becomes overdue',
  ],
  dashboard: [
    'What indicators do you need on the mobile dashboard?',
    'Common: total registered, due visits, overdue, high-risk cases',
  ],
  review: [
    'Review everything above — anything to change?',
    'When you\'re ready, click "Generate Bundle" in the panel',
  ],
};

// Idle nudge suggestions (shown after 30s of inactivity)
const IDLE_NUDGES = [
  'You can ask me anything about Avni — forms, programs, visit scheduling...',
  'Need help? Try: "What fields should I capture for ANC visits?"',
  'You can edit any section directly by clicking the pencil icon',
  'Tip: I can suggest standard fields based on your sector',
];

// ── The Hook ──────────────────────────────────────────────────────────────

interface FeedbackSettings {
  soundEnabled: boolean;
  hapticEnabled: boolean;
  nudgesEnabled: boolean;
}

const SETTINGS_KEY = 'avni-feedback-settings';

function loadSettings(): FeedbackSettings {
  try {
    const saved = localStorage.getItem(SETTINGS_KEY);
    if (saved) return JSON.parse(saved);
  } catch { /* ignore */ }
  return { soundEnabled: false, hapticEnabled: true, nudgesEnabled: true }; // Sound OFF by default
}

function saveSettings(settings: FeedbackSettings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch { /* ignore */ }
}

export type FeedbackAPI = ReturnType<typeof useFeedback>;

export function useFeedback() {
  const [settings, setSettings] = useState<FeedbackSettings>(loadSettings);
  const [nudges, setNudges] = useState<Nudge[]>([]);
  const [celebration, setCelebration] = useState(false);
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nudgeCountRef = useRef(0);

  // Persist settings
  useEffect(() => {
    saveSettings(settings);
  }, [settings]);

  // Toggle settings
  const toggleSound = useCallback(() => {
    setSettings(prev => {
      const next = { ...prev, soundEnabled: !prev.soundEnabled };
      // Play a test tone when enabling
      if (next.soundEnabled) {
        setTimeout(() => playTone(660, 0.1, 'sine', 0.1), 50);
      }
      return next;
    });
  }, []);

  const toggleHaptic = useCallback(() => {
    setSettings(prev => {
      const next = { ...prev, hapticEnabled: !prev.hapticEnabled };
      if (next.hapticEnabled) haptics.light();
      return next;
    });
  }, []);

  const toggleNudges = useCallback(() => {
    setSettings(prev => ({ ...prev, nudgesEnabled: !prev.nudgesEnabled }));
  }, []);

  // ── Nudge management ──

  const addNudge = useCallback((nudge: Omit<Nudge, 'id'>) => {
    const id = `nudge-${Date.now()}-${nudgeCountRef.current++}`;
    const newNudge = { ...nudge, id };
    setNudges(prev => [...prev.slice(-4), newNudge]); // Keep max 5
    if (nudge.autoDismissMs) {
      setTimeout(() => {
        setNudges(prev => prev.filter(n => n.id !== id));
      }, nudge.autoDismissMs);
    }
  }, []);

  const dismissNudge = useCallback((id: string) => {
    setNudges(prev => prev.filter(n => n.id !== id));
  }, []);

  // ── Idle timer ──

  const resetIdleTimer = useCallback(() => {
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    if (!settings.nudgesEnabled) return;
    idleTimerRef.current = setTimeout(() => {
      const msg = IDLE_NUDGES[Math.floor(Math.random() * IDLE_NUDGES.length)];
      addNudge({
        message: `\uD83D\uDCA1 ${msg}`,
        type: 'suggestion',
        autoDismissMs: 10000,
      });
    }, 30000); // 30 seconds of inactivity
  }, [settings.nudgesEnabled, addNudge]);

  // Start idle timer on mount
  useEffect(() => {
    resetIdleTimer();
    return () => {
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    };
  }, [resetIdleTimer]);

  // ── Feedback triggers ──

  const onSectionBuilt = useCallback((sectionName?: string) => {
    if (settings.soundEnabled) sounds.sectionBuilt();
    if (settings.hapticEnabled) haptics.medium();
    if (settings.nudgesEnabled && sectionName) {
      addNudge({
        message: `\u2728 ${sectionName} updated!`,
        type: 'progress',
        autoDismissMs: 2500,
      });
    }
  }, [settings.soundEnabled, settings.hapticEnabled, settings.nudgesEnabled, addNudge]);

  const onPhaseAdvanced = useCallback((phase: string) => {
    if (settings.soundEnabled) sounds.phaseAdvanced();
    if (settings.hapticEnabled) haptics.double();
    if (settings.nudgesEnabled) {
      const phaseNames: Record<string, string> = {
        org: 'Organization', subjects: 'Subject Types', programs: 'Programs',
        encounters: 'Encounters', forms: 'Forms', scheduling: 'Visit Scheduling',
        dashboard: 'Dashboard', review: 'Review',
      };
      addNudge({
        message: `\uD83C\uDFAF Moving to ${phaseNames[phase] || phase}`,
        type: 'progress',
        autoDismissMs: 3000,
      });
    }
  }, [settings.soundEnabled, settings.hapticEnabled, settings.nudgesEnabled, addNudge]);

  const onBundleReady = useCallback(() => {
    if (settings.soundEnabled) sounds.bundleReady();
    if (settings.hapticEnabled) haptics.success();
    setCelebration(true);
    setTimeout(() => setCelebration(false), 4000);
  }, [settings.soundEnabled, settings.hapticEnabled]);

  const onError = useCallback((message?: string) => {
    if (settings.soundEnabled) sounds.error();
    if (settings.hapticEnabled) haptics.error();
    if (settings.nudgesEnabled && message) {
      addNudge({
        message: `\u26A0\uFE0F ${message}`,
        type: 'tip',
        autoDismissMs: 4000,
      });
    }
  }, [settings.soundEnabled, settings.hapticEnabled, settings.nudgesEnabled, addNudge]);

  const onMessageSent = useCallback(() => {
    if (settings.soundEnabled) sounds.messageSent();
    if (settings.hapticEnabled) haptics.light();
    resetIdleTimer();
  }, [settings.soundEnabled, settings.hapticEnabled, resetIdleTimer]);

  const onMessageReceived = useCallback(() => {
    if (settings.soundEnabled) sounds.messageReceived();
  }, [settings.soundEnabled]);

  const onWelcome = useCallback(() => {
    if (settings.soundEnabled) sounds.welcome();
  }, [settings.soundEnabled]);

  const onItemAdded = useCallback(() => {
    if (settings.soundEnabled) sounds.itemAdded();
    if (settings.hapticEnabled) haptics.light();
  }, [settings.soundEnabled, settings.hapticEnabled]);

  const showPhaseNudge = useCallback((phase: string) => {
    if (!settings.nudgesEnabled) return;
    const suggestions = PHASE_NUDGES[phase];
    if (suggestions && suggestions.length > 0) {
      const msg = suggestions[Math.floor(Math.random() * suggestions.length)];
      addNudge({
        message: `\uD83D\uDCA1 ${msg}`,
        type: 'suggestion',
        autoDismissMs: 8000,
      });
    }
  }, [settings.nudgesEnabled, addNudge]);

  return {
    // Settings
    settings,
    toggleSound,
    toggleHaptic,
    toggleNudges,

    // Triggers
    onSectionBuilt,
    onPhaseAdvanced,
    onBundleReady,
    onError,
    onMessageSent,
    onMessageReceived,
    onWelcome,
    onItemAdded,

    // Nudges
    nudges,
    addNudge,
    dismissNudge,
    showPhaseNudge,

    // Celebration
    celebration,
  };
}
