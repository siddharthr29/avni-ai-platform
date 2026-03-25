import { useState } from 'react';
import { User, Building2, Layers, FileText, ArrowRight, Mail, Lock } from 'lucide-react';
import { AvniLogo } from './AvniLogo';

const SECTORS = [
  'Maternal & Child Health (MCH)',
  'Water & Sanitation (WASH)',
  'Education',
  'Nutrition',
  'Livelihoods',
  'Sports Development',
  'Tuberculosis (TB)',
  'Non-Communicable Diseases (NCD)',
  'Community Development',
  'Other',
];

interface UserProfilePickerProps {
  onLogin: (data: {
    email: string;
    password: string;
    name: string;
    orgName: string;
    sector: string;
    orgContext: string;
    isRegister: boolean;
  }) => Promise<void>;
}

export function UserProfilePicker({ onLogin }: UserProfilePickerProps) {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [orgName, setOrgName] = useState('');
  const [sector, setSector] = useState('');
  const [orgContext, setOrgContext] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const canSubmitLogin = email.trim() && password.trim();
  const canSubmitRegister = email.trim() && password.trim() && name.trim() && orgName.trim() && sector;
  const canSubmit = isRegister ? canSubmitRegister : canSubmitLogin;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    setError('');
    setLoading(true);
    try {
      await onLogin({ email, password, name, orgName, sector, orgContext, isRegister });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        <div className="text-center mb-8">
          <div className="flex justify-center mb-4">
            <AvniLogo size={48} variant="icon" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">
            {isRegister ? 'Create Account' : (
              <>
                <span className="text-teal-700">Avni</span> hai T<span className="text-teal-700">AI</span>yaar
              </>
            )}
          </h1>
          <p className="text-gray-600 mt-2">
            {isRegister ? 'Set up your account to get started' : 'AI-powered Avni implementation platform'}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          {/* Email */}
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1.5">
              Email <span className="text-red-500">*</span>
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                id="email"
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@organisation.org"
                className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 bg-white focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                autoFocus
                autoComplete="email"
              />
            </div>
          </div>

          {/* Password */}
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1.5">
              Password <span className="text-red-500">*</span>
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                id="password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder={isRegister ? 'Min 6 characters' : 'Enter your password'}
                className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 bg-white focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                autoComplete={isRegister ? 'new-password' : 'current-password'}
              />
            </div>
          </div>

          {/* Registration-only fields */}
          {isRegister && (
            <>
              {/* Name */}
              <div>
                <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1.5">
                  Your Name <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    id="name"
                    type="text"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    placeholder="e.g. Priya Sharma"
                    className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 bg-white focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  />
                </div>
              </div>

              {/* Organisation */}
              <div>
                <label htmlFor="org" className="block text-sm font-medium text-gray-700 mb-1.5">
                  Organisation Name <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    id="org"
                    type="text"
                    value={orgName}
                    onChange={e => setOrgName(e.target.value)}
                    placeholder="e.g. Sangwari, JSS, CInI"
                    className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 bg-white focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  />
                </div>
              </div>

              {/* Sector */}
              <div>
                <label htmlFor="sector" className="block text-sm font-medium text-gray-700 mb-1.5">
                  Sector <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <Layers className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <select
                    id="sector"
                    value={sector}
                    onChange={e => setSector(e.target.value)}
                    className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 appearance-none bg-white"
                  >
                    <option value="">Select your sector...</option>
                    {SECTORS.map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Org Context */}
              <div>
                <label htmlFor="context" className="block text-sm font-medium text-gray-700 mb-1.5">
                  About Your Organisation
                </label>
                <div className="relative">
                  <FileText className="absolute left-3 top-3 w-4 h-4 text-gray-400" />
                  <textarea
                    id="context"
                    value={orgContext}
                    onChange={e => setOrgContext(e.target.value)}
                    placeholder="e.g. We work with 500 tribal women across 3 districts in Chhattisgarh on maternal health."
                    rows={3}
                    className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 bg-white focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-none"
                  />
                </div>
              </div>
            </>
          )}

          <button
            type="submit"
            disabled={!canSubmit || loading}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-primary-700 hover:bg-primary-800 disabled:bg-gray-200 disabled:text-gray-500 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium text-sm"
          >
            {loading ? (
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full spinner" />
            ) : (
              <>
                {isRegister ? 'Create Account' : 'Sign In'}
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>

          <div className="text-center pt-2">
            <button
              type="button"
              onClick={() => { setIsRegister(!isRegister); setError(''); }}
              className="text-sm text-primary-600 hover:text-primary-700 font-medium"
            >
              {isRegister ? 'Already have an account? Sign in' : "Don't have an account? Register"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
