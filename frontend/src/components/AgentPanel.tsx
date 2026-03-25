import { useState, useEffect } from "react"
import { authFetch } from "../services/api"
import { Card, CardHeader, CardTitle, CardContent } from "./ui/card"
import { Badge } from "./ui/badge"
import { Button } from "./ui/button"
import { Input } from "./ui/input"
import { Alert } from "./ui/alert"
import { Bot, CheckCircle, AlertCircle, Clock, ArrowRight, Send, Loader2 } from "lucide-react"

interface AgentStep {
  step: number
  thought: string
  action: string
  input: Record<string, any>
  observation: string
  status: string
  retries: number
  duration_ms: number
}

interface AgentTaskData {
  task_id: string
  goal: string
  status: string
  steps: AgentStep[]
  error: string
  step_count: number
}

interface AgentPanelProps {
  taskId?: string
  onNewTask?: (goal: string, authToken: string) => Promise<AgentTaskData>
}

const statusColors: Record<string, string> = {
  success: "text-success",
  failed: "text-danger",
  needs_retry: "text-warning",
  needs_user: "text-info",
}

const statusIcons: Record<string, any> = {
  running: Loader2,
  completed: CheckCircle,
  failed: AlertCircle,
  needs_user: Clock,
}

export function AgentPanel({ taskId: initialTaskId, onNewTask: _onNewTask }: AgentPanelProps) {
  const [task, setTask] = useState<AgentTaskData | null>(null)
  const [userInput, setUserInput] = useState("")
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (initialTaskId) {
      pollTask(initialTaskId)
    }
  }, [initialTaskId])

  async function pollTask(id: string) {
    try {
      const resp = await authFetch(`/api/agent/task/${id}`)
      if (resp.ok) {
        setTask(await resp.json())
      }
    } catch {}
  }

  async function handleResume() {
    if (!task || !userInput.trim()) return
    setLoading(true)
    try {
      const resp = await authFetch(`/api/agent/resume/${task.task_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_response: userInput }),
      })
      if (resp.ok) {
        setTask(await resp.json())
        setUserInput("")
      }
    } catch {}
    setLoading(false)
  }

  if (!task) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12 text-muted">
          <Bot className="h-8 w-8 mr-3 opacity-50" />
          No active agent task
        </CardContent>
      </Card>
    )
  }

  const StatusIcon = statusIcons[task.status] || Clock

  return (
    <Card className="w-full">
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-primary" />
            Agent Task
          </CardTitle>
          <p className="text-sm text-muted mt-1">{task.goal}</p>
        </div>
        <Badge
          variant={task.status === "completed" ? "success" : task.status === "failed" ? "danger" : "default"}
          className="gap-1"
        >
          <StatusIcon className={`h-3 w-3 ${task.status === "running" ? "animate-spin" : ""}`} />
          {task.status}
        </Badge>
      </CardHeader>

      <CardContent className="space-y-3">
        {task.steps.map((step) => (
          <div key={step.step} className="border border-border rounded-lg p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono text-muted">Step {step.step}</span>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-xs">{step.action}</Badge>
                <span className={`text-xs ${statusColors[step.status] || "text-muted"}`}>
                  {step.status}
                </span>
                <span className="text-xs text-muted">{step.duration_ms}ms</span>
              </div>
            </div>
            <p className="text-sm text-dark">
              <span className="font-medium">Thought:</span> {step.thought}
            </p>
            {step.observation && (
              <p className="text-sm text-muted">
                <ArrowRight className="inline h-3 w-3 mr-1" />
                {step.observation.slice(0, 300)}
              </p>
            )}
            {step.retries > 0 && (
              <span className="text-xs text-warning">Retries: {step.retries}</span>
            )}
          </div>
        ))}

        {task.error && (
          <Alert variant="danger" title="Agent Error">
            {task.error}
          </Alert>
        )}

        {task.status === "needs_user" && (
          <div className="flex gap-2 mt-4">
            <Input
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              placeholder="Type your response..."
              onKeyDown={(e) => e.key === "Enter" && handleResume()}
            />
            <Button onClick={handleResume} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
