import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { LandingPage } from '../LandingPage';

describe('LandingPage', () => {
  it('renders hero heading text', () => {
    render(<LandingPage onStart={vi.fn()} />);
    expect(screen.getByText(/Set up your Avni app/i)).toBeInTheDocument();
    expect(screen.getByText(/in hours, not weeks/i)).toBeInTheDocument();
  });

  it('renders the AI-Powered Implementation tagline', () => {
    render(<LandingPage onStart={vi.fn()} />);
    expect(screen.getByText('AI-Powered Implementation')).toBeInTheDocument();
  });

  it('calls onStart when Sign In button is clicked', async () => {
    const user = userEvent.setup();
    const onStart = vi.fn();
    render(<LandingPage onStart={onStart} />);

    const signInButton = screen.getByRole('button', { name: /sign in/i });
    await user.click(signInButton);
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it('calls onStart when Get Started button is clicked', async () => {
    const user = userEvent.setup();
    const onStart = vi.fn();
    render(<LandingPage onStart={onStart} />);

    const getStartedButton = screen.getByRole('button', { name: /get started/i });
    await user.click(getStartedButton);
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it('renders About button and calls onAbout when clicked', async () => {
    const user = userEvent.setup();
    const onAbout = vi.fn();
    render(<LandingPage onStart={vi.fn()} onAbout={onAbout} />);

    const aboutButtons = screen.getAllByRole('button', { name: /about|learn more/i });
    expect(aboutButtons.length).toBeGreaterThan(0);
    await user.click(aboutButtons[0]);
    expect(onAbout).toHaveBeenCalledTimes(1);
  });

  it('renders all 6 feature cards', () => {
    render(<LandingPage onStart={vi.fn()} />);

    expect(screen.getByText('Generate Bundles')).toBeInTheDocument();
    expect(screen.getByText('Chat with AI')).toBeInTheDocument();
    expect(screen.getByText('Write Rules')).toBeInTheDocument();
    expect(screen.getByText('Validate Before Deploy')).toBeInTheDocument();
    expect(screen.getByText('Multiple AI Providers')).toBeInTheDocument();
    expect(screen.getByText('India-Ready')).toBeInTheDocument();
  });

  it('renders the "What you can do" section heading', () => {
    render(<LandingPage onStart={vi.fn()} />);
    expect(screen.getByText('What you can do')).toBeInTheDocument();
  });

  it('renders footer with avniproject.org link', () => {
    render(<LandingPage onStart={vi.fn()} />);
    const link = screen.getByRole('link', { name: /avniproject\.org/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', 'https://avniproject.org');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('does not render About/Learn More buttons when onAbout is not provided', () => {
    render(<LandingPage onStart={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /^about$/i })).not.toBeInTheDocument();
    expect(screen.queryByText('About this project')).not.toBeInTheDocument();
  });
});
