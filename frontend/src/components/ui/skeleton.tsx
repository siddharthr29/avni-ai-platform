import { cn } from '../../lib/utils';

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-gray-200', className)} />;
}

export function MessageSkeleton() {
  return (
    <div className="space-y-4 px-4 py-3">
      {/* Assistant message skeleton */}
      <div className="flex justify-start">
        <div className="max-w-[80%] space-y-2">
          <Skeleton className="h-4 w-72" />
          <Skeleton className="h-4 w-56" />
          <Skeleton className="h-4 w-40" />
        </div>
      </div>
      {/* User message skeleton */}
      <div className="flex justify-end">
        <div className="max-w-[80%] space-y-2">
          <Skeleton className="h-4 w-48 bg-teal-100" />
        </div>
      </div>
      {/* Another assistant message skeleton */}
      <div className="flex justify-start">
        <div className="max-w-[80%] space-y-2">
          <Skeleton className="h-4 w-64" />
          <Skeleton className="h-4 w-80" />
          <Skeleton className="h-4 w-52" />
        </div>
      </div>
    </div>
  );
}

export function SidebarSkeleton() {
  return (
    <div className="space-y-3 px-3 py-2">
      {/* Group label */}
      <Skeleton className="h-3 w-16 mb-2" />
      {/* Session items */}
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-center gap-2 px-2 py-2.5">
          <Skeleton className="h-1.5 w-1.5 rounded-full shrink-0" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-full" />
            <Skeleton className="h-2.5 w-20" />
          </div>
        </div>
      ))}
      {/* Another group */}
      <Skeleton className="h-3 w-20 mt-4 mb-2" />
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={`old-${i}`} className="flex items-center gap-2 px-2 py-2.5">
          <Skeleton className="h-1.5 w-1.5 rounded-full shrink-0" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-full" />
            <Skeleton className="h-2.5 w-24" />
          </div>
        </div>
      ))}
    </div>
  );
}
