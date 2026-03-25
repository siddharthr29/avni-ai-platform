import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { UserProfilePicker } from '../UserProfilePicker';

describe('UserProfilePicker', () => {
  const mockOnLogin = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    mockOnLogin.mockClear();
  });

  it('renders the sign-in heading by default', () => {
    render(<UserProfilePicker onLogin={mockOnLogin} />);
    expect(screen.getByText('Sign in to Avni AI')).toBeInTheDocument();
  });

  it('renders email and password fields', () => {
    render(<UserProfilePicker onLogin={mockOnLogin} />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it('submit button is disabled when fields are empty', () => {
    render(<UserProfilePicker onLogin={mockOnLogin} />);
    const submitButton = screen.getByRole('button', { name: /sign in/i });
    expect(submitButton).toBeDisabled();
  });

  it('submit button is enabled with valid email and password', async () => {
    const user = userEvent.setup();
    render(<UserProfilePicker onLogin={mockOnLogin} />);

    await user.type(screen.getByLabelText(/email/i), 'test@example.org');
    await user.type(screen.getByLabelText(/password/i), 'password123');

    const submitButton = screen.getByRole('button', { name: /sign in/i });
    expect(submitButton).not.toBeDisabled();
  });

  it('handles login form submission', async () => {
    const user = userEvent.setup();
    render(<UserProfilePicker onLogin={mockOnLogin} />);

    await user.type(screen.getByLabelText(/email/i), 'test@example.org');
    await user.type(screen.getByLabelText(/password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(mockOnLogin).toHaveBeenCalledWith(
        expect.objectContaining({
          email: 'test@example.org',
          password: 'password123',
          isRegister: false,
        }),
      );
    });
  });

  it('switches to registration mode and shows additional fields', async () => {
    const user = userEvent.setup();
    render(<UserProfilePicker onLogin={mockOnLogin} />);

    await user.click(screen.getByText(/don't have an account/i));

    // 'Create Account' appears as both a heading and a button
    const matches = screen.getAllByText('Create Account');
    expect(matches).toHaveLength(2);
    expect(screen.getByLabelText(/your name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/organisation name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/sector/i)).toBeInTheDocument();
  });

  it('shows org context textarea in registration mode', async () => {
    const user = userEvent.setup();
    render(<UserProfilePicker onLogin={mockOnLogin} />);

    await user.click(screen.getByText(/don't have an account/i));
    expect(screen.getByLabelText(/about your organisation/i)).toBeInTheDocument();
  });

  it('input text has dark text color class', () => {
    render(<UserProfilePicker onLogin={mockOnLogin} />);
    const emailInput = screen.getByLabelText(/email/i);
    expect(emailInput.className).toContain('text-gray-900');
  });

  it('placeholder has gray color class', () => {
    render(<UserProfilePicker onLogin={mockOnLogin} />);
    const emailInput = screen.getByLabelText(/email/i);
    expect(emailInput.className).toContain('placeholder:text-gray-400');
  });

  it('registration submit is disabled without required fields', async () => {
    const user = userEvent.setup();
    render(<UserProfilePicker onLogin={mockOnLogin} />);

    await user.click(screen.getByText(/don't have an account/i));

    await user.type(screen.getByLabelText(/email/i), 'test@example.org');
    await user.type(screen.getByLabelText(/password/i), 'password123');
    // Missing name, org, sector

    const submitButton = screen.getByRole('button', { name: /create account/i });
    expect(submitButton).toBeDisabled();
  });

  it('displays error message on login failure', async () => {
    const user = userEvent.setup();
    mockOnLogin.mockRejectedValueOnce(new Error('Invalid credentials'));
    render(<UserProfilePicker onLogin={mockOnLogin} />);

    await user.type(screen.getByLabelText(/email/i), 'test@example.org');
    await user.type(screen.getByLabelText(/password/i), 'wrongpass');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText('Invalid credentials')).toBeInTheDocument();
    });
  });
});
