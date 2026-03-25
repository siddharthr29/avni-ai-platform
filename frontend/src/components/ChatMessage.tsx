import { memo, useState } from 'react';
import { AlertCircle, RefreshCw, ClipboardCheck } from 'lucide-react';
import type { Message } from '../types';
import { FieldMapping } from './FieldMapping';
import { BundlePreview } from './BundlePreview';
import { BundleReviewWizard } from './BundleReviewWizard';
import { RuleDisplay } from './RuleDisplay';
import { WorkflowProgress } from './WorkflowProgress';
import { CheckpointCard } from './CheckpointCard';
import { AmbiguityResolver } from './AmbiguityResolver';
import { MessageBubble, LoadingBubble } from './chat/MessageBubble';
import { MessageContent } from './chat/MessageContent';
import { MessageMetadata } from './chat/MessageMetadata';
import { MessageFeedback } from './chat/MessageFeedback';
import { MessageAttachments } from './chat/MessageAttachments';
import { ProgressIndicator, ExtractedDataTable } from './chat/MetadataWidgets';

interface ChatMessageProps {
  message: Message;
  onToast: (type: 'success' | 'error' | 'info', message: string) => void;
  isLoading?: boolean;
  isLastMessage?: boolean;
  onRetry?: () => void;
  onOpenArtifact?: (messageId: string, attachment: { name: string; data: string; mimeType: string }) => void;
  sessionId?: string;
  onCheckpointApprove?: (workflowId: string, stepId: string, feedback?: string) => void;
  onCheckpointReject?: (workflowId: string, stepId: string, feedback: string) => void;
  onClarificationSubmit?: (answers: Record<string, string>) => void;
}

export const ChatMessage = memo(function ChatMessage({ message, onToast, isLoading, isLastMessage, onRetry, onOpenArtifact, sessionId, onCheckpointApprove, onCheckpointReject, onClarificationSubmit }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';
  const isStreaming = isAssistant && isLastMessage && isLoading;
  const metaType = message.metadata?.type;
  const [showReviewWizard, setShowReviewWizard] = useState(false);

  // Loading state: empty assistant message
  if (!isUser && !message.content && !metaType) {
    return <LoadingBubble />;
  }

  return (
    <MessageBubble role={message.role} isStreaming={isStreaming}>
      {/* Attachments */}
      <MessageAttachments
        attachments={message.attachments ?? []}
        messageId={message.id}
        isUser={isUser}
        onOpenArtifact={onOpenArtifact}
      />

      {/* Content with streaming cursor */}
      <div className="relative">
        <MessageContent content={message.content} isUser={isUser} />
        {isStreaming && message.content && (
          <span className="streaming-cursor">&#9613;</span>
        )}
      </div>

      {/* Metadata-based widgets */}
      {metaType === 'progress' && message.metadata?.progress && (
        <ProgressIndicator progress={message.metadata.progress} />
      )}
      {metaType === 'voice_mapped' && message.metadata?.fields && message.metadata?.confidence && (
        <FieldMapping fields={message.metadata.fields} confidence={message.metadata.confidence} onToast={onToast} />
      )}
      {metaType === 'image_extracted' && (
        <ExtractedDataTable
          records={message.metadata?.records ?? []}
          warnings={message.metadata?.warnings ?? []}
          onOpenAsArtifact={onOpenArtifact ? (records) => {
            const headers = Object.keys(records[0] || {});
            const rows = records.map(r => headers.map(h => String(r[h] ?? '')));
            const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
            onOpenArtifact(message.id, { name: 'extracted-data.csv', data: btoa(csv), mimeType: 'text/csv' });
          } : undefined}
        />
      )}
      {metaType === 'bundle_ready' && (
        <>
          <BundlePreview files={message.metadata?.bundleFiles} downloadUrl={message.metadata?.downloadUrl} bundleId={message.metadata?.bundleId} onToast={onToast} />
          {message.metadata?.bundleId && !showReviewWizard && (
            <button
              onClick={() => setShowReviewWizard(true)}
              className="mt-2 flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-teal-700 bg-teal-50 hover:bg-teal-100 border border-teal-200 rounded-lg transition-colors"
            >
              <ClipboardCheck className="w-4 h-4" />
              Review Before Download
            </button>
          )}
          {showReviewWizard && message.metadata?.bundleId && (
            <div className="mt-3">
              <BundleReviewWizard
                bundleId={message.metadata.bundleId}
                onClose={() => setShowReviewWizard(false)}
                onToast={onToast}
              />
            </div>
          )}
        </>
      )}
      {metaType === 'rule' && message.metadata?.code && (
        <div className="mt-2">
          <RuleDisplay code={message.metadata.code} ruleType={message.metadata.ruleType} />
        </div>
      )}
      {/* Workflow progress, checkpoint, clarification */}
      {metaType === 'workflow_progress' && message.metadata && (
        <div className="mt-2">
          <WorkflowProgress
            workflowId={message.metadata.workflowId ?? ''}
            name={(message.metadata as any).workflowName ?? 'Workflow'}
            steps={(message.metadata as any).steps ?? []}
            currentStepIndex={(message.metadata as any).currentStepIndex ?? 0}
            status={(message.metadata as any).workflowStatus ?? 'running'}
            currentDetail={(message.metadata as any).currentDetail}
            provider={(message.metadata as any).provider}
            tokensUsed={(message.metadata as any).tokensUsed}
            tokensBudget={(message.metadata as any).tokensBudget}
          />
        </div>
      )}
      {metaType === 'checkpoint' && message.metadata?.step && onCheckpointApprove && onCheckpointReject && (
        <div className="mt-2">
          <CheckpointCard
            workflowId={message.metadata.workflowId ?? ''}
            stepId={message.metadata.step.id}
            stepName={message.metadata.step.name}
            checkpointLevel={message.metadata.needs === 'approval' ? 'approve' : message.metadata.needs === 'input' ? 'block' : 'review'}
            summary={message.metadata.resultSummary ?? ''}
            details={(message.metadata as any).details}
            onApprove={onCheckpointApprove}
            onReject={onCheckpointReject}
          />
        </div>
      )}
      {metaType === 'clarification' && message.metadata?.questions && onClarificationSubmit && (
        <div className="mt-2">
          <AmbiguityResolver
            questions={message.metadata.questions}
            onSubmit={onClarificationSubmit}
            similarOrgs={(message.metadata as any).similarOrgs}
          />
        </div>
      )}
      {metaType === 'error' && (
        <>
          <div className="mt-2 flex items-start gap-2 bg-red-50 text-red-700 rounded-lg px-3 py-2 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{message.content}</span>
          </div>
          {onRetry && (
            <button onClick={onRetry} className="mt-2 flex items-center gap-1.5 text-xs text-red-600 hover:text-red-800 hover:bg-red-50 rounded-md px-2 py-1 transition-colors">
              <RefreshCw className="w-3.5 h-3.5" /> Retry
            </button>
          )}
        </>
      )}

      {/* Feedback + copy (assistant only, not streaming) */}
      {isAssistant && message.content && !isStreaming && (
        <MessageFeedback messageId={message.id} sessionId={sessionId} content={message.content} onToast={onToast} />
      )}

      {/* Timestamp */}
      <MessageMetadata timestamp={message.timestamp} isUser={isUser} />
    </MessageBubble>
  );
});
