import React, { useState, useEffect, useCallback } from "react"
import { Button } from "./ui/button"
import { Badge } from "./ui/badge"
import { X, ChevronLeft, ChevronRight, Sparkles } from "lucide-react"
import { cn } from "../lib/utils"

interface TourStep {
  target: string  // CSS selector for the element to highlight
  title: string
  description: string
  position: "top" | "bottom" | "left" | "right"
}

const TOUR_STEPS: TourStep[] = [
  {
    target: "[data-tour='org-context']",
    title: "Connect Your Organisation",
    description: "Start by connecting to your Avni organisation. Paste your AUTH-TOKEN from Avni to enable bundle uploads and org management.",
    position: "right",
  },
  {
    target: "[data-tour='chat']",
    title: "Chat with Avni AI",
    description: "Ask questions about Avni, get help with rules, troubleshoot issues, or request bundle generation. The AI knows 36,000+ knowledge chunks from real implementations.",
    position: "bottom",
  },
  {
    target: "[data-tour='srs-wizard']",
    title: "SRS Creation Wizard",
    description: "Create a Software Requirements Specification in 10 guided steps. Define subject types, programs, encounters, forms, and schedules -- then generate a ready-to-upload bundle.",
    position: "bottom",
  },
  {
    target: "[data-tour='bundle-review']",
    title: "Review & Upload Bundles",
    description: "Review generated bundles before uploading. Edit JSON files, run validation checks, and preview what changes will be applied to your org.",
    position: "bottom",
  },
  {
    target: "[data-tour='agent']",
    title: "Autonomous Agent",
    description: "Let the AI agent handle complex multi-step tasks autonomously. It plans, executes MCP tools, validates bundles, and self-corrects errors.",
    position: "bottom",
  },
  {
    target: "[data-tour='usage']",
    title: "Track Your Progress",
    description: "Monitor platform usage: bundles generated, hours saved, and the 30% effort reduction target from the Avni Concept Note.",
    position: "bottom",
  },
]

const STORAGE_KEY = "avni_tour_completed"

interface ProductTourProps {
  onComplete?: () => void
}

export function ProductTour({ onComplete }: ProductTourProps) {
  const [active, setActive] = useState(false)
  const [step, setStep] = useState(0)
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null)

  useEffect(() => {
    // Auto-start for first-time users
    const completed = localStorage.getItem(STORAGE_KEY)
    if (!completed) {
      // Small delay to let the app render
      const timer = setTimeout(() => setActive(true), 1500)
      return () => clearTimeout(timer)
    }
  }, [])

  useEffect(() => {
    if (!active) return
    const currentStep = TOUR_STEPS[step]
    const el = document.querySelector(currentStep.target)
    if (el) {
      const rect = el.getBoundingClientRect()
      setTargetRect(rect)
      el.scrollIntoView({ behavior: "smooth", block: "center" })
    } else {
      setTargetRect(null)
    }
  }, [active, step])

  // Recalculate position on window resize
  useEffect(() => {
    if (!active) return
    const handleResize = () => {
      const currentStep = TOUR_STEPS[step]
      const el = document.querySelector(currentStep.target)
      if (el) {
        setTargetRect(el.getBoundingClientRect())
      }
    }
    window.addEventListener("resize", handleResize)
    return () => window.removeEventListener("resize", handleResize)
  }, [active, step])

  const finish = useCallback(() => {
    setActive(false)
    localStorage.setItem(STORAGE_KEY, "true")
    onComplete?.()
  }, [onComplete])

  const next = () => {
    if (step < TOUR_STEPS.length - 1) {
      setStep(s => s + 1)
    } else {
      finish()
    }
  }

  const prev = () => {
    if (step > 0) setStep(s => s - 1)
  }

  if (!active) {
    return (
      <button
        onClick={() => { setStep(0); setActive(true) }}
        className="fixed bottom-4 right-4 z-40 flex items-center gap-2 px-4 py-2 rounded-full bg-primary-500 text-white shadow-lg hover:bg-primary-600 transition-colors text-sm"
        title="Start product tour"
      >
        <Sparkles className="h-4 w-4" />
        Tour
      </button>
    )
  }

  const currentStep = TOUR_STEPS[step]

  // Calculate tooltip position
  let tooltipStyle: React.CSSProperties = {}
  if (targetRect) {
    const padding = 12
    switch (currentStep.position) {
      case "bottom":
        tooltipStyle = {
          top: targetRect.bottom + padding,
          left: Math.max(16, targetRect.left + targetRect.width / 2 - 160),
        }
        break
      case "top":
        tooltipStyle = {
          bottom: window.innerHeight - targetRect.top + padding,
          left: Math.max(16, targetRect.left + targetRect.width / 2 - 160),
        }
        break
      case "right":
        tooltipStyle = {
          top: targetRect.top + targetRect.height / 2 - 60,
          left: targetRect.right + padding,
        }
        break
      case "left":
        tooltipStyle = {
          top: targetRect.top + targetRect.height / 2 - 60,
          right: window.innerWidth - targetRect.left + padding,
        }
        break
    }
  } else {
    // Center on screen if target not found
    tooltipStyle = {
      top: "50%",
      left: "50%",
      transform: "translate(-50%, -50%)",
    }
  }

  return (
    <>
      {/* Backdrop with spotlight cutout */}
      <div className="fixed inset-0 z-50">
        {/* Dark overlay */}
        <div className="absolute inset-0 bg-black/60" onClick={finish} />

        {/* Spotlight cutout */}
        {targetRect && (
          <div
            className="absolute rounded-lg ring-4 ring-primary-400 ring-offset-4 ring-offset-transparent"
            style={{
              top: targetRect.top - 4,
              left: targetRect.left - 4,
              width: targetRect.width + 8,
              height: targetRect.height + 8,
              backgroundColor: "transparent",
              boxShadow: "0 0 0 9999px rgba(0,0,0,0.6)",
              zIndex: 51,
            }}
          />
        )}
      </div>

      {/* Tooltip */}
      <div
        className="fixed z-[52] w-80 rounded-xl bg-white shadow-2xl border border-gray-200 p-5"
        style={tooltipStyle}
      >
        <div className="flex items-center justify-between mb-3">
          <Badge variant="default" className="text-xs">
            Step {step + 1} of {TOUR_STEPS.length}
          </Badge>
          <button onClick={finish} className="text-gray-400 hover:text-gray-600">
            <X className="h-4 w-4" />
          </button>
        </div>

        <h3 className="font-semibold text-gray-900 mb-2">{currentStep.title}</h3>
        <p className="text-sm text-gray-600 mb-4 leading-relaxed">{currentStep.description}</p>

        <div className="flex items-center justify-between">
          <button
            onClick={finish}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            Skip tour
          </button>
          <div className="flex gap-2">
            {step > 0 && (
              <Button variant="outline" size="sm" onClick={prev}>
                <ChevronLeft className="h-3 w-3 mr-1" /> Back
              </Button>
            )}
            <Button size="sm" onClick={next}>
              {step < TOUR_STEPS.length - 1 ? (
                <>Next <ChevronRight className="h-3 w-3 ml-1" /></>
              ) : (
                "Finish"
              )}
            </Button>
          </div>
        </div>

        {/* Step dots */}
        <div className="flex justify-center gap-1.5 mt-3">
          {TOUR_STEPS.map((_, i) => (
            <div
              key={i}
              className={cn(
                "w-1.5 h-1.5 rounded-full transition-colors",
                i === step ? "bg-primary-500" : i < step ? "bg-primary-200" : "bg-gray-200"
              )}
            />
          ))}
        </div>
      </div>
    </>
  )
}
