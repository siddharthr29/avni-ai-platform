import { useState, useCallback, useRef, useEffect } from 'react';
import type { Workflow, WorkflowStep } from '../types';
import {
  startWorkflow,
  getWorkflowStatus,
  approveStep,
  rejectStep,
  provideStepInput,
  cancelWorkflow,
  subscribeToWorkflow,
} from '../services/api';

function updateStepStatus(workflow: Workflow | null, event: any): Workflow | null {
  if (!workflow) return null;

  const stepData = event.step;
  if (!stepData) return workflow;

  return {
    ...workflow,
    status: event.type === 'workflow_completed'
      ? 'completed'
      : event.type === 'workflow_failed'
        ? 'failed'
        : workflow.status,
    current_step_index: event.type === 'step_completed'
      ? workflow.current_step_index + 1
      : workflow.current_step_index,
    steps: workflow.steps.map(s =>
      s.id === stepData.id ? { ...s, ...stepData } : s
    ),
  };
}

function calculateProgress(workflow: Workflow | null): number {
  if (!workflow || workflow.steps.length === 0) return 0;
  const completedCount = workflow.steps.filter(
    s => s.status === 'completed' || s.status === 'approved'
  ).length;
  return Math.round((completedCount / workflow.steps.length) * 100);
}

interface UseWorkflowReturn {
  workflow: Workflow | null;
  events: any[];
  startBundleWorkflow: (srsData: any, orgContext: any) => Promise<void>;
  approve: (stepId: string, feedback?: string) => Promise<void>;
  reject: (stepId: string, feedback: string) => Promise<void>;
  provideInput: (stepId: string, data: any) => Promise<void>;
  cancel: () => Promise<void>;
  refresh: () => Promise<void>;
  isRunning: boolean;
  isPaused: boolean;
  currentStep: WorkflowStep | undefined;
  progress: number;
  error: string | null;
}

export function useWorkflow(): UseWorkflowReturn {
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Clean up SSE on unmount
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  const startBundleWorkflow = useCallback(async (srsData: any, orgContext: any) => {
    setError(null);
    setEvents([]);

    // Close any existing SSE connection
    eventSourceRef.current?.close();

    try {
      const wf = await startWorkflow('bundle_generation', {
        srs_data: srsData,
        org_context: orgContext,
      });
      setWorkflow(wf);

      // Subscribe to SSE events
      const es = subscribeToWorkflow(wf.id, (event) => {
        setEvents(prev => [...prev, event]);

        // Update workflow state from events
        if (event.type === 'step_started' || event.type === 'step_completed' || event.type === 'step_failed') {
          setWorkflow(prev => updateStepStatus(prev, event));
        }

        if (event.type === 'checkpoint') {
          setWorkflow(prev => prev ? {
            ...prev,
            status: 'paused',
            steps: prev.steps.map(s =>
              s.id === event.step?.id ? { ...s, ...event.step } : s
            ),
          } : null);
        }

        if (event.type === 'workflow_completed') {
          setWorkflow(prev => prev ? { ...prev, status: 'completed' } : null);
        }

        if (event.type === 'workflow_failed') {
          setWorkflow(prev => prev ? { ...prev, status: 'failed' } : null);
          setError(event.error || 'Workflow failed');
        }
      });

      eventSourceRef.current = es;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      throw err;
    }
  }, []);

  const approve = useCallback(async (stepId: string, feedback?: string) => {
    if (!workflow) return;
    try {
      await approveStep(workflow.id, stepId, feedback);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [workflow]);

  const reject = useCallback(async (stepId: string, feedback: string) => {
    if (!workflow) return;
    try {
      await rejectStep(workflow.id, stepId, feedback);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [workflow]);

  const provideInputFn = useCallback(async (stepId: string, data: any) => {
    if (!workflow) return;
    try {
      await provideStepInput(workflow.id, stepId, data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [workflow]);

  const cancelFn = useCallback(async () => {
    if (!workflow) return;
    try {
      await cancelWorkflow(workflow.id);
      eventSourceRef.current?.close();
      setWorkflow(prev => prev ? { ...prev, status: 'cancelled' } : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [workflow]);

  const refresh = useCallback(async () => {
    if (!workflow) return;
    try {
      const updated = await getWorkflowStatus(workflow.id);
      setWorkflow(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [workflow]);

  return {
    workflow,
    events,
    startBundleWorkflow,
    approve,
    reject,
    provideInput: provideInputFn,
    cancel: cancelFn,
    refresh,
    isRunning: workflow?.status === 'running',
    isPaused: workflow?.status === 'paused',
    currentStep: workflow ? workflow.steps[workflow.current_step_index] : undefined,
    progress: calculateProgress(workflow),
    error,
  };
}
