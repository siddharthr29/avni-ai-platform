import type { Meta, StoryObj } from '@storybook/react-vite';
import Chat from './Chat';

const meta: Meta<typeof Chat> = {
  title: 'Components/Chat',
  component: Chat,
  parameters: {
    layout: 'fullscreen',
  },
};

export default meta;
type Story = StoryObj<typeof Chat>;

export const Default: Story = {};

export const WithSessionId: Story = {
  args: {
    sessionId: 'test-session-123',
  },
};
