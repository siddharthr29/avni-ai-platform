import { useState } from 'react';
import { ChevronLeft, Users, Activity } from 'lucide-react';
import { UserManagement } from './UserManagement';
import { PlatformStatsView } from './PlatformStats';
import type { UserProfile } from '../../types';

interface AdminPanelProps {
  onClose: () => void;
  profile: UserProfile;
  onToast: (type: 'success' | 'error' | 'info', message: string) => void;
}

type AdminTab = 'users' | 'stats';

export function AdminPanel({ onClose, profile, onToast }: AdminPanelProps) {
  const [activeTab, setActiveTab] = useState<AdminTab>('users');

  const tabs: { id: AdminTab; label: string; icon: typeof Users }[] = [
    { id: 'users', label: 'Users', icon: Users },
    { id: 'stats', label: 'Stats', icon: Activity },
  ];

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <div className="h-14 border-b border-gray-200 bg-white flex items-center px-4 shrink-0">
        <button
          onClick={onClose}
          className="p-2 rounded-lg hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 mr-3"
          aria-label="Back to chat"
        >
          <ChevronLeft className="w-5 h-5 text-gray-600" />
        </button>
        <h1 className="text-lg font-semibold text-gray-900">Admin Panel</h1>

        {/* Tabs */}
        <div className="flex items-center gap-1 ml-8">
          {tabs.map(tab => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors ${
                  activeTab === tab.id
                    ? 'bg-primary-50 text-primary-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        {activeTab === 'users' && (
          <UserManagement profile={profile} onToast={onToast} />
        )}
        {activeTab === 'stats' && (
          <PlatformStatsView onToast={onToast} />
        )}
      </div>
    </div>
  );
}
