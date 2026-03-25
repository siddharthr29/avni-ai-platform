import { useEffect } from 'react';
import { X, CheckCircle, AlertCircle, Info } from 'lucide-react';
import clsx from 'clsx';
import type { Toast as ToastType } from '../types';

interface ToastContainerProps {
  toasts: ToastType[];
  onDismiss: (id: string) => void;
}

function ToastIcon({ type }: { type: ToastType['type'] }) {
  switch (type) {
    case 'success':
      return <CheckCircle className="w-5 h-5 text-green-500 shrink-0" />;
    case 'error':
      return <AlertCircle className="w-5 h-5 text-red-500 shrink-0" />;
    case 'info':
      return <Info className="w-5 h-5 text-blue-500 shrink-0" />;
  }
}

function ToastItem({ toast, onDismiss }: { toast: ToastType; onDismiss: (id: string) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => {
      onDismiss(toast.id);
    }, 5000);

    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  return (
    <div
      role={toast.type === 'error' ? 'alert' : 'status'}
      className={clsx(
        'flex items-start gap-3 px-4 py-3 rounded-lg shadow-lg border max-w-sm w-full',
        'animate-[slideIn_0.3s_ease-out]',
        toast.type === 'success' && 'bg-green-50 border-green-200',
        toast.type === 'error' && 'bg-red-50 border-red-200',
        toast.type === 'info' && 'bg-blue-50 border-blue-200'
      )}
    >
      <ToastIcon type={toast.type} />
      <p className="text-sm text-gray-800 flex-1">{toast.message}</p>
      <button
        onClick={() => onDismiss(toast.id)}
        className="p-2 min-w-[44px] min-h-[44px] flex items-center justify-center rounded hover:bg-gray-100 transition-colors shrink-0"
        aria-label="Dismiss"
      >
        <X className="w-4 h-4 text-gray-400" />
      </button>
    </div>
  );
}

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2" aria-live="polite">
      {toasts.map(toast => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
