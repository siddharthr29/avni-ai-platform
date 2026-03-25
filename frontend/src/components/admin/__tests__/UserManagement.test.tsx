import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { UserManagement } from '../UserManagement';
import type { UserProfile, AdminUser } from '../../../types';

// Mock the API module
vi.mock('../../../services/api', () => ({
  fetchAdminUsers: vi.fn(),
  updateUserRole: vi.fn(),
  updateUserStatus: vi.fn(),
  deleteUser: vi.fn(),
}));

import { fetchAdminUsers, deleteUser } from '../../../services/api';

const mockProfile: UserProfile = {
  id: 'admin-1',
  name: 'Admin User',
  email: 'admin@test.org',
  orgName: 'Test Org',
  sector: 'Health',
  orgContext: '',
  role: 'platform_admin',
  isActive: true,
  createdAt: '2024-01-01',
  accessToken: 'tok',
  refreshToken: 'ref',
};

const mockUsers: AdminUser[] = [
  {
    id: 'user-1',
    name: 'Alice Smith',
    email: 'alice@test.org',
    orgName: 'Org A',
    sector: 'Health',
    role: 'implementor',
    isActive: true,
    lastLogin: '2024-06-01',
    createdAt: '2024-01-01',
  },
  {
    id: 'user-2',
    name: 'Bob Jones',
    email: 'bob@test.org',
    orgName: 'Org B',
    sector: 'Education',
    role: 'ngo_user',
    isActive: false,
    lastLogin: null,
    createdAt: '2024-02-01',
  },
];

const mockOnToast = vi.fn();

describe('UserManagement', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchAdminUsers).mockResolvedValue({ users: mockUsers, total: 2 });
  });

  it('shows loading spinner initially', () => {
    vi.mocked(fetchAdminUsers).mockReturnValue(new Promise(() => {})); // never resolves
    render(<UserManagement profile={mockProfile} onToast={mockOnToast} />);
    expect(screen.getByText('Loading users...')).toBeInTheDocument();
  });

  it('renders user table with data', async () => {
    render(<UserManagement profile={mockProfile} onToast={mockOnToast} />);

    await waitFor(() => {
      expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    });
    expect(screen.getByText('Bob Jones')).toBeInTheDocument();
    expect(screen.getByText('alice@test.org')).toBeInTheDocument();
    expect(screen.getByText('bob@test.org')).toBeInTheDocument();
  });

  it('shows "No users found" when empty', async () => {
    vi.mocked(fetchAdminUsers).mockResolvedValue({ users: [], total: 0 });
    render(<UserManagement profile={mockProfile} onToast={mockOnToast} />);

    await waitFor(() => {
      expect(screen.getByText('No users found')).toBeInTheDocument();
    });
  });

  it('has a search input', async () => {
    render(<UserManagement profile={mockProfile} onToast={mockOnToast} />);
    const searchInput = screen.getByPlaceholderText(/search by name or email/i);
    expect(searchInput).toBeInTheDocument();
  });

  it('search input triggers re-fetch with search term', async () => {
    const user = userEvent.setup();
    render(<UserManagement profile={mockProfile} onToast={mockOnToast} />);

    await waitFor(() => {
      expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/search by name or email/i);
    await user.type(searchInput, 'Alice');

    await waitFor(() => {
      expect(fetchAdminUsers).toHaveBeenCalledWith(
        expect.objectContaining({ search: 'Alice' }),
      );
    });
  });

  it('role filter dropdown is present', async () => {
    render(<UserManagement profile={mockProfile} onToast={mockOnToast} />);

    await waitFor(() => {
      expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    });

    const roleSelect = screen.getByDisplayValue('All Roles');
    expect(roleSelect).toBeInTheDocument();
  });

  it('status filter dropdown is present', async () => {
    render(<UserManagement profile={mockProfile} onToast={mockOnToast} />);

    await waitFor(() => {
      expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    });

    const statusSelect = screen.getByDisplayValue('All Status');
    expect(statusSelect).toBeInTheDocument();
  });

  it('Invite User button is present', async () => {
    render(<UserManagement profile={mockProfile} onToast={mockOnToast} />);

    await waitFor(() => {
      expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /invite user/i })).toBeInTheDocument();
  });

  it('delete button shows confirmation flow', async () => {
    const user = userEvent.setup();
    render(<UserManagement profile={mockProfile} onToast={mockOnToast} />);

    await waitFor(() => {
      expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    });

    // Find delete button (trash icon) for a user
    const deleteButtons = screen.getAllByTitle('Delete user');
    expect(deleteButtons.length).toBeGreaterThan(0);

    await user.click(deleteButtons[0]);

    // Should show confirmation
    expect(screen.getByText('Confirm')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('confirms deletion and calls deleteUser', async () => {
    const user = userEvent.setup();
    vi.mocked(deleteUser).mockResolvedValue({ success: true });
    render(<UserManagement profile={mockProfile} onToast={mockOnToast} />);

    await waitFor(() => {
      expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByTitle('Delete user');
    await user.click(deleteButtons[0]);
    await user.click(screen.getByText('Confirm'));

    await waitFor(() => {
      expect(deleteUser).toHaveBeenCalled();
    });
  });
});
