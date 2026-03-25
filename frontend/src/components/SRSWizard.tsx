import { useState } from "react"
import { authFetch } from "../services/api"
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "./ui/card"
import { Button } from "./ui/button"
import { Input } from "./ui/input"
import { Textarea } from "./ui/textarea"
import { Badge } from "./ui/badge"
import {
  ChevronRight, ChevronLeft, Check, Building2, Users,
  Heart, ClipboardList, FileText, Calendar, BarChart3,
  Shield, Eye, Sparkles
} from "lucide-react"

interface SRSWizardData {
  // Step 1
  org_name: string
  sector: string
  geography: string
  beneficiaries: string
  // Step 2
  subject_types: Array<{ name: string; type: string; registration_fields: string }>
  // Step 3
  programs: Array<{ name: string; description: string; subject_type: string; colour: string }>
  // Step 4
  encounter_types: Array<{ name: string; program: string; type: string; scheduling: string }>
  // Step 5
  registration_fields: Array<{ name: string; type: string; mandatory: boolean; options?: string }>
  // Step 6
  encounter_fields: Array<{ encounter: string; name: string; type: string; mandatory: boolean; options?: string }>
  // Step 7
  schedules: Array<{ encounter: string; frequency: string; max_visits: number }>
  // Step 8
  dashboards: Array<{ name: string; indicator: string; type: string }>
  // Step 9
  roles: Array<{ name: string; permissions: string[] }>
}

const STEPS = [
  { icon: Building2, label: "Organisation", description: "Basic org details" },
  { icon: Users, label: "Subject Types", description: "Who you're tracking" },
  { icon: Heart, label: "Programs", description: "Health/education programs" },
  { icon: ClipboardList, label: "Encounters", description: "Visit types" },
  { icon: FileText, label: "Registration", description: "Registration form" },
  { icon: FileText, label: "Visit Forms", description: "Encounter forms" },
  { icon: Calendar, label: "Schedules", description: "Visit scheduling" },
  { icon: BarChart3, label: "Dashboards", description: "Reports & indicators" },
  { icon: Shield, label: "Roles", description: "User permissions" },
  { icon: Eye, label: "Review", description: "Review & generate" },
]

const SECTORS = ["Health", "Education", "Livelihoods", "Water & Sanitation", "Agriculture", "Social Protection", "Other"]
const SUBJECT_TYPES = ["Individual", "Household", "Group", "Person"]
const FIELD_TYPES = ["Text", "Numeric", "Date", "Coded (Single)", "Coded (Multiple)", "Notes", "Image", "Location", "PhoneNumber", "Id"]
const SCHEDULING = ["Scheduled (fixed)", "Scheduled (flexible)", "On demand", "One-time"]

export function SRSWizard({ onGenerate }: { onGenerate?: (data: SRSWizardData) => void }) {
  const [step, setStep] = useState(0)
  const [data, setData] = useState<SRSWizardData>({
    org_name: "",
    sector: "",
    geography: "",
    beneficiaries: "",
    subject_types: [{ name: "", type: "Individual", registration_fields: "" }],
    programs: [{ name: "", description: "", subject_type: "", colour: "#0d6efd" }],
    encounter_types: [{ name: "", program: "", type: "ProgramEncounter", scheduling: "Scheduled (fixed)" }],
    registration_fields: [{ name: "", type: "Text", mandatory: true }],
    encounter_fields: [{ encounter: "", name: "", type: "Text", mandatory: false }],
    schedules: [{ encounter: "", frequency: "Monthly", max_visits: 12 }],
    dashboards: [{ name: "", indicator: "", type: "count" }],
    roles: [{ name: "Field Worker", permissions: ["view_subject", "register_subject", "view_enrolment", "create_enrolment"] }],
  })

  const updateField = (field: string, value: unknown) => {
    setData(prev => ({ ...prev, [field]: value }))
  }

  const addItem = (field: string, template: Record<string, unknown>) => {
    setData(prev => ({ ...prev, [field]: [...(prev as unknown as Record<string, unknown[]>)[field], template] }))
  }

  const updateItem = (field: string, index: number, key: string, value: unknown) => {
    setData(prev => {
      const items = [...(prev as unknown as Record<string, Record<string, unknown>[]>)[field]]
      items[index] = { ...items[index], [key]: value }
      return { ...prev, [field]: items }
    })
  }

  const removeItem = (field: string, index: number) => {
    setData(prev => {
      const items = [...(prev as unknown as Record<string, unknown[]>)[field]]
      items.splice(index, 1)
      return { ...prev, [field]: items }
    })
  }

  async function handleGenerate() {
    try {
      const resp = await authFetch("/api/srs/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      })
      if (resp.ok) {
        onGenerate?.(data)
      }
    } catch (err) {
      console.error("Failed to generate:", err)
    }
  }

  function renderStep() {
    switch (step) {
      case 0:
        return (
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium text-gray-900 mb-1 block">Organisation Name *</label>
              <Input value={data.org_name} onChange={e => updateField("org_name", e.target.value)} placeholder="e.g. Phulwari Foundation" />
            </div>
            <div>
              <label className="text-sm font-medium text-gray-900 mb-1 block">Sector *</label>
              <div className="flex flex-wrap gap-2">
                {SECTORS.map(s => (
                  <button key={s} onClick={() => updateField("sector", s)}
                    className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${data.sector === s ? "bg-primary-500 text-white border-primary-500" : "border-gray-300 text-gray-700 hover:border-primary-500"}`}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-900 mb-1 block">Geography</label>
              <Input value={data.geography} onChange={e => updateField("geography", e.target.value)} placeholder="e.g. Rural Maharashtra, 5 districts" />
            </div>
            <div>
              <label className="text-sm font-medium text-gray-900 mb-1 block">Target Beneficiaries</label>
              <Textarea value={data.beneficiaries} onChange={e => updateField("beneficiaries", e.target.value)} placeholder="e.g. Pregnant women, children 0-5 years, lactating mothers" />
            </div>
          </div>
        )

      case 1:
        return (
          <div className="space-y-4">
            <p className="text-sm text-gray-500">Who are you tracking? Each subject type gets its own registration form.</p>
            {data.subject_types.map((st, i) => (
              <div key={i} className="p-3 rounded-lg border border-gray-200 space-y-2">
                <div className="flex gap-2">
                  <Input value={st.name} onChange={e => updateItem("subject_types", i, "name", e.target.value)} placeholder="e.g. Beneficiary, Child, Household" className="flex-1" />
                  <select value={st.type} onChange={e => updateItem("subject_types", i, "type", e.target.value)}
                    className="px-3 py-2 rounded-md border border-gray-300 text-sm bg-white">
                    {SUBJECT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                  {data.subject_types.length > 1 && (
                    <Button variant="outline" size="sm" onClick={() => removeItem("subject_types", i)}>Remove</Button>
                  )}
                </div>
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => addItem("subject_types", { name: "", type: "Individual", registration_fields: "" })}>
              + Add Subject Type
            </Button>
          </div>
        )

      case 2:
        return (
          <div className="space-y-4">
            <p className="text-sm text-gray-500">Programs group related encounters (e.g. Maternal Health, Child Nutrition).</p>
            {data.programs.map((p, i) => (
              <div key={i} className="p-3 rounded-lg border border-gray-200 space-y-2">
                <Input value={p.name} onChange={e => updateItem("programs", i, "name", e.target.value)} placeholder="Program name" />
                <Textarea value={p.description} onChange={e => updateItem("programs", i, "description", e.target.value)} placeholder="Brief description" rows={2} />
                <select value={p.subject_type} onChange={e => updateItem("programs", i, "subject_type", e.target.value)}
                  className="w-full px-3 py-2 rounded-md border border-gray-300 text-sm bg-white">
                  <option value="">Select subject type...</option>
                  {data.subject_types.filter(st => st.name).map(st => <option key={st.name} value={st.name}>{st.name}</option>)}
                </select>
                {data.programs.length > 1 && (
                  <Button variant="outline" size="sm" onClick={() => removeItem("programs", i)}>Remove</Button>
                )}
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => addItem("programs", { name: "", description: "", subject_type: "", colour: "#0d6efd" })}>
              + Add Program
            </Button>
          </div>
        )

      case 3:
        return (
          <div className="space-y-4">
            <p className="text-sm text-gray-500">What types of visits/encounters happen in each program?</p>
            {data.encounter_types.map((et, i) => (
              <div key={i} className="p-3 rounded-lg border border-gray-200 space-y-2">
                <Input value={et.name} onChange={e => updateItem("encounter_types", i, "name", e.target.value)} placeholder="e.g. ANC Visit, Growth Monitoring" />
                <div className="grid grid-cols-2 gap-2">
                  <select value={et.program} onChange={e => updateItem("encounter_types", i, "program", e.target.value)}
                    className="px-3 py-2 rounded-md border border-gray-300 text-sm bg-white">
                    <option value="">Program...</option>
                    {data.programs.filter(p => p.name).map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
                  </select>
                  <select value={et.scheduling} onChange={e => updateItem("encounter_types", i, "scheduling", e.target.value)}
                    className="px-3 py-2 rounded-md border border-gray-300 text-sm bg-white">
                    {SCHEDULING.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                {data.encounter_types.length > 1 && (
                  <Button variant="outline" size="sm" onClick={() => removeItem("encounter_types", i)}>Remove</Button>
                )}
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => addItem("encounter_types", { name: "", program: "", type: "ProgramEncounter", scheduling: "Scheduled (fixed)" })}>
              + Add Encounter Type
            </Button>
          </div>
        )

      case 4:
        return (
          <div className="space-y-4">
            <p className="text-sm text-gray-500">What fields should be on the registration form?</p>
            {data.registration_fields.map((f, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input value={f.name} onChange={e => updateItem("registration_fields", i, "name", e.target.value)} placeholder="Field name" className="flex-1" />
                <select value={f.type} onChange={e => updateItem("registration_fields", i, "type", e.target.value)}
                  className="px-3 py-2 rounded-md border border-gray-300 text-sm bg-white w-40">
                  {FIELD_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                <label className="flex items-center gap-1 text-xs text-gray-500 whitespace-nowrap">
                  <input type="checkbox" checked={f.mandatory} onChange={e => updateItem("registration_fields", i, "mandatory", e.target.checked)} />
                  Required
                </label>
                <Button variant="outline" size="sm" onClick={() => removeItem("registration_fields", i)}>x</Button>
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => addItem("registration_fields", { name: "", type: "Text", mandatory: false })}>
              + Add Field
            </Button>
          </div>
        )

      case 5:
        return (
          <div className="space-y-4">
            <p className="text-sm text-gray-500">What fields should be on each encounter form?</p>
            {data.encounter_fields.map((f, i) => (
              <div key={i} className="flex items-center gap-2">
                <select value={f.encounter} onChange={e => updateItem("encounter_fields", i, "encounter", e.target.value)}
                  className="px-3 py-2 rounded-md border border-gray-300 text-sm bg-white w-40">
                  <option value="">Encounter...</option>
                  {data.encounter_types.filter(et => et.name).map(et => <option key={et.name} value={et.name}>{et.name}</option>)}
                </select>
                <Input value={f.name} onChange={e => updateItem("encounter_fields", i, "name", e.target.value)} placeholder="Field name" className="flex-1" />
                <select value={f.type} onChange={e => updateItem("encounter_fields", i, "type", e.target.value)}
                  className="px-3 py-2 rounded-md border border-gray-300 text-sm bg-white w-32">
                  {FIELD_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                <Button variant="outline" size="sm" onClick={() => removeItem("encounter_fields", i)}>x</Button>
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => addItem("encounter_fields", { encounter: "", name: "", type: "Text", mandatory: false })}>
              + Add Field
            </Button>
          </div>
        )

      case 6:
        return (
          <div className="space-y-4">
            <p className="text-sm text-gray-500">How often should each encounter type be scheduled?</p>
            {data.schedules.map((s, i) => (
              <div key={i} className="flex items-center gap-2">
                <select value={s.encounter} onChange={e => updateItem("schedules", i, "encounter", e.target.value)}
                  className="px-3 py-2 rounded-md border border-gray-300 text-sm bg-white flex-1">
                  <option value="">Encounter...</option>
                  {data.encounter_types.filter(et => et.name && et.scheduling.startsWith("Scheduled")).map(et => (
                    <option key={et.name} value={et.name}>{et.name}</option>
                  ))}
                </select>
                <select value={s.frequency} onChange={e => updateItem("schedules", i, "frequency", e.target.value)}
                  className="px-3 py-2 rounded-md border border-gray-300 text-sm bg-white w-32">
                  <option>Weekly</option>
                  <option>Fortnightly</option>
                  <option>Monthly</option>
                  <option>Quarterly</option>
                  <option>Yearly</option>
                </select>
                <Input type="number" value={s.max_visits} onChange={e => updateItem("schedules", i, "max_visits", parseInt(e.target.value) || 0)} className="w-20" placeholder="Max" />
                <Button variant="outline" size="sm" onClick={() => removeItem("schedules", i)}>x</Button>
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => addItem("schedules", { encounter: "", frequency: "Monthly", max_visits: 12 })}>
              + Add Schedule
            </Button>
          </div>
        )

      case 7:
        return (
          <div className="space-y-4">
            <p className="text-sm text-gray-500">What dashboards and indicators do you need?</p>
            {data.dashboards.map((d, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input value={d.name} onChange={e => updateItem("dashboards", i, "name", e.target.value)} placeholder="Dashboard name" className="flex-1" />
                <Input value={d.indicator} onChange={e => updateItem("dashboards", i, "indicator", e.target.value)} placeholder="Indicator" className="flex-1" />
                <select value={d.type} onChange={e => updateItem("dashboards", i, "type", e.target.value)}
                  className="px-3 py-2 rounded-md border border-gray-300 text-sm bg-white w-28">
                  <option value="count">Count</option>
                  <option value="percentage">Percentage</option>
                  <option value="list">List</option>
                  <option value="chart">Chart</option>
                </select>
                <Button variant="outline" size="sm" onClick={() => removeItem("dashboards", i)}>x</Button>
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => addItem("dashboards", { name: "", indicator: "", type: "count" })}>
              + Add Dashboard
            </Button>
          </div>
        )

      case 8:
        return (
          <div className="space-y-4">
            <p className="text-sm text-gray-500">Define user roles and their permissions.</p>
            {data.roles.map((r, i) => (
              <div key={i} className="p-3 rounded-lg border border-gray-200 space-y-2">
                <Input value={r.name} onChange={e => updateItem("roles", i, "name", e.target.value)} placeholder="Role name" />
                <div className="flex flex-wrap gap-2">
                  {["view_subject", "register_subject", "view_enrolment", "create_enrolment", "edit_subject", "void_subject", "approve_subject", "view_checklist", "upload_data"].map(perm => (
                    <label key={perm} className={`px-2 py-1 rounded text-xs cursor-pointer border transition-colors ${
                      r.permissions.includes(perm) ? "bg-primary-500 text-white border-primary-500" : "border-gray-300 text-gray-500 hover:border-primary-500"
                    }`}>
                      <input type="checkbox" className="sr-only" checked={r.permissions.includes(perm)}
                        onChange={e => {
                          const perms = e.target.checked ? [...r.permissions, perm] : r.permissions.filter(p => p !== perm)
                          updateItem("roles", i, "permissions", perms)
                        }} />
                      {perm.replace(/_/g, " ")}
                    </label>
                  ))}
                </div>
                {data.roles.length > 1 && (
                  <Button variant="outline" size="sm" onClick={() => removeItem("roles", i)}>Remove Role</Button>
                )}
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => addItem("roles", { name: "", permissions: [] })}>
              + Add Role
            </Button>
          </div>
        )

      case 9:
        return (
          <div className="space-y-4">
            <h3 className="font-medium text-gray-900">Review Your SRS</h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="p-3 rounded-lg bg-gray-50">
                <p className="font-medium text-gray-900">Organisation</p>
                <p className="text-gray-500">{data.org_name || "Not set"} &middot; {data.sector || "No sector"}</p>
                <p className="text-gray-500">{data.geography || "No geography"}</p>
              </div>
              <div className="p-3 rounded-lg bg-gray-50">
                <p className="font-medium text-gray-900">Subject Types ({data.subject_types.filter(s => s.name).length})</p>
                {data.subject_types.filter(s => s.name).map(s => (
                  <Badge key={s.name} variant="outline" className="mr-1 mt-1">{s.name} ({s.type})</Badge>
                ))}
              </div>
              <div className="p-3 rounded-lg bg-gray-50">
                <p className="font-medium text-gray-900">Programs ({data.programs.filter(p => p.name).length})</p>
                {data.programs.filter(p => p.name).map(p => (
                  <Badge key={p.name} variant="outline" className="mr-1 mt-1">{p.name}</Badge>
                ))}
              </div>
              <div className="p-3 rounded-lg bg-gray-50">
                <p className="font-medium text-gray-900">Encounters ({data.encounter_types.filter(e => e.name).length})</p>
                {data.encounter_types.filter(e => e.name).map(e => (
                  <Badge key={e.name} variant="outline" className="mr-1 mt-1">{e.name}</Badge>
                ))}
              </div>
              <div className="p-3 rounded-lg bg-gray-50">
                <p className="font-medium text-gray-900">Registration Fields ({data.registration_fields.filter(f => f.name).length})</p>
              </div>
              <div className="p-3 rounded-lg bg-gray-50">
                <p className="font-medium text-gray-900">Encounter Fields ({data.encounter_fields.filter(f => f.name).length})</p>
              </div>
              <div className="p-3 rounded-lg bg-gray-50">
                <p className="font-medium text-gray-900">Dashboards ({data.dashboards.filter(d => d.name).length})</p>
              </div>
              <div className="p-3 rounded-lg bg-gray-50">
                <p className="font-medium text-gray-900">Roles ({data.roles.filter(r => r.name).length})</p>
                {data.roles.filter(r => r.name).map(r => (
                  <Badge key={r.name} variant="outline" className="mr-1 mt-1">{r.name}</Badge>
                ))}
              </div>
            </div>
          </div>
        )

      default:
        return null
    }
  }

  const StepIcon = STEPS[step].icon

  return (
    <Card className="w-full max-w-3xl mx-auto">
      <CardHeader>
        <div className="flex items-center gap-4 mb-4">
          {STEPS.map((s, i) => {
            const Icon = s.icon
            return (
              <button key={i} onClick={() => setStep(i)}
                className={`flex items-center justify-center w-8 h-8 rounded-full text-xs font-medium transition-colors ${
                  i === step ? "bg-primary-500 text-white" : i < step ? "bg-success-500 text-white" : "bg-gray-200 text-gray-500"
                }`} title={s.label}>
                {i < step ? <Check className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
              </button>
            )
          })}
        </div>
        <CardTitle className="flex items-center gap-2">
          <StepIcon className="h-5 w-5 text-primary-500" />
          Step {step + 1}: {STEPS[step].label}
        </CardTitle>
        <p className="text-sm text-gray-500">{STEPS[step].description}</p>
      </CardHeader>

      <CardContent>{renderStep()}</CardContent>

      <CardFooter className="flex justify-between">
        <Button variant="outline" onClick={() => setStep(s => s - 1)} disabled={step === 0}>
          <ChevronLeft className="h-4 w-4 mr-1" /> Back
        </Button>
        {step < STEPS.length - 1 ? (
          <Button onClick={() => setStep(s => s + 1)}>
            Next <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        ) : (
          <Button onClick={handleGenerate} className="gap-2">
            <Sparkles className="h-4 w-4" /> Generate Bundle
          </Button>
        )}
      </CardFooter>
    </Card>
  )
}
