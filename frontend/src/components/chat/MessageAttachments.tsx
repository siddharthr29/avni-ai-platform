import { FileSpreadsheet } from 'lucide-react';
import type { Attachment } from '../../types';

interface MessageAttachmentsProps {
  attachments: Attachment[];
  messageId: string;
  isUser: boolean;
  onOpenArtifact?: (messageId: string, attachment: { name: string; data: string; mimeType: string }) => void;
}

export function MessageAttachments({ attachments, messageId, isUser, onOpenArtifact }: MessageAttachmentsProps) {
  if (!attachments || attachments.length === 0) return null;

  if (isUser) {
    return (
      <div className="flex flex-wrap gap-2 mb-2">
        {attachments.map((att, i) => {
          const isSpreadsheet = att.type === 'file' && /\.(csv|xlsx|xls|tsv)$/i.test(att.name);
          return (
            <div key={i} className="flex items-center gap-1.5 bg-white/20 rounded-lg px-2 py-1.5 text-xs text-white/90">
              {att.type === 'image' ? (
                <img
                  src={att.previewUrl ?? `data:${att.mimeType};base64,${att.data}`}
                  alt={att.name}
                  className="w-16 h-16 object-cover rounded"
                />
              ) : (
                <>
                  {isSpreadsheet && <FileSpreadsheet className="w-3.5 h-3.5 shrink-0" />}
                  <span className="truncate max-w-[120px]">{att.name}</span>
                  {isSpreadsheet && onOpenArtifact && (
                    <button
                      onClick={() => onOpenArtifact(messageId, att)}
                      className="ml-1 px-1.5 py-0.5 rounded bg-white/30 hover:bg-white/50 text-[10px] font-medium transition-colors"
                    >
                      Edit
                    </button>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  // Assistant attachments (if any in future)
  return (
    <div className="flex flex-wrap gap-2 mb-2">
      {attachments.map((att, i) => (
        <div key={i} className="flex items-center gap-1.5 bg-gray-100 rounded-lg px-2 py-1.5 text-xs text-gray-600">
          <FileSpreadsheet className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate max-w-[120px]">{att.name}</span>
        </div>
      ))}
    </div>
  );
}
