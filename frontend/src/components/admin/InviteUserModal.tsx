import { useState } from 'react';
import { X, Copy, Check } from 'lucide-react';
import { inviteUser, createAdminUser } from '../../services/api';
import type { UserRole } from '../../types';

interface InviteUserModalProps {
  mode: 'invite' | 'create';
  currentUserRole: UserRole;
  onClose: () => void;
  onSuccess: () => void;
  onToast: (type: 'success' | 'error' | 'info', message: string) => void;
}

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: 'ngo_user', label: 'NGO User' },
  { value: 'implementor', label: 'Implementor' },
  { value: 'org_admin', label: 'Org Admin' },
  { value: 'platform_admin', label: 'Platform Admin' },
];

const SECTOR_OPTIONS = [
  'Health', 'Education', 'Nutrition', 'WASH', 'Livelihoods', 'Agriculture', 'Other',
];

export function InviteUserModal({ mode, currentUserRole, onClose, onSuccess, onToast }: InviteUserModalProps) {
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [orgName, setOrgName] = useState('');
  const [sector, setSector] = useState('');
  const [role, setRole] = useState<UserRole>('ngo_user');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const availableRoles = currentUserRole === 'org_admin'
    ? ROLE_OPTIONS.filter(r => r.value === 'ngo_user' || r.value === 'implementor')
    : ROLE_OPTIONS;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !name.trim() || !orgName.trim()) return;

    setSubmitting(true);
    try {
      if (mode === 'invite') {
        const result = await inviteUser({
          email: email.trim(),
          name: name.trim(),
          orgName: orgName.trim(),
          role,
          sector: sector || undefined,
        });
        if (result.tempPassword) {
          setTempPassword(result.tempPassword);
        } else {
          onToast('success', 'User invited successfully');
          onSuccess();
        }
      } else {
        const result = await createAdminUser({
          email: email.trim(),
          name: name.trim(),
          password: password.trim(),
          orgName: orgName.trim(),
          role,
          sector: sector || undefined,
        });
        if (result.tempPassword) {
          setTempPassword(result.tempPassword);
        } else {
          onToast('success', 'User created successfully');
          onSuccess();
        }
      }
    } catch (err) {
      onToast('error', `Failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleCopy = async () => {
    if (!tempPassword) return;
    try {
      await navigator.clipboard.writeText(tempPassword);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      onToast('error', 'Failed to copy to clipboard');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 scale-in">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">
            {mode === 'invite' ? 'Invite User' : 'Create User'}
          </h2>
          <button
            onClick={tempPassword ? onSuccess : onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Temp password display */}
        {tempPassword ? (
          <div className="p-5">
            <p className="text-sm text-gray-700 mb-3">
              User {mode === 'invite' ? 'invited' : 'created'} successfully. Share this temporary password:
            </p>
            <div className="flex items-center gap-2 p-3 bg-gray-50 border border-gray-200 rounded-lg">
              <code className="flex-1 text-sm font-mono text-gray-900 select-all">{tempPassword}</code>
              <button
                onClick={handleCopy}
                className="p-1.5 rounded-lg hover:bg-gray-200 transition-colors"
                title="Copy password"
              >
                {copied ? (
                  <Check className="w-4 h-4 text-green-600" />
                ) : (
                  <Copy className="w-4 h-4 text-gray-500" />
                )}
              </button>
            </div>
            <p className="text-xs text-gray-400 mt-2">
              The user should change this password after first login.
            </p>
            <button
              onClick={onSuccess}
              className="w-full mt-4 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-5 space-y-4">
            {/* Email */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Email <span className="text-red-500">*</span>
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="user@example.org"
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>

            {/* Name */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Full name"
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>

            {/* Password (create mode only) */}
            {mode === 'create' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Password <span className="text-red-500">*</span>
                </label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Set a password"
                  minLength={8}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
              </div>
            )}

            {/* Organization */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Organization <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                required
                value={orgName}
                onChange={e => setOrgName(e.target.value)}
                placeholder="Organization name"
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>

            {/* Sector */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Sector
              </label>
              <select
                value={sector}
                onChange={e => setSector(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-gray-700"
              >
                <option value="">Select sector (optional)</option>
                {SECTOR_OPTIONS.map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>

            {/* Role */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Role
              </label>
              <select
                value={role}
                onChange={e => setRole(e.target.value as UserRole)}
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-gray-700"
              >
                {availableRoles.map(r => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>

            {/* Buttons */}
            <div className="flex items-center gap-3 pt-2">
              <button
                type="submit"
                disabled={submitting}
                className="flex-1 px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
              >
                {submitting ? 'Processing...' : mode === 'invite' ? 'Send Invite' : 'Create User'}
              </button>
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
