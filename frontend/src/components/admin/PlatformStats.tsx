import { useState, useEffect } from 'react';
import { Users, UserCheck, MessageSquare, Activity } from 'lucide-react';
import { fetchPlatformStats } from '../../services/api';
import type { PlatformStats } from '../../types';

interface PlatformStatsViewProps {
  onToast: (type: 'success' | 'error' | 'info', message: string) => void;
}

const ROLE_LABELS: Record<string, string> = {
  ngo_user: 'NGO Users',
  implementor: 'Implementors',
  org_admin: 'Org Admins',
  platform_admin: 'Platform Admins',
};

const ROLE_COLORS: Record<string, string> = {
  ngo_user: 'bg-gray-50 border-gray-200',
  implementor: 'bg-blue-50 border-blue-200',
  org_admin: 'bg-amber-50 border-amber-200',
  platform_admin: 'bg-red-50 border-red-200',
};

const ROLE_TEXT: Record<string, string> = {
  ngo_user: 'text-gray-700',
  implementor: 'text-blue-700',
  org_admin: 'text-amber-700',
  platform_admin: 'text-red-700',
};

export function PlatformStatsView({ onToast }: PlatformStatsViewProps) {
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await fetchPlatformStats();
        setStats(data);
      } catch (err) {
        onToast('error', `Failed to load stats: ${err instanceof Error ? err.message : 'Unknown error'}`);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [onToast]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-primary-600 border-t-transparent rounded-full spinner mx-auto mb-3" />
          <p className="text-sm text-gray-500">Loading platform stats...</p>
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="text-center py-20 text-gray-400">
        Unable to load platform statistics.
      </div>
    );
  }

  const sortedOrgs = Object.entries(stats.usersByOrg)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 10);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Overview Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard
          icon={Users}
          label="Total Users"
          value={stats.totalUsers}
          color="text-primary-600"
          bg="bg-primary-50"
        />
        <StatCard
          icon={UserCheck}
          label="Active Users"
          value={stats.activeUsers}
          color="text-green-600"
          bg="bg-green-50"
        />
        <StatCard
          icon={Activity}
          label="Total Sessions"
          value={stats.totalSessions}
          color="text-blue-600"
          bg="bg-blue-50"
        />
        <StatCard
          icon={MessageSquare}
          label="Messages (24h)"
          value={stats.recentMessages24h}
          color="text-amber-600"
          bg="bg-amber-50"
        />
      </div>

      {/* Messages row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <h3 className="text-sm font-medium text-gray-500 mb-3">Messages Activity</h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Last 24 hours</span>
              <span className="text-lg font-semibold text-gray-900">{stats.recentMessages24h.toLocaleString()}</span>
            </div>
            <div className="h-px bg-gray-100" />
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Last 7 days</span>
              <span className="text-lg font-semibold text-gray-900">{stats.recentMessages7d.toLocaleString()}</span>
            </div>
          </div>
        </div>

        {/* Users by Org */}
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <h3 className="text-sm font-medium text-gray-500 mb-3">Top Organizations</h3>
          {sortedOrgs.length === 0 ? (
            <p className="text-sm text-gray-400">No organization data available.</p>
          ) : (
            <div className="space-y-2">
              {sortedOrgs.map(([org, count]) => (
                <div key={org} className="flex items-center justify-between">
                  <span className="text-sm text-gray-700 truncate mr-2">{org}</span>
                  <span className="text-sm font-medium text-gray-900 shrink-0">{count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Users by Role */}
      <div>
        <h3 className="text-sm font-medium text-gray-500 mb-3">Users by Role</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Object.entries(stats.usersByRole).map(([role, count]) => (
            <div
              key={role}
              className={`border rounded-lg p-4 ${ROLE_COLORS[role] || 'bg-gray-50 border-gray-200'}`}
            >
              <p className={`text-2xl font-bold ${ROLE_TEXT[role] || 'text-gray-700'}`}>
                {count}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                {ROLE_LABELS[role] || role}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  color,
  bg,
}: {
  icon: typeof Users;
  label: string;
  value: number;
  color: string;
  bg: string;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 ${bg} rounded-lg flex items-center justify-center`}>
          <Icon className={`w-5 h-5 ${color}`} />
        </div>
        <div>
          <p className="text-2xl font-bold text-gray-900">{value.toLocaleString()}</p>
          <p className="text-xs text-gray-500">{label}</p>
        </div>
      </div>
    </div>
  );
}
