import React, { useState } from "react"
import { Button } from "./ui/button"
import { Badge } from "./ui/badge"
import { OrgContext } from "./OrgContext"
import { SRSWizard } from "./SRSWizard"
import { BundleReview } from "./BundleReview"
import { AgentPanel } from "./AgentPanel"
import { UsageTracking } from "./UsageTracking"
import {
  MessageSquare, FileText, Package, Bot, BarChart3,
  Menu, X, Sparkles, Building2
} from "lucide-react"
import { ProductTour } from "./ProductTour"

interface AppLayoutProps {
  children?: React.ReactNode
}

const NAV_ITEMS = [
  { id: "chat", icon: MessageSquare, label: "Chat", tourId: "chat" },
  { id: "srs", icon: FileText, label: "SRS Wizard", tourId: "srs-wizard" },
  { id: "bundle", icon: Package, label: "Bundle Review", tourId: "bundle-review" },
  { id: "agent", icon: Bot, label: "Agent", tourId: "agent" },
  { id: "usage", icon: BarChart3, label: "Usage", tourId: "usage" },
] as const

type ViewId = typeof NAV_ITEMS[number]["id"]

export function AppLayout({ children }: AppLayoutProps) {
  const [activeView, setActiveView] = useState<ViewId>("chat")
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [bundleId, setBundleId] = useState<string | null>(null)
  const [agentTaskId] = useState<string | null>(null)

  return (
    <div className="h-screen flex bg-gray-50">
      {/* Sidebar */}
      <aside className={`${sidebarOpen ? "w-72" : "w-0"} transition-all duration-300 overflow-hidden flex-shrink-0`}>
        <div className="w-72 h-full flex flex-col bg-gray-900 text-gray-300">
          {/* Logo */}
          <div className="p-4 flex items-center gap-3 border-b border-white/10">
            <Sparkles className="h-6 w-6 text-primary-400" />
            <span className="font-bold text-lg text-white">Avni AI</span>
          </div>

          {/* Org Context */}
          <div className="p-3" data-tour="org-context">
            <OrgContext />
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-2 space-y-1">
            {NAV_ITEMS.map(item => {
              const Icon = item.icon
              return (
                <button
                  key={item.id}
                  data-tour={item.tourId}
                  onClick={() => setActiveView(item.id)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                    activeView === item.id
                      ? "bg-gray-700 text-white"
                      : "text-gray-300 hover:bg-white/10"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </button>
              )
            })}
          </nav>

          {/* Version */}
          <div className="p-4 text-xs text-white/40">
            Avni AI Platform v1.0
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-14 flex items-center justify-between px-4 border-b border-gray-200 bg-white">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => setSidebarOpen(!sidebarOpen)}>
              {sidebarOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </Button>
            <h1 className="font-semibold text-gray-900">
              {NAV_ITEMS.find(n => n.id === activeView)?.label}
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">
              <Building2 className="h-3 w-3 mr-1" /> 63 API endpoints
            </Badge>
          </div>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {activeView === "chat" && children}
          {activeView === "srs" && (
            <SRSWizard onGenerate={(data) => {
              console.log("SRS generated:", data)
            }} />
          )}
          {activeView === "bundle" && bundleId && (
            <BundleReview bundleId={bundleId} onClose={() => setBundleId(null)} />
          )}
          {activeView === "bundle" && !bundleId && (
            <div className="flex flex-col items-center justify-center h-64 text-gray-500">
              <Package className="h-12 w-12 mb-3 opacity-30" />
              <p>No bundle selected. Generate one from the SRS Wizard or chat.</p>
            </div>
          )}
          {activeView === "agent" && <AgentPanel taskId={agentTaskId || undefined} />}
          {activeView === "usage" && <UsageTracking />}
        </div>
      </main>

      <ProductTour />
    </div>
  )
}
