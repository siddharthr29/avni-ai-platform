import React, { useState, useEffect } from "react"
import { authFetch } from "../services/api"
import { Card, CardHeader, CardTitle, CardContent } from "./ui/card"
import { Badge } from "./ui/badge"
import { Building2, Package, Clock, TrendingUp, Users, MessageSquare } from "lucide-react"

interface UsageStats {
  orgs_connected: number
  bundles_generated: number
  bundles_uploaded: number
  chat_messages: number
  avg_bundle_time_minutes: number
  estimated_hours_saved: number
  active_users: number
  top_intents: Array<{ intent: string; count: number }>
}

interface StatCardProps {
  icon: React.ElementType
  label: string
  value: string | number
  subtitle?: string
  color: string
}

function StatCard({ icon: Icon, label, value, subtitle, color }: StatCardProps) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm text-gray-500">{label}</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
            {subtitle && <p className="text-xs text-gray-500 mt-1">{subtitle}</p>}
          </div>
          <div className={`p-2 rounded-lg ${color}`}>
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function UsageTracking() {
  const [stats, setStats] = useState<UsageStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadStats()
    const interval = setInterval(loadStats, 60000)
    return () => clearInterval(interval)
  }, [])

  async function loadStats() {
    try {
      const resp = await authFetch("/api/usage/stats")
      if (resp.ok) {
        setStats(await resp.json())
      }
    } catch {
      // API not available yet, will show defaults
    }
    setLoading(false)
  }

  if (loading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {[...Array(6)].map((_, i) => (
          <Card key={i}>
            <CardContent className="pt-6">
              <div className="animate-pulse space-y-3">
                <div className="h-4 w-24 bg-gray-200 rounded" />
                <div className="h-8 w-16 bg-gray-200 rounded" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  const s = stats || {
    orgs_connected: 0,
    bundles_generated: 0,
    bundles_uploaded: 0,
    chat_messages: 0,
    avg_bundle_time_minutes: 0,
    estimated_hours_saved: 0,
    active_users: 0,
    top_intents: [],
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <StatCard icon={Building2} label="Orgs Connected" value={s.orgs_connected} color="bg-primary-100 text-primary-700" />
        <StatCard icon={Package} label="Bundles Generated" value={s.bundles_generated} subtitle={`${s.bundles_uploaded} uploaded`} color="bg-success-50 text-success-700" />
        <StatCard icon={Clock} label="Hours Saved" value={s.estimated_hours_saved.toFixed(1)} subtitle={`Avg ${s.avg_bundle_time_minutes}min per bundle`} color="bg-primary-50 text-primary-700" />
        <StatCard icon={MessageSquare} label="Chat Messages" value={s.chat_messages} color="bg-warning-50 text-gray-900" />
        <StatCard icon={Users} label="Active Users" value={s.active_users} color="bg-primary-100 text-primary-700" />
        <StatCard icon={TrendingUp} label="30% Target" value={s.estimated_hours_saved > 0 ? `${Math.round((s.estimated_hours_saved / Math.max(1, s.bundles_generated * 8)) * 100)}%` : "--"} subtitle="Effort reduction" color="bg-success-50 text-success-700" />
      </div>

      {s.top_intents.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Top User Intents</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {s.top_intents.map((intent, i) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <span className="text-gray-700">{intent.intent}</span>
                  <Badge variant="outline">{intent.count}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
