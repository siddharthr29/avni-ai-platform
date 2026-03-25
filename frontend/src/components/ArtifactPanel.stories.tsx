import type { Meta, StoryObj } from '@storybook/react-vite';
import ArtifactPanel from './ArtifactPanel';

const meta: Meta<typeof ArtifactPanel> = {
  title: 'Components/ArtifactPanel',
  component: ArtifactPanel,
  parameters: {
    layout: 'padded',
  },
};

export default meta;
type Story = StoryObj<typeof ArtifactPanel>;

export const WithJSON: Story = {
  args: {
    artifact: {
      type: 'json',
      title: 'Sample Bundle',
      content: JSON.stringify({ concepts: [{ name: 'Weight', dataType: 'Numeric' }] }, null, 2),
    },
  },
};

export const WithCode: Story = {
  args: {
    artifact: {
      type: 'code',
      title: 'Sample Rule',
      content: 'const getStatusOfChild = (child) => {\n  const weight = child.getObservationValue("Weight");\n  return weight < 2.5 ? "Underweight" : "Normal";\n};',
    },
  },
};
