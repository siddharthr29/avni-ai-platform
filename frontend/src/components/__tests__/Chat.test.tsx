import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Chat } from '../Chat';
import type { Message, UserProfile } from '../../types';

// Mock child components that have complex dependencies
vi.mock('../ChatMessage', () => ({
  ChatMessage: ({ message }: { message: Message }) => (
    <div data-testid={`message-${message.id}`} data-role={message.role}>
      {message.content}
    </div>
  ),
}));

vi.mock('../ChatInput', () => ({
  ChatInput: ({ onSendMessage, isLoading }: { onSendMessage: (msg: string) => void; isLoading: boolean }) => (
    <div data-testid="chat-input">
      <textarea
        data-testid="message-input"
        placeholder="Type / for commands, or ask a question..."
        disabled={isLoading}
      />
      <button
        data-testid="send-button"
        disabled={isLoading}
        onClick={() => onSendMessage('test')}
        aria-label="Send message"
      >
        Send
      </button>
    </div>
  ),
  SLASH_COMMANDS: [],
}));

vi.mock('../VoiceCapture', () => ({
  VoiceCapture: () => <div data-testid="voice-capture" />,
}));

vi.mock('../ImageUpload', () => ({
  ImageUpload: () => <div data-testid="image-upload" />,
}));

vi.mock('../FormContext', () => ({
  FormContextPanel: () => null,
}));

vi.mock('../ArtifactPanel', () => ({
  ArtifactPanel: () => null,
}));

vi.mock('../SpreadsheetEditor', () => ({
  parseCSVToSpreadsheet: vi.fn(),
  spreadsheetToCSV: vi.fn(),
}));

vi.mock('../AvniLogo', () => ({
  AvniLogo: () => <div data-testid="avni-logo" />,
}));

const mockOnToast = vi.fn();
const mockOnSendMessage = vi.fn();

const sampleMessages: Message[] = [
  {
    id: 'msg-1',
    role: 'user',
    content: 'Hello, how do I create a bundle?',
    timestamp: new Date(),
  },
  {
    id: 'msg-2',
    role: 'assistant',
    content: 'To create a bundle, you can use the /bundle command.',
    timestamp: new Date(),
  },
];

describe('Chat', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock the health check fetch
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), { status: 200 }),
    );
  });

  it('renders the message input area', () => {
    render(
      <Chat
        messages={[]}
        isLoading={false}
        onSendMessage={mockOnSendMessage}
        onToast={mockOnToast}
      />,
    );
    expect(screen.getByTestId('chat-input')).toBeInTheDocument();
  });

  it('renders empty state with suggestions when no messages', () => {
    render(
      <Chat
        messages={[]}
        isLoading={false}
        onSendMessage={mockOnSendMessage}
        onToast={mockOnToast}
      />,
    );
    expect(screen.getByText(/Welcome to Avni AI/i)).toBeInTheDocument();
  });

  it('shows personalized greeting when profile is provided', () => {
    const profile: UserProfile = {
      id: 'u1',
      name: 'Priya Sharma',
      email: 'priya@test.org',
      orgName: 'Test',
      sector: 'Health',
      orgContext: '',
      role: 'implementor',
      isActive: true,
      createdAt: '',
      accessToken: '',
      refreshToken: '',
    };
    render(
      <Chat
        messages={[]}
        isLoading={false}
        onSendMessage={mockOnSendMessage}
        onToast={mockOnToast}
        profile={profile}
      />,
    );
    expect(screen.getByText(/Hello, Priya/i)).toBeInTheDocument();
  });

  it('renders message bubbles when messages exist', () => {
    render(
      <Chat
        messages={sampleMessages}
        isLoading={false}
        onSendMessage={mockOnSendMessage}
        onToast={mockOnToast}
      />,
    );
    expect(screen.getByTestId('message-msg-1')).toBeInTheDocument();
    expect(screen.getByTestId('message-msg-2')).toBeInTheDocument();
  });

  it('renders user and assistant messages with correct content', () => {
    render(
      <Chat
        messages={sampleMessages}
        isLoading={false}
        onSendMessage={mockOnSendMessage}
        onToast={mockOnToast}
      />,
    );
    expect(screen.getByText(/Hello, how do I create a bundle/)).toBeInTheDocument();
    expect(screen.getByText(/To create a bundle/)).toBeInTheDocument();
  });

  it('shows loading progress bar when isLoading is true', () => {
    const { container } = render(
      <Chat
        messages={sampleMessages}
        isLoading={true}
        onSendMessage={mockOnSendMessage}
        onToast={mockOnToast}
      />,
    );
    const progressBar = container.querySelector('.progress-bar');
    expect(progressBar).toBeInTheDocument();
  });

  it('does not show progress bar when not loading', () => {
    const { container } = render(
      <Chat
        messages={sampleMessages}
        isLoading={false}
        onSendMessage={mockOnSendMessage}
        onToast={mockOnToast}
      />,
    );
    const progressBar = container.querySelector('.progress-bar');
    expect(progressBar).not.toBeInTheDocument();
  });

  it('renders suggestion categories in empty state', () => {
    render(
      <Chat
        messages={[]}
        isLoading={false}
        onSendMessage={mockOnSendMessage}
        onToast={mockOnToast}
      />,
    );
    expect(screen.getByText('Build')).toBeInTheDocument();
    expect(screen.getByText('Learn')).toBeInTheDocument();
    expect(screen.getByText('Support')).toBeInTheDocument();
  });
});
