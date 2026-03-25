import { useState, useEffect, useCallback } from 'react';
import { Search, UserPlus, Trash2, ChevronLeft, ChevronRight } from 'lucide-react';
import { fetchAdminUsers, updateUserRole, updateUserStatus, deleteUser } from '../../services/api';
import { InviteUserModal } from './InviteUserModal';
import type { AdminUser, UserProfile, UserRole } from '../../types';

interface UserManagementProps {
  profile: UserProfile;
  onToast: (type: 'success' | 'error' | 'info', message: string) => void;
}

const ROLE_COLORS: Record<string, string> = {
  ngo_user: 'bg-gray-100 text-gray-700',
  implementor: 'bg-blue-100 text-blue-700',
  org_admin: 'bg-amber-100 text-amber-700',
  platform_admin: 'bg-red-100 text-red-700',
};

const ROLE_LABELS: Record<string, string> = {
  ngo_user: 'NGO User',
  implementor: 'Implementor',
  org_admin: 'Org Admin',
  platform_admin: 'Platform Admin',
};

const ALL_ROLES: UserRole[] = ['ngo_user', 'implementor', 'org_admin', 'platform_admin'];
const PAGE_SIZE = 20;

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function UserManagement({ profile, onToast }: UserManagementProps) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<'' | 'active' | 'inactive'>('');
  const [offset, setOffset] = useState(0);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const filters: Record<string, unknown> = { offset, limit: PAGE_SIZE };
      if (search.trim()) filters.search = search.trim();
      if (roleFilter) filters.role = roleFilter;
      if (statusFilter === 'active') filters.isActive = true;
      if (statusFilter === 'inactive') filters.isActive = false;

      const result = await fetchAdminUsers(filters as Parameters<typeof fetchAdminUsers>[0]);
      setUsers(result.users);
      setTotal(result.total);
    } catch (err) {
      onToast('error', `Failed to load users: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  }, [search, roleFilter, statusFilter, offset, onToast]);

  useEffect(() => {
    const timer = setTimeout(() => loadUsers(), 300);
    return () => clearTimeout(timer);
  }, [loadUsers]);

  const handleRoleChange = async (userId: string, newRole: string) => {
    try {
      await updateUserRole(userId, newRole);
      onToast('success', 'User role updated');
      loadUsers();
    } catch (err) {
      onToast('error', `Failed to update role: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  const handleStatusToggle = async (userId: string, currentActive: boolean) => {
    try {
      await updateUserStatus(userId, !currentActive);
      onToast('success', `User ${currentActive ? 'deactivated' : 'activated'}`);
      loadUsers();
    } catch (err) {
      onToast('error', `Failed to update status: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  const handleDelete = async (userId: string) => {
    try {
      await deleteUser(userId);
      onToast('success', 'User deleted');
      setDeleteConfirm(null);
      loadUsers();
    } catch (err) {
      onToast('error', `Failed to delete user: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  const availableRoles = profile.role === 'org_admin'
    ? ALL_ROLES.filter(r => r === 'ngo_user' || r === 'implementor')
    : ALL_ROLES;

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="max-w-6xl mx-auto">
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-4">
        {/* Search */}
        <div className="relative flex-1 w-full sm:max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={e => { setSearch(e.target.value); setOffset(0); }}
            placeholder="Search by name or email..."
            className="w-full pl-9 pr-3 py-2 text-sm bg-white border border-gray-200 rounded-lg text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
          />
        </div>

        {/* Filters */}
        <select
          value={roleFilter}
          onChange={e => { setRoleFilter(e.target.value); setOffset(0); }}
          className="px-3 py-2 text-sm bg-white border border-gray-200 rounded-lg text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="">All Roles</option>
          {ALL_ROLES.map(r => (
            <option key={r} value={r}>{ROLE_LABELS[r]}</option>
          ))}
        </select>

        <select
          value={statusFilter}
          onChange={e => { setStatusFilter(e.target.value as typeof statusFilter); setOffset(0); }}
          className="px-3 py-2 text-sm bg-white border border-gray-200 rounded-lg text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="">All Status</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>

        {/* Action Buttons */}
        <div className="flex items-center gap-2 ml-auto">
          <button
            onClick={() => setShowInviteModal(true)}
            className="flex items-center gap-1.5 px-3 py-2 text-sm bg-primary-600 hover:bg-primary-700 text-white rounded-lg transition-colors font-medium"
          >
            <UserPlus className="w-4 h-4" />
            Invite User
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-1.5 px-3 py-2 text-sm bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 rounded-lg transition-colors font-medium"
          >
            <UserPlus className="w-4 h-4" />
            Create User
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Email</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 hidden md:table-cell">Org</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Role</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 hidden lg:table-cell">Last Login</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-gray-400">
                    <div className="w-6 h-6 border-2 border-primary-600 border-t-transparent rounded-full spinner mx-auto mb-2" />
                    Loading users...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-gray-400">
                    No users found
                  </td>
                </tr>
              ) : (
                users.map(user => (
                  <tr key={user.id} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 font-medium text-gray-900">{user.name}</td>
                    <td className="px-4 py-3 text-gray-600">{user.email}</td>
                    <td className="px-4 py-3 text-gray-600 hidden md:table-cell">{user.orgName}</td>
                    <td className="px-4 py-3">
                      {profile.role === 'platform_admin' && user.id !== profile.id ? (
                        <select
                          value={user.role}
                          onChange={e => handleRoleChange(user.id, e.target.value)}
                          className={`px-2 py-0.5 text-xs font-medium rounded-full border-0 cursor-pointer ${ROLE_COLORS[user.role] || 'bg-gray-100 text-gray-700'}`}
                        >
                          {availableRoles.map(r => (
                            <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                          ))}
                        </select>
                      ) : (
                        <span className={`inline-block px-2 py-0.5 text-xs font-medium rounded-full ${ROLE_COLORS[user.role] || 'bg-gray-100 text-gray-700'}`}>
                          {ROLE_LABELS[user.role] || user.role}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full ${user.isActive ? 'bg-green-500' : 'bg-red-500'}`} />
                        <span className="text-xs text-gray-600">{user.isActive ? 'Active' : 'Inactive'}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs hidden lg:table-cell">
                      {formatDate(user.lastLogin)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        {user.id !== profile.id && (
                          <>
                            <button
                              onClick={() => handleStatusToggle(user.id, user.isActive)}
                              className={`px-2 py-1 text-xs rounded-lg transition-colors ${
                                user.isActive
                                  ? 'text-amber-700 hover:bg-amber-50'
                                  : 'text-green-700 hover:bg-green-50'
                              }`}
                              title={user.isActive ? 'Deactivate' : 'Activate'}
                            >
                              {user.isActive ? 'Deactivate' : 'Activate'}
                            </button>

                            {deleteConfirm === user.id ? (
                              <div className="flex items-center gap-1">
                                <button
                                  onClick={() => handleDelete(user.id)}
                                  className="px-2 py-1 text-xs bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                                >
                                  Confirm
                                </button>
                                <button
                                  onClick={() => setDeleteConfirm(null)}
                                  className="px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => setDeleteConfirm(user.id)}
                                className="p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                                title="Delete user"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50">
            <p className="text-xs text-gray-500">
              Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total} users
            </p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                disabled={offset === 0}
                className="p-1.5 rounded-lg hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-4 h-4 text-gray-600" />
              </button>
              <span className="text-xs text-gray-600 px-2">
                Page {currentPage} of {totalPages}
              </span>
              <button
                onClick={() => setOffset(offset + PAGE_SIZE)}
                disabled={offset + PAGE_SIZE >= total}
                className="p-1.5 rounded-lg hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight className="w-4 h-4 text-gray-600" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Invite User Modal */}
      {showInviteModal && (
        <InviteUserModal
          mode="invite"
          currentUserRole={profile.role}
          onClose={() => setShowInviteModal(false)}
          onSuccess={() => { setShowInviteModal(false); loadUsers(); }}
          onToast={onToast}
        />
      )}

      {/* Create User Modal */}
      {showCreateModal && (
        <InviteUserModal
          mode="create"
          currentUserRole={profile.role}
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => { setShowCreateModal(false); loadUsers(); }}
          onToast={onToast}
        />
      )}
    </div>
  );
}
