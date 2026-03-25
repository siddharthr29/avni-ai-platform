import { ArrowRight, MessageSquare, Package, BookOpen, Shield, Zap, Globe } from 'lucide-react';
import { AvniLogo } from './AvniLogo';

interface LandingPageProps {
  onStart: () => void;
  onAbout?: () => void;
}

export function LandingPage({ onStart, onAbout }: LandingPageProps) {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      {/* ── Header ── */}
      <header className="sticky top-0 z-50 bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AvniLogo size={32} variant="full" />
          </div>
          <nav className="flex items-center gap-5">
            <a
              href="https://avniproject.org"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors hidden sm:inline"
            >
              Avni Project
            </a>
            <a
              href="https://avni.readme.io"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors hidden sm:inline"
            >
              Docs
            </a>
            {onAbout && (
              <button
                onClick={onAbout}
                className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
              >
                About
              </button>
            )}
            <button
              onClick={onStart}
              className="px-5 py-2 bg-teal-700 hover:bg-teal-800 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Sign In
            </button>
          </nav>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="flex-1 flex items-center">
        <div className="max-w-6xl mx-auto px-6 py-20 w-full">
          <div className="max-w-3xl">
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 leading-[1.1] tracking-tight">
              <span className="text-teal-700">Avni</span> hai T<span className="text-teal-700">AI</span>yaar
            </h1>
            <p className="mt-2 text-lg text-teal-700 font-medium">
              Set up your Avni app in hours, not weeks
            </p>
            <p className="mt-6 text-lg text-gray-600 leading-relaxed max-w-xl">
              Upload your scoping sheet, chat about requirements, generate implementation bundles,
              and deploy — all from one conversation.
            </p>
            <div className="mt-10 flex flex-wrap gap-4">
              <button
                onClick={onStart}
                className="group inline-flex items-center gap-2 px-7 py-3.5 bg-teal-700 hover:bg-teal-800 text-white font-semibold rounded-lg transition-all text-base"
              >
                Get Started
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
              </button>
              {onAbout && (
                <button
                  onClick={onAbout}
                  className="px-7 py-3.5 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold rounded-lg transition-colors text-base"
                >
                  Learn More
                </button>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── What You Can Do ── */}
      <section className="bg-gray-50 border-t border-gray-200">
        <div className="max-w-6xl mx-auto px-6 py-20">
          <h2 className="text-2xl font-bold text-gray-900 mb-10">What you can do</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {[
              {
                icon: Package,
                title: 'Generate Bundles',
                desc: 'Upload an SRS Excel sheet and get a complete Avni bundle — concepts, forms, mappings, and visit schedules.',
              },
              {
                icon: MessageSquare,
                title: 'Chat with AI',
                desc: 'Ask questions about Avni configuration in plain English. Answers grounded in real implementation data.',
              },
              {
                icon: BookOpen,
                title: 'Write Rules',
                desc: 'Describe skip logic, visit schedules, or validations in English — get production-ready JavaScript rules.',
              },
              {
                icon: Shield,
                title: 'Validate Before Deploy',
                desc: '100+ automated checks catch errors before they reach avni-server. Fix issues in conversation.',
              },
              {
                icon: Zap,
                title: 'Multiple AI Providers',
                desc: 'OpenAI, Groq, Gemini, Ollama — use whichever fits your budget. Automatic failover between providers.',
              },
              {
                icon: Globe,
                title: 'India-Ready',
                desc: 'Aadhaar/PAN detection, Hindi support, PCPNDT compliance, gender-neutral language — built for Indian NGOs.',
              },
            ].map(({ icon: Icon, title, desc }) => (
              <div
                key={title}
                className="p-6 bg-white rounded-xl border border-gray-200 hover:border-gray-300 transition-colors"
              >
                <div className="w-10 h-10 rounded-lg bg-teal-50 flex items-center justify-center mb-4">
                  <Icon className="w-5 h-5 text-teal-700" />
                </div>
                <h3 className="text-base font-semibold text-gray-900 mb-2">{title}</h3>
                <p className="text-sm text-gray-600 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-gray-200 bg-white">
        <div className="max-w-6xl mx-auto px-6 py-8">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <AvniLogo size={24} variant="icon" />
                <span className="font-semibold text-gray-900">Avni hai T<span className="text-teal-700">AI</span>yaar</span>
              </div>
              <p className="text-sm text-gray-500">AI-powered implementation platform for Avni</p>
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
              <a href="https://avniproject.org" target="_blank" rel="noopener noreferrer" className="text-gray-500 hover:text-teal-700 transition-colors">Avni Project</a>
              <a href="https://avni.readme.io" target="_blank" rel="noopener noreferrer" className="text-gray-500 hover:text-teal-700 transition-colors">Documentation</a>
              <a href="https://github.com/avniproject" target="_blank" rel="noopener noreferrer" className="text-gray-500 hover:text-teal-700 transition-colors">GitHub</a>
              {onAbout && (
                <button onClick={onAbout} className="text-gray-500 hover:text-teal-700 transition-colors">About</button>
              )}
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
