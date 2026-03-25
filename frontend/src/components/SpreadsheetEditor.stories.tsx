import type { Meta, StoryObj } from '@storybook/react-vite';
import SpreadsheetEditor from './SpreadsheetEditor';

const meta: Meta<typeof SpreadsheetEditor> = {
  title: 'Components/SpreadsheetEditor',
  component: SpreadsheetEditor,
  parameters: {
    layout: 'padded',
  },
};

export default meta;
type Story = StoryObj<typeof SpreadsheetEditor>;

export const Empty: Story = {
  args: {
    data: 'Name,Age,Role\n',
  },
};

export const WithData: Story = {
  args: {
    data: 'Name,Age,Role\nJohn,30,Developer\nJane,25,Designer\nBob,35,Manager\n',
  },
};
