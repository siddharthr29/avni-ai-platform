import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { PlatformStatsView } from '../PlatformStats';
import type { PlatformStats } from '../../../types';

vi.mock('../../../services/api', () => ({
  fetchPlatformStats: vi.fn(),
}));

import { fetchPlatformStats } from '../../../services/api';

const mockStats: PlatformStats = {
  totalUsers: 150,
  activeUsers: 120,
  usersByRole: {
    ngo_user: 80,
    implementor: 40,
    org_admin: 20,
    platform_admin: 10,
  },
  usersByOrg: {
    'Sangwari': 30,
    'JSS': 25,
    'CInI': 20,
  },
  totalSessions: 500,
  recentMessages24h: 45,
  recentMessages7d: 230,
  recentMessages30d: 900,
};

const mockOnToast = vi.fn();

describe('PlatformStatsView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchPlatformStats).mockResolvedValue(mockStats);
  });

  it('shows loading state initially', () => {
    vi.mocked(fetchPlatformStats).mockReturnValue(new Promise(() => {}));
    render(<PlatformStatsView onToast={mockOnToast} />);
    expect(screen.getByText('Loading platform stats...')).toBeInTheDocument();
  });

  it('renders stat cards with correct values', async () => {
    render(<PlatformStatsView onToast={mockOnToast} />);

    await waitFor(() => {
      expect(screen.getByText('150')).toBeInTheDocument();
    });
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('500')).toBeInTheDocument();
    // '45' appears in both the stat card and the Messages Activity section,
    // so use getAllByText to avoid the duplicate element error.
    const matches45 = screen.getAllByText('45');
    expect(matches45).toHaveLength(2);
  });

  it('renders stat card labels', async () => {
    render(<PlatformStatsView onToast={mockOnToast} />);

    await waitFor(() => {
      expect(screen.getByText('Total Users')).toBeInTheDocument();
    });
    expect(screen.getByText('Active Users')).toBeInTheDocument();
    expect(screen.getByText('Total Sessions')).toBeInTheDocument();
    expect(screen.getByText('Messages (24h)')).toBeInTheDocument();
  });

  it('shows messages activity section', async () => {
    render(<PlatformStatsView onToast={mockOnToast} />);

    await waitFor(() => {
      expect(screen.getByText('Messages Activity')).toBeInTheDocument();
    });
    expect(screen.getByText('Last 24 hours')).toBeInTheDocument();
    expect(screen.getByText('Last 7 days')).toBeInTheDocument();
  });

  it('shows top organizations', async () => {
    render(<PlatformStatsView onToast={mockOnToast} />);

    await waitFor(() => {
      expect(screen.getByText('Top Organizations')).toBeInTheDocument();
    });
    expect(screen.getByText('Sangwari')).toBeInTheDocument();
    expect(screen.getByText('JSS')).toBeInTheDocument();
    expect(screen.getByText('CInI')).toBeInTheDocument();
  });

  it('shows users by role section', async () => {
    render(<PlatformStatsView onToast={mockOnToast} />);

    await waitFor(() => {
      expect(screen.getByText('Users by Role')).toBeInTheDocument();
    });
    expect(screen.getByText('NGO Users')).toBeInTheDocument();
    expect(screen.getByText('Implementors')).toBeInTheDocument();
    expect(screen.getByText('Org Admins')).toBeInTheDocument();
    expect(screen.getByText('Platform Admins')).toBeInTheDocument();
  });

  it('handles error state when stats fail to load', async () => {
    vi.mocked(fetchPlatformStats).mockRejectedValue(new Error('Network error'));
    render(<PlatformStatsView onToast={mockOnToast} />);

    await waitFor(() => {
      expect(mockOnToast).toHaveBeenCalledWith(
        'error',
        expect.stringContaining('Failed to load stats'),
      );
    });
    // Should show the error fallback
    expect(screen.getByText('Unable to load platform statistics.')).toBeInTheDocument();
  });
});
