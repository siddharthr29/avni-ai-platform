import { useState, useCallback } from 'react';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { Chat } from './components/Chat';
import { useChat } from './hooks/useChat';

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const {
    messages,
    sessions,
    currentSessionId,
    isLoading,
    sendMessage,
    startNewSession,
    switchSession,
  } = useChat();

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
    // Start a new session if none exists, then send the action as a message
    if (!currentSessionId) {
      startNewSession();
    }

    const actionMessages: Record<string, string> = {
      'Generate Bundle': 'I want to generate an Avni implementation bundle. Can you help me get started?',
      'Voice Capture': 'I want to capture field data using voice input. Please help me set this up.',
      'Upload Image': 'I have an image of a register/form that I want to extract data from.',
      'Get Help': 'I need help with my Avni implementation. Can you guide me?',
    };

    const message = actionMessages[action] ?? action;
    sendMessage(message);

    // Close sidebar on mobile after action
    if (window.innerWidth < 768) {
      setSidebarOpen(false);
    }
  }, [currentSessionId, startNewSession, sendMessage]);

  return (
    <div className="flex h-full bg-white">
      <Sidebar
        sessions={sessions}
        currentSessionId={currentSessionId}
        isOpen={sidebarOpen}
        onNewChat={handleNewChat}
        onSelectSession={switchSession}
        onClose={handleCloseSidebar}
        onQuickAction={handleQuickAction}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <Header onToggleSidebar={handleToggleSidebar} />
        <Chat
          messages={messages}
          isLoading={isLoading}
          onSendMessage={sendMessage}
        />
      </div>
    </div>
  );
}

export default App;
