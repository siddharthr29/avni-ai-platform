import clsx from 'clsx';

interface MessageMetadataProps {
  timestamp: Date;
  isUser: boolean;
}

export function MessageMetadata({ timestamp, isUser }: MessageMetadataProps) {
  return (
    <div className={clsx(
      'text-xs mt-1.5',
      isUser ? 'text-white/70' : 'text-gray-500'
    )}>
      {new Date(timestamp).toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
      })}
    </div>
  );
}
