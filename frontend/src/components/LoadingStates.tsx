export function MessageSkeleton() {
  return (
    <div className="px-4 py-4 max-w-2xl mx-auto">
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-gray-200 shimmer shrink-0" />
        <div className="flex-1 space-y-2.5 pt-1">
          <div className="h-3.5 bg-gray-200 rounded shimmer w-3/4" />
          <div className="h-3.5 bg-gray-200 rounded shimmer w-1/2" />
          <div className="h-3.5 bg-gray-200 rounded shimmer w-5/6" />
        </div>
      </div>
    </div>
  );
}

export function BundleSkeleton() {
  return (
    <div className="p-4 border border-gray-200 rounded-xl space-y-3">
      <div className="flex items-center gap-2">
        <div className="w-5 h-5 rounded bg-gray-200 shimmer" />
        <div className="h-3.5 bg-gray-200 rounded shimmer w-32" />
      </div>
      <div className="pl-7 space-y-2">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-gray-200 shimmer" />
          <div className="h-3 bg-gray-200 rounded shimmer w-24" />
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-gray-200 shimmer" />
          <div className="h-3 bg-gray-200 rounded shimmer w-28" />
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-gray-200 shimmer" />
          <div className="h-3 bg-gray-200 rounded shimmer w-20" />
        </div>
        <div className="pl-6 space-y-2">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-gray-200 shimmer" />
            <div className="h-3 bg-gray-200 rounded shimmer w-36" />
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-gray-200 shimmer" />
            <div className="h-3 bg-gray-200 rounded shimmer w-32" />
          </div>
        </div>
      </div>
    </div>
  );
}

export function TableSkeleton({ rows = 4, cols = 3 }: { rows?: number; cols?: number }) {
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex gap-4 p-3 bg-gray-50 border-b border-gray-200">
        {Array.from({ length: cols }).map((_, i) => (
          <div
            key={i}
            className="h-3.5 bg-gray-200 rounded shimmer flex-1"
          />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div
          key={rowIdx}
          className="flex gap-4 p-3 border-b border-gray-100 last:border-b-0"
        >
          {Array.from({ length: cols }).map((_, colIdx) => (
            <div
              key={colIdx}
              className="h-3 bg-gray-200 rounded shimmer flex-1"
              style={{ animationDelay: `${(rowIdx * cols + colIdx) * 0.05}s` }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const sizeClasses = {
    sm: 'w-4 h-4 border-2',
    md: 'w-6 h-6 border-2',
    lg: 'w-8 h-8 border-3',
  };

  return (
    <div
      className={`${sizeClasses[size]} border-gray-200 border-t-primary-600 rounded-full spinner`}
      role="status"
      aria-label="Loading"
    />
  );
}
