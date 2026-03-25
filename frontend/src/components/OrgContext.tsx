import { useState, useEffect } from "react"
import { authFetch } from "../services/api"
import { Card, CardHeader, CardTitle, CardContent } from "./ui/card"
import { Button } from "./ui/button"
import { Input } from "./ui/input"
import { Badge } from "./ui/badge"
import { Building2, Key, Shield, CheckCircle } from "lucide-react"

interface OrgContextData {
  org_name: string
  org_uuid: string
  sector: string
  auth_token: string
  connected: boolean
}

export function OrgContext() {
  const [orgData, setOrgData] = useState<OrgContextData>({
    org_name: "",
    org_uuid: "",
    sector: "",
    auth_token: "",
    connected: false,
  })
  const [loading, setLoading] = useState(false)
  const [tokenInput, setTokenInput] = useState("")

  useEffect(() => {
    // Load saved context
    const saved = localStorage.getItem("avni_org_context")
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        setOrgData(parsed)
        setTokenInput(parsed.auth_token || "")
      } catch {}
    }
  }, [])

  async function connectOrg() {
    if (!tokenInput.trim()) return
    setLoading(true)
    try {
      const resp = await authFetch(`/api/avni/org/current?auth_token=${encodeURIComponent(tokenInput)}`)
      if (resp.ok) {
        const data = await resp.json()
        const org = data.org || {}
        const newContext: OrgContextData = {
          org_name: org.name || org.organisationName || "",
          org_uuid: org.uuid || org.organisationUUID || "",
          sector: org.category?.name || "",
          auth_token: tokenInput,
          connected: true,
        }
        setOrgData(newContext)
        localStorage.setItem("avni_org_context", JSON.stringify(newContext))

        // Also set org context on the backend
        await authFetch("/api/org/context", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            org_name: newContext.org_name,
            org_uuid: newContext.org_uuid,
            sector: newContext.sector,
          }),
        })
      } else {
        setOrgData(prev => ({ ...prev, connected: false }))
      }
    } catch (err) {
      console.error("Failed to connect:", err)
    }
    setLoading(false)
  }

  function disconnect() {
    setOrgData({
      org_name: "",
      org_uuid: "",
      sector: "",
      auth_token: "",
      connected: false,
    })
    setTokenInput("")
    localStorage.removeItem("avni_org_context")
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Building2 className="h-5 w-5 text-primary" />
          Organisation Context
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {orgData.connected ? (
          <>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted">Organisation</span>
                <Badge variant="success" className="gap-1">
                  <CheckCircle className="h-3 w-3" /> Connected
                </Badge>
              </div>
              <p className="font-medium text-dark">{orgData.org_name}</p>
              {orgData.sector && (
                <p className="text-sm text-muted">Sector: {orgData.sector}</p>
              )}
              {orgData.org_uuid && (
                <p className="text-xs text-muted font-mono">{orgData.org_uuid.slice(0, 8)}...</p>
              )}
            </div>
            <Button variant="outline" size="sm" onClick={disconnect} className="w-full">
              Disconnect
            </Button>
          </>
        ) : (
          <>
            <div className="space-y-2">
              <label className="text-sm font-medium text-dark flex items-center gap-1">
                <Key className="h-4 w-4" /> Auth Token
              </label>
              <Input
                type="password"
                placeholder="Paste your Avni AUTH-TOKEN"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && connectOrg()}
              />
              <p className="text-xs text-muted">
                Get this from Avni &rarr; Profile &rarr; Copy Auth Token
              </p>
            </div>
            <Button
              onClick={connectOrg}
              disabled={!tokenInput.trim() || loading}
              className="w-full gap-2"
            >
              {loading ? (
                <div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
              ) : (
                <Shield className="h-4 w-4" />
              )}
              Connect to Avni
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  )
}
