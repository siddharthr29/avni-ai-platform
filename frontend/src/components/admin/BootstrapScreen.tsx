import { useState } from 'react';
import { Shield } from 'lucide-react';
import { bootstrapAdmin } from '../../services/api';
import { AvniLogo } from '../AvniLogo';

interface BootstrapScreenProps {
  onBootstrapComplete: (data: {
    accessToken: string;
    refreshToken: string;
    user: { id: string; name: string; email: string; orgName: string; role: string };
  }) => void;
  onToast: (type: 'success' | 'error' | 'info', message: string) => void;
}

export function BootstrapScreen({ onBootstrapComplete, onToast }: BootstrapScreenProps) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [orgName, setOrgName] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !email.trim() || !password.trim() || !orgName.trim()) return;

    setSubmitting(true);
    try {
      const result = await bootstrapAdmin({
        name: name.trim(),
        email: email.trim(),
        password: password.trim(),
        orgName: orgName.trim(),
      });

      onToast('success', 'Platform admin created successfully! You are now logged in.');
      onBootstrapComplete({
        accessToken: result.accessToken,
        refreshToken: result.refreshToken,
        user: {
          id: result.user.id,
          name: result.user.name,
          email: result.user.email,
          orgName: result.user.orgName,
          role: 'platform_admin',
        },
      });
    } catch (err) {
      onToast('error', `Bootstrap failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-lg border border-gray-200 w-full max-w-md p-8">
        {/* Header */}
        <div className="text-center mb-6">
          <div className="flex items-center justify-center gap-3 mb-4">
            <AvniLogo size={32} variant="full" />
            <Shield className="w-6 h-6 text-primary-600" />
          </div>
          <h1 className="text-xl font-semibold text-gray-900">Setup Platform Admin</h1>
          <p className="text-sm text-gray-600 mt-1">
            No admin account exists yet. Create the first platform admin to get started.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Your full name"
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Email <span className="text-red-500">*</span>
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="admin@example.org"
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Password <span className="text-red-500">*</span>
            </label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Minimum 8 characters"
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Organization <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              required
              value={orgName}
              onChange={e => setOrgName(e.target.value)}
              placeholder="Your organization name"
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full px-4 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors mt-2"
          >
            {submitting ? 'Creating admin...' : 'Create Platform Admin'}
          </button>
        </form>
      </div>
    </div>
  );
}
