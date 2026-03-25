import * as React from "react"
import { cn } from "../../lib/utils"
import { AlertCircle, CheckCircle, Info, AlertTriangle } from "lucide-react"

const variants = {
  default: "bg-surface border-border text-body",
  success: "bg-success-light border-success text-success",
  danger: "bg-danger-light border-danger text-danger",
  warning: "bg-warning-light border-warning text-dark",
  info: "bg-info-light border-info text-dark",
}

const icons = {
  default: Info,
  success: CheckCircle,
  danger: AlertCircle,
  warning: AlertTriangle,
  info: Info,
}

interface AlertProps {
  variant?: keyof typeof variants
  children: React.ReactNode
  className?: string
  title?: string
}

export function Alert({ variant = "default", children, className, title }: AlertProps) {
  const Icon = icons[variant]
  return (
    <div className={cn("flex gap-3 rounded-lg border p-4", variants[variant], className)}>
      <Icon className="h-5 w-5 shrink-0 mt-0.5" />
      <div className="flex-1">
        {title && <h5 className="mb-1 font-medium">{title}</h5>}
        <div className="text-sm">{children}</div>
      </div>
    </div>
  )
}
