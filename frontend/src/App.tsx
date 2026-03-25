import { useState, useCallback, useEffect, useRef, lazy, Suspense } from 'react';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { Chat } from './components/Chat';
import { ToastContainer } from './components/Toast';
import { LandingPage } from './components/LandingPage';
import { ErrorBoundary } from './components/ErrorBoundary';
import { UserProfilePicker } from './components/UserProfilePicker';
import { SkipToContent } from './components/SkipToContent';
import { AccessibilityProvider } from './components/AccessibilityProvider';
import { ToastProvider, useToast } from './contexts/ToastContext';
import { ProfileProvider } from './contexts/ProfileContext';
import { I18nProvider } from './i18n/I18nProvider';
import { useFeedback } from './hooks/useFeedback';
import { NudgeBar, CelebrationOverlay, FeedbackSettings } from './components/NudgeBar';

// Lazy-load heavy views to reduce initial bundle size (Joy: performance)
const SRSBuilder = lazy(() => import('./components/srs/SRSBuilder.tsx').then(m => ({ default: m.SRSBuilder })));
const DocsViewer = lazy(() => import('./components/DocsViewer').then(m => ({ default: m.DocsViewer })));
const AdminPanel = lazy(() => import('./components/admin/AdminPanel').then(m => ({ default: m.AdminPanel })));
const AboutPage = lazy(() => import('./components/AboutPage').then(m => ({ default: m.AboutPage })));
import { useChat } from './hooks/useChat';
import { useUserProfile } from './hooks/useUserProfile';
import type { SlashCommand } from './components/ChatInput';
import type { SRSData } from './types';

function LoadingFallback() {
  return (
    <div className="flex items-center justify-center h-full bg-white">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-primary-600 border-t-transparent rounded-full spinner mx-auto mb-3" />
        <p className="text-sm text-gray-500">Loading...</p>
      </div>
    </div>
  );
}

function AppContent() {
  const { profile, login, updateProfile, logout } = useUserProfile();
  const [showLanding, setShowLanding] = useState(() => !profile);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [view, setView] = useState<'chat' | 'srs' | 'docs' | 'admin' | 'about'>('chat');
  const { toasts, addToast, dismissToast } = useToast();
  const feedback = useFeedback();
  const {
    messages,
    sessions,
    currentSessionId,
    isLoading,
    sendMessage,
    startNewSession,
    switchSession,
    deleteSession,
    // SRS mode
    srsMode,
    srsData,
    srsPhase,
    srsBundleStatus,
    srsBundleId,
    setSrsData,
    startSrsMode,
    stopSrsMode,
    generateSrsBundle,
  } = useChat(profile?.id ?? null, profile);

  const handleToggleSidebar = useCallback(() => {
    setSidebarOpen(prev => !prev);
  }, []);

  const handleCloseSidebar = useCallback(() => {
    setSidebarOpen(false);
  }, []);

  const handleNewChat = useCallback(() => {
    startNewSession();
  }, [startNewSession]);

  const handleQuickAction = useCallback((action: string) => {
    if (action === 'Generate Bundle') {
      setView('srs');
      return;
    }
    if (action === 'Chat Builder') {
      // Activate SRS mode within the existing chat — no separate view
      setView('chat');
      startSrsMode();
      if (window.innerWidth < 768) {
        setSidebarOpen(false);
      }
      return;
    }

    if (!currentSessionId) {
      startNewSession();
    }

    const actionMessages: Record<string, string> = {
      'Voice Capture': 'I want to capture field data using voice input. Please help me set this up.',
      'Upload Image': 'I have an image of a register/form that I want to extract data from.',
      'Get Help': 'I need help with my Avni implementation. Can you guide me?',
    };

    const message = actionMessages[action] ?? action;
    sendMessage(message);

    if (window.innerWidth < 768) {
      setSidebarOpen(false);
    }
  }, [currentSessionId, startNewSession, sendMessage, startSrsMode]);

  const handleEnterApp = useCallback(() => {
    setShowLanding(false);
  }, []);

  const handleGoHome = useCallback(() => {
    setShowLanding(true);
  }, []);

  const handleLogout = useCallback(async () => {
    await logout();
    setShowLanding(true);
  }, [logout]);

  // ── Feedback triggers for SRS state changes ──────────────────────────────
  const prevSrsPhaseRef = useRef(srsPhase);
  const prevBundleStatusRef = useRef(srsBundleStatus);

  useEffect(() => {
    if (srsPhase !== prevSrsPhaseRef.current && srsPhase !== 'start') {
      feedback.onPhaseAdvanced(srsPhase);
      feedback.showPhaseNudge(srsPhase);
    }
    prevSrsPhaseRef.current = srsPhase;
  }, [srsPhase, feedback]);

  useEffect(() => {
    if (srsBundleStatus === 'done' && prevBundleStatusRef.current !== 'done') {
      feedback.onBundleReady();
    }
    if (srsBundleStatus === 'error' && prevBundleStatusRef.current !== 'error') {
      feedback.onError('Bundle generation failed');
    }
    prevBundleStatusRef.current = srsBundleStatus;
  }, [srsBundleStatus, feedback]);

  // Listen for SRS section highlights and trigger section-built feedback
  useEffect(() => {
    const handler = (e: Event) => {
      const section = (e as CustomEvent).detail?.section;
      if (section) {
        const sectionNames: Record<string, string> = {
          organization: 'Organization', subjects: 'Subject Types', programs: 'Programs',
          forms: 'Forms', scheduling: 'Visit Scheduling', dashboard: 'Dashboard',
          permissions: 'Permissions',
        };
        feedback.onSectionBuilt(sectionNames[section] || section);
      }
    };
    window.addEventListener('srs-highlight-section', handler);
    return () => window.removeEventListener('srs-highlight-section', handler);
  }, [feedback]);

  // Listen for backend-triggered actions (e.g. "open SRS builder")
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.action === 'open_srs_builder') {
        setView('chat');
        startSrsMode();
      }
    };
    window.addEventListener('avni-action', handler);
    return () => window.removeEventListener('avni-action', handler);
  }, [startSrsMode]);

  // Update document title based on view (Mahalakshme: documentation quality)
  useEffect(() => {
    const titles: Record<string, string> = {
      chat: srsMode ? 'Avni AI — SRS Chat Builder' : 'Avni AI — Chat',
      srs: 'Avni AI — SRS Builder',
      docs: 'Avni AI — Documentation',
      admin: 'Avni AI — Admin Panel',
      about: 'Avni AI — About',
    };
    document.title = showLanding ? 'Avni AI Platform' : (titles[view] || 'Avni AI');
  }, [view, showLanding]);

  // Keyboard shortcuts
  useEffect(() => {
    if (showLanding || !profile) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      const isMod = e.metaKey || e.ctrlKey;

      if (isMod && e.key === 'k') {
        e.preventDefault();
        const textarea = document.querySelector<HTMLTextAreaElement>(
          'textarea[placeholder="Type a message..."]'
        );
        textarea?.focus();
      }

      if (isMod && e.key === 'n') {
        e.preventDefault();
        startNewSession();
      }

      if (e.key === 'Escape') {
        if (sidebarOpen && window.innerWidth < 768) {
          setSidebarOpen(false);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showLanding, profile, startNewSession, sidebarOpen]);

  const handleCloseSRSBuilder = useCallback(() => {
    setView('chat');
  }, []);

  const handleOpenDocs = useCallback(() => {
    setView('docs');
  }, []);

  const handleCloseDocs = useCallback(() => {
    setView('chat');
  }, []);

  const handleOpenAdmin = useCallback(() => {
    if (profile?.role === 'platform_admin' || profile?.role === 'org_admin') {
      setView('admin');
    }
  }, [profile?.role]);

  const handleCloseAdmin = useCallback(() => {
    setView('chat');
  }, []);

  const handleOpenAbout = useCallback(() => {
    setView('about');
  }, []);

  const handleCloseAbout = useCallback(() => {
    setView('chat');
  }, []);

  const handleSlashCommand = useCallback((command: SlashCommand) => {
    if (command.viewAction === 'srs') {
      setView('srs');
    } else if (command.viewAction === 'docs') {
      setView('docs');
    }
  }, []);

  const handleGenerateBundle = useCallback((_srsData: SRSData) => {
    setView('chat');
    if (!currentSessionId) {
      startNewSession();
    }
    sendMessage('Generate an Avni implementation bundle from the SRS data I just completed.');
    addToast('success', 'SRS data submitted for bundle generation');
  }, [currentSessionId, startNewSession, sendMessage, addToast]);

  // Show landing page for new visitors
  if (showLanding && !profile) {
    if (view === 'about') {
      return (
        <Suspense fallback={<LoadingFallback />}>
          <AboutPage onClose={() => setView('chat')} />
        </Suspense>
      );
    }
    return <LandingPage onStart={handleEnterApp} onAbout={handleOpenAbout} />;
  }

  // Show user profile picker after landing (or if no profile)
  if (!profile) {
    return <UserProfilePicker onLogin={login} />;
  }

  // Show landing page for returning users who clicked home
  if (showLanding) {
    if (view === 'about') {
      return (
        <Suspense fallback={<LoadingFallback />}>
          <AboutPage onClose={() => setView('chat')} />
        </Suspense>
      );
    }
    return <LandingPage onStart={handleEnterApp} onAbout={handleOpenAbout} />;
  }

  if (view === 'about') {
    return (
      <Suspense fallback={<LoadingFallback />}>
        <AboutPage onClose={handleCloseAbout} />
      </Suspense>
    );
  }

  if (view === 'admin' && profile && (profile.role === 'platform_admin' || profile.role === 'org_admin')) {
    return (
      <Suspense fallback={<LoadingFallback />}>
        <AdminPanel onClose={handleCloseAdmin} profile={profile} onToast={addToast} />
      </Suspense>
    );
  }

  if (view === 'docs') {
    return (
      <Suspense fallback={<LoadingFallback />}>
        <DocsViewer onClose={handleCloseDocs} />
      </Suspense>
    );
  }

  if (view === 'srs') {
    return (
      <ErrorBoundary sectionName="SRS Builder">
        <Suspense fallback={<LoadingFallback />}>
          <SRSBuilder
            onClose={handleCloseSRSBuilder}
            onGenerateBundle={handleGenerateBundle}
            orgName={profile?.orgName}
            sector={profile?.sector}
          />
        </Suspense>
      </ErrorBoundary>
    );
  }

  return (
    <ProfileProvider profile={profile} updateProfile={updateProfile} logout={logout}>
      <ErrorBoundary>
        <SkipToContent />
        <div className="flex h-screen overflow-hidden bg-white">
          <ErrorBoundary sectionName="Sidebar">
            <Sidebar
              sessions={sessions}
              currentSessionId={currentSessionId}
              isOpen={sidebarOpen}
              onNewChat={handleNewChat}
              onSelectSession={switchSession}
              onDeleteSession={deleteSession}
              onClose={handleCloseSidebar}
              onQuickAction={handleQuickAction}
            />
          </ErrorBoundary>

          <div id="main-content" className="flex-1 flex flex-col min-w-0 overflow-hidden">
            <div className="flex items-center shrink-0">
              <div className="flex-1 min-w-0">
                <Header
                  onToggleSidebar={handleToggleSidebar}
                  onGoHome={handleGoHome}
                  onOpenDocs={handleOpenDocs}
                  onOpenAdmin={handleOpenAdmin}
                  onOpenAbout={handleOpenAbout}
                  profile={profile}
                  onLogout={handleLogout}
                  onUpdateProfile={updateProfile}
                  onToast={addToast}
                />
              </div>
              <div className="pr-2 hidden sm:block">
                <FeedbackSettings
                  soundEnabled={feedback.settings.soundEnabled}
                  hapticEnabled={feedback.settings.hapticEnabled}
                  nudgesEnabled={feedback.settings.nudgesEnabled}
                  onToggleSound={feedback.toggleSound}
                  onToggleHaptic={feedback.toggleHaptic}
                  onToggleNudges={feedback.toggleNudges}
                />
              </div>
            </div>
            <ErrorBoundary sectionName="Chat">
              <Chat
                messages={messages}
                isLoading={isLoading}
                onSendMessage={sendMessage}
                onCommand={handleSlashCommand}
                onToast={addToast}
                profile={profile}
                currentSessionId={currentSessionId}
                srsMode={srsMode}
                srsData={srsData}
                srsPhase={srsPhase}
                srsBundleStatus={srsBundleStatus}
                srsBundleId={srsBundleId}
                onSrsChange={setSrsData}
                onGenerateSrsBundle={generateSrsBundle}
                onStopSrsMode={stopSrsMode}
                feedback={feedback}
              />
            </ErrorBoundary>
          </div>

          <ToastContainer toasts={toasts} onDismiss={dismissToast} />
          <NudgeBar nudges={feedback.nudges} onDismiss={feedback.dismissNudge} />
          <CelebrationOverlay show={feedback.celebration} />
        </div>
      </ErrorBoundary>
    </ProfileProvider>
  );
}

function App() {
  return (
    <I18nProvider>
      <AccessibilityProvider>
        <ToastProvider>
          <AppContent />
        </ToastProvider>
      </AccessibilityProvider>
    </I18nProvider>
  );
}

export default App;
