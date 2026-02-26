import { Menu, Settings } from 'lucide-react';

interface HeaderProps {
  onToggleSidebar: () => void;
}

export function Header({ onToggleSidebar }: HeaderProps) {
  return (
    <header className="h-14 border-b border-gray-200 bg-white flex items-center px-4 shrink-0">
      <button
        onClick={onToggleSidebar}
        className="p-2 rounded-lg hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 mr-3"
        aria-label="Toggle sidebar"
      >
        <Menu className="w-5 h-5 text-gray-600" />
      </button>

      <div className="flex items-center gap-2">
        <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
          <span className="text-white font-bold text-sm">A</span>
        </div>
        <div>
          <h1 className="text-base font-semibold text-gray-900 leading-tight">Avni AI</h1>
          <p className="text-xs text-gray-500 leading-tight">Implementation Platform</p>
        </div>
      </div>

      <div className="ml-auto">
        <button
          className="p-2 rounded-lg hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
          aria-label="Settings"
        >
          <Settings className="w-5 h-5 text-gray-500" />
        </button>
      </div>
    </header>
  );
}
