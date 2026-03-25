import type { Meta, StoryObj } from '@storybook/react-vite';
import UserProfilePicker from './UserProfilePicker';

const meta: Meta<typeof UserProfilePicker> = {
  title: 'Components/UserProfilePicker',
  component: UserProfilePicker,
  parameters: {
    layout: 'centered',
  },
};

export default meta;
type Story = StoryObj<typeof UserProfilePicker>;

export const Default: Story = {};
