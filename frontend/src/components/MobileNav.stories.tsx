import type { Meta, StoryObj } from '@storybook/react-vite';
import MobileNav from './MobileNav';

const meta: Meta<typeof MobileNav> = {
  title: 'Components/MobileNav',
  component: MobileNav,
  parameters: {
    viewport: { defaultViewport: 'mobile1' },
    layout: 'fullscreen',
  },
};

export default meta;
type Story = StoryObj<typeof MobileNav>;

export const Default: Story = {};
