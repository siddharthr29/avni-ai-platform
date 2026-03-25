import { useState, useEffect, useRef } from 'react';
import {
  ArrowLeft, ChevronDown, ChevronRight,
  Server, Shield, Layers, Zap, Globe, Lock,
  FileText, Code, Users, BarChart3,
  CheckCircle2, AlertTriangle, TrendingUp, Clock, Target, Workflow,
} from 'lucide-react';
import { AvniLogo } from './AvniLogo';

interface AboutPageProps {
  onClose: () => void;
}

function useScrollReveal() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add('about-visible');
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.08 }
    );
    const targets = el.querySelectorAll('.about-reveal');
    targets.forEach((child) => observer.observe(child));
    return () => observer.disconnect();
  }, []);
  return ref;
}

const SECTIONS = [
  'The Story',
  'The Problem',
  'Our Analysis',
  'The Approach',
  'Tech Stack',
  'Architecture',
  'AI Guardrails',
  'Avni Compatibility',
  'Security & Scale',
  'Use Cases',
  'Expected Impact',
];

export function AboutPage({ onClose }: AboutPageProps) {
  const contentRef = useScrollReveal();
  const [activeSection, setActiveSection] = useState(0);
  const sectionRefs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const idx = sectionRefs.current.indexOf(entry.target as HTMLElement);
            if (idx >= 0) setActiveSection(idx);
          }
        }
      },
      { threshold: 0.3 }
    );
    sectionRefs.current.forEach((el) => el && observer.observe(el));
    return () => observer.disconnect();
  }, []);

  const scrollTo = (idx: number) => {
    sectionRefs.current[idx]?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="h-full flex flex-col bg-gray-900">
      {/* ── Sticky header ── */}
      <header className="h-14 border-b border-white/10 bg-gray-900/95 backdrop-blur-md flex items-center px-5 shrink-0 z-30 sticky top-0">
        <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/10 transition-colors mr-3">
          <ArrowLeft className="w-5 h-5 text-gray-300" />
        </button>
        <AvniLogo size={24} variant="icon" />
        <span className="ml-2 font-semibold text-white">Avni hai T<span className="text-emerald-400">AI</span>yaar</span>
        <div className="ml-auto hidden lg:flex items-center gap-1">
          {SECTIONS.map((s, i) => (
            <button
              key={s}
              onClick={() => scrollTo(i)}
              className={`px-2 py-1 text-xs rounded-md transition-colors ${
                activeSection === i ? 'bg-white/20 text-white font-medium' : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {i + 1}
            </button>
          ))}
        </div>
        <span className="ml-3 text-xs text-gray-400 hidden md:inline">
          {activeSection + 1}/{SECTIONS.length} — {SECTIONS[activeSection]}
        </span>
      </header>

      {/* ── Scrollable slides ── */}
      <div ref={contentRef} className="flex-1 overflow-y-auto scroll-smooth">

        {/* ─── SLIDE 1: The Story ─── */}
        <section
          ref={el => { sectionRefs.current[0] = el; }}
          className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-900 via-gray-800 to-primary-900 text-white px-6 py-24"
        >
          <div className="max-w-3xl mx-auto text-center about-reveal">
            <div className="mb-8 flex justify-center">
              <AvniLogo size={56} variant="icon" />
            </div>
            <h1 className="text-5xl sm:text-6xl font-bold mb-6 leading-tight tracking-tight">
              <span className="text-emerald-400">Avni</span>{' '}hai{' '}T<span className="text-emerald-400">AI</span>yaar
            </h1>
            <p className="text-xl text-gray-300 mb-10 max-w-2xl mx-auto leading-relaxed">
              An AI-powered platform that helps NGOs configure and deploy{' '}
              <a href="https://avniproject.org" className="text-primary-400 underline" target="_blank" rel="noopener noreferrer">Avni</a>{' '}
              implementations — reducing weeks of manual work to hours of guided conversation.
            </p>
            <div className="flex flex-wrap justify-center gap-3 text-sm">
              {['Self-Hosted', 'No Cloud Dependency', '36,700+ Knowledge Chunks', '160+ API Endpoints'].map(tag => (
                <span key={tag} className="px-4 py-2 bg-white/10 text-gray-300 rounded-full">{tag}</span>
              ))}
            </div>
            <button onClick={() => scrollTo(1)} className="mt-14 animate-bounce">
              <ChevronDown className="w-8 h-8 text-gray-400" />
            </button>
          </div>
        </section>

        {/* ─── SLIDE 2: The Problem ─── */}
        <section
          ref={el => { sectionRefs.current[1] = el; }}
          className="min-h-screen flex items-center px-6 py-24 bg-white"
        >
          <div className="max-w-4xl mx-auto w-full">
            <div className="about-reveal mb-10">
              <span className="text-sm font-semibold text-red-500 uppercase tracking-widest">The Problem</span>
              <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mt-3 mb-4 leading-snug">
                Implementation takes too long and is cumbersome
              </h2>
              <p className="text-base text-gray-600 max-w-2xl leading-relaxed">
                Setting up Avni for a new organisation involves multiple manual steps, each requiring
                domain expertise that is scarce and expensive.
              </p>
            </div>

            <div className="grid md:grid-cols-2 gap-10">
              <div className="about-reveal">
                <h3 className="text-lg font-semibold text-gray-900 mb-5">Current Process</h3>
                <div className="space-y-3">
                  {[
                    { step: 'Requirement Gathering', time: 'Client calls, PDFs, Excel sheets', icon: FileText },
                    { step: 'Specification Mapping', time: '1.5–2 days per organisation', icon: Workflow },
                    { step: 'App Configuration', time: 'Requires Avni domain expert', icon: Code },
                    { step: 'Testing & Corrections', time: 'Back-and-forth iterations', icon: AlertTriangle },
                    { step: 'Go Live', time: 'Field training needed', icon: Users },
                  ].map(({ step, time, icon: Icon }) => (
                    <div key={step} className="flex items-start gap-4 p-4 bg-red-50 border border-red-100 rounded-lg">
                      <Icon className="w-5 h-5 text-red-400 mt-0.5 shrink-0" />
                      <div>
                        <p className="text-sm font-semibold text-gray-900">{step}</p>
                        <p className="text-sm text-gray-600 mt-0.5">{time}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="about-reveal">
                <h3 className="text-lg font-semibold text-gray-900 mb-5">Key Pain Points</h3>
                <div className="space-y-4">
                  {[
                    { title: 'Lengthy scoping process', desc: 'Gathering requirements through calls, PDFs, and Excel sheets takes days before work begins.' },
                    { title: 'Skilled resource dependency', desc: 'Mapping requirements to Avni\'s data model requires deep domain expertise — a scarce resource.' },
                    { title: 'Repetitive manual configuration', desc: 'Creating forms, concepts, encounter types, and mappings is tedious repetitive work.' },
                    { title: 'Rule writing is complex', desc: 'Skip logic, visit scheduling, and validation rules require JavaScript expertise on top of Avni knowledge.' },
                    { title: 'High cost limits reach', desc: 'The implementation effort means smaller NGOs can\'t afford to adopt Avni.' },
                  ].map(({ title, desc }) => (
                    <div key={title} className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
                      <p className="text-sm font-semibold text-gray-900">{title}</p>
                      <p className="text-sm text-gray-600 mt-1 leading-relaxed">{desc}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── SLIDE 3: Analysis ─── */}
        <section
          ref={el => { sectionRefs.current[2] = el; }}
          className="min-h-screen flex items-center px-6 py-24 bg-gray-50"
        >
          <div className="max-w-4xl mx-auto w-full">
            <div className="about-reveal mb-10">
              <span className="text-sm font-semibold text-amber-600 uppercase tracking-widest">Our Analysis</span>
              <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mt-3 mb-4 leading-snug">
                Where AI adds value vs. where it doesn't
              </h2>
              <p className="text-base text-gray-600 max-w-2xl leading-relaxed mb-5">
                Not everything needs an LLM. We separated deterministic work from AI-driven work to maximise reliability.
              </p>
              <div className="bg-amber-50 border border-amber-200 rounded-lg px-5 py-3 max-w-2xl">
                <p className="text-sm text-gray-700 leading-relaxed">
                  <span className="font-semibold text-amber-800">What does "deterministic" mean?</span>{' '}
                  The system follows fixed, predictable rules — like a calculator. Same input always produces the exact same output. No AI guessing, 100% reliable.
                </p>
              </div>
            </div>

            <div className="overflow-x-auto about-reveal">
              <table className="w-full text-sm border border-gray-200 rounded-lg overflow-hidden">
                <thead>
                  <tr className="bg-gray-100">
                    <th className="text-left py-3 px-5 font-semibold text-gray-900">Step</th>
                    <th className="text-left py-3 px-5 font-semibold text-gray-900">Method</th>
                    <th className="text-left py-3 px-5 font-semibold text-gray-900 hidden sm:table-cell">Rationale</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {[
                    ['Intent classification', 'AI (LLM)', 'Natural language understanding needed for routing'],
                    ['SRS Excel parsing', 'Deterministic', 'Fixed column semantics (A–Q), rule-based parser'],
                    ['Field property inference', 'AI (LLM)', 'Domain reasoning: "Number of children" → no negative'],
                    ['Bundle JSON generation', 'Deterministic', 'Exact schemas required; template engine with stable UUIDs'],
                    ['Validation & gap detection', 'Deterministic', 'Known rules for complete bundles'],
                    ['Skip logic / rules', 'Hybrid', 'Simple: templates. Complex: AI'],
                    ['Unstructured → structured spec', 'AI (LLM)', 'Interpreting PDFs, call notes into Avni data model'],
                    ['Conversational corrections', 'AI (LLM)', 'NL understanding to update bundle assets'],
                    ['RAG knowledge retrieval', 'Hybrid', 'Semantic search + BM25 keyword + RRF fusion'],
                  ].map(([step, method, rationale]) => (
                    <tr key={step} className="hover:bg-white transition-colors">
                      <td className="py-3 px-5 font-medium text-gray-900">{step}</td>
                      <td className="py-3 px-5">
                        <span className={`inline-block px-3 py-1 rounded-md text-xs font-medium ${
                          method === 'AI (LLM)' ? 'bg-blue-100 text-blue-700' :
                          method === 'Deterministic' ? 'bg-green-100 text-green-700' :
                          'bg-amber-100 text-amber-700'
                        }`}>
                          {method}
                        </span>
                      </td>
                      <td className="py-3 px-5 text-gray-600 hidden sm:table-cell">{rationale}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* ─── SLIDE 4: Approach ─── */}
        <section
          ref={el => { sectionRefs.current[3] = el; }}
          className="min-h-screen flex items-center px-6 py-24 bg-white"
        >
          <div className="max-w-4xl mx-auto w-full">
            <div className="about-reveal mb-10">
              <span className="text-sm font-semibold text-primary-600 uppercase tracking-widest">The Approach</span>
              <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mt-3 leading-snug">
                Six design principles
              </h2>
            </div>

            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {[
                { icon: Server, title: 'Self-Hosted First', desc: 'Ollama for LLM, sentence-transformers for embeddings, pgvector for RAG. Zero API keys required. Data never leaves the server.' },
                { icon: Layers, title: 'Zero-LLM Critical Path', desc: 'Bundle generation is purely template-based. SRS parsing is rule-based. LLM failure means less polish, not broken output.' },
                { icon: Zap, title: 'Graceful Degradation', desc: '5 LLM providers with circuit breaker failover. RAG falls back to keyword search. Rate limiter falls back to in-memory.' },
                { icon: Shield, title: '8-Layer AI Guardrails', desc: 'Text normalisation → PII encryption → injection detection → ban lists → output guard → gender bias check → audit → domain validation.' },
                { icon: Globe, title: 'India-Specific Design', desc: 'Aadhaar/PAN/Voter ID detection. Hindi + 9 Indian scripts. PCPNDT Act compliance. Gender-neutral language.' },
                { icon: Lock, title: 'Multi-Tenant RBAC', desc: '4 hierarchical roles, 26 permissions, org-level isolation, JWT auth, resource ownership enforcement.' },
              ].map(({ icon: Icon, title, desc }) => (
                <div key={title} className="about-reveal p-6 bg-gray-50 border border-gray-200 rounded-xl hover:shadow-md transition-shadow">
                  <Icon className="w-8 h-8 text-primary-600 mb-4" />
                  <h3 className="text-base font-semibold text-gray-900 mb-2">{title}</h3>
                  <p className="text-sm text-gray-600 leading-relaxed">{desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── SLIDE 5: Tech Stack ─── */}
        <section
          ref={el => { sectionRefs.current[4] = el; }}
          className="min-h-screen flex items-center px-6 py-24 bg-gray-900 text-white"
        >
          <div className="max-w-5xl mx-auto w-full">
            <div className="about-reveal mb-10">
              <span className="text-sm font-semibold text-emerald-400 uppercase tracking-widest">Tech Stack</span>
              <h2 className="text-3xl sm:text-4xl font-bold mt-3 mb-3 leading-snug">Every choice has a reason</h2>
              <p className="text-base text-gray-400 max-w-2xl leading-relaxed">
                Built for NGOs deploying in low-connectivity environments with strict data sovereignty requirements.
              </p>
            </div>

            <div className="grid md:grid-cols-2 gap-5">
              {[
                { layer: 'Backend', tech: 'Python 3.14 + FastAPI', why: 'Async-first, auto-generated OpenAPI docs, Pydantic validation. Same ecosystem as ML/AI libraries.', how: '24 router modules, 160+ endpoints, middleware stack (auth → RBAC → rate limit → metrics).' },
                { layer: 'Frontend', tech: 'React 19 + Vite + Tailwind CSS v4', why: 'React 19 for concurrent features, Vite for sub-second HMR, Tailwind for consistent design.', how: '47 components, lazy-loaded views, SSE streaming for real-time chat.' },
                { layer: 'Database', tech: 'PostgreSQL 16 + pgvector', why: 'Vector similarity search without a separate vector DB. One database for everything.', how: 'HNSW indexes for cosine similarity, GIN indexes for BM25, 18 tables, 8 migrations.' },
                { layer: 'LLM Inference', tech: 'Multi-provider (OpenAI, Groq, Ollama)', why: 'Runs on cloud or locally. 5 providers with per-provider circuit breaker and automatic failover.', how: 'Task-aware routing: OpenAI for rules, Groq for chat (speed), Ollama for validation (free).' },
                { layer: 'Embeddings', tech: 'sentence-transformers (MiniLM-L6-v2)', why: 'Runs in-process, 384 dimensions, fast. No API call per embedding — works offline.', how: 'Loaded once at startup. Encodes queries and docs into same vector space.' },
                { layer: 'RAG Search', tech: 'Hybrid: Semantic + BM25 + RRF', why: 'Semantic alone misses Avni terminology. BM25 alone misses rephrased queries. RRF combines both.', how: '36,700+ chunks across 14 collections. 4-layer retrieval: vector → BM25 → RRF → dedup.' },
                { layer: 'Auth', tech: 'JWT + bcrypt + Fernet encryption', why: 'Stateless JWT for scaling, bcrypt for passwords, Fernet for BYOK key encryption at rest.', how: 'Access tokens (24h) + refresh tokens (30d, rotated). 4-role RBAC with 26 permissions.' },
                { layer: 'Infrastructure', tech: 'Docker Compose + nginx', why: 'Single docker-compose deploys all services. nginx handles SSL. Prometheus + Grafana for observability.', how: 'Health checks, resource limits, automated PostgreSQL backups.' },
              ].map(({ layer, tech, why, how }) => (
                <div key={layer} className="about-reveal p-5 bg-white/5 border border-white/10 rounded-xl">
                  <span className="text-xs font-mono text-emerald-400 bg-emerald-400/10 px-2.5 py-1 rounded-md">{layer}</span>
                  <h3 className="text-base font-semibold text-white mt-3 mb-3">{tech}</h3>
                  <p className="text-sm text-gray-300 leading-relaxed mb-2">
                    <span className="text-amber-400 font-medium">Why: </span>{why}
                  </p>
                  <p className="text-sm text-gray-300 leading-relaxed">
                    <span className="text-blue-400 font-medium">How: </span>{how}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── SLIDE 6: Architecture ─── */}
        <section
          ref={el => { sectionRefs.current[5] = el; }}
          className="min-h-screen flex items-center px-6 py-24 bg-white"
        >
          <div className="max-w-4xl mx-auto w-full">
            <div className="about-reveal mb-10">
              <span className="text-sm font-semibold text-purple-600 uppercase tracking-widest">Architecture</span>
              <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mt-3 leading-snug">
                Request lifecycle
              </h2>
              <p className="text-base text-gray-600 mt-3 max-w-2xl leading-relaxed">
                From the moment you type a message to when you see the response — here is what happens.
              </p>
            </div>

            <div className="about-reveal space-y-5">
              {[
                { num: '1', label: 'User Message', desc: 'You type a message. The app opens a live SSE connection so you see the response word-by-word.', color: 'bg-blue-600' },
                { num: '2', label: 'Safety Checks', desc: 'The system verifies identity, checks permissions, rate-limits the request, and hides sensitive data like Aadhaar numbers.', color: 'bg-amber-500' },
                { num: '3', label: 'Intent Classification', desc: 'The system determines what you want — chat, create bundle, write rule, ask for support, upload voice/image.', color: 'bg-purple-600' },
                { num: '4', label: 'Knowledge Retrieval', desc: 'Your question is searched by meaning (semantic) and by keywords (BM25). Results are merged and ranked from 36,000+ chunks.', color: 'bg-emerald-600' },
                { num: '5', label: 'Context Assembly', desc: 'Six layers: organisation details, retrieved knowledge, task instructions, detected actions, clarification questions, safety rules.', color: 'bg-red-500' },
                { num: '6', label: 'AI Response', desc: 'The AI model generates a response. If the primary provider is down, it switches to a backup — up to 5 fallback providers.', color: 'bg-indigo-600' },
                { num: '7', label: 'Output Safety', desc: 'Response is checked for leaked instructions, harmful scripts, low-confidence answers, gender-biased language, and sensitive data.', color: 'bg-pink-600' },
                { num: '8', label: 'Streaming', desc: 'The response streams to your screen word-by-word. Safety warnings appear as notifications. Conversation is saved automatically.', color: 'bg-teal-600' },
              ].map(({ num, label, desc, color }) => (
                <div key={num} className="flex items-start gap-5">
                  <div className={`${color} w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm shrink-0`}>
                    {num}
                  </div>
                  <div className="flex-1 pb-5 border-b border-gray-100 last:border-b-0">
                    <p className="text-base font-semibold text-gray-900 mb-1">{label}</p>
                    <p className="text-sm text-gray-600 leading-relaxed">{desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── SLIDE 7: AI Guardrails ─── */}
        <section
          ref={el => { sectionRefs.current[6] = el; }}
          className="min-h-screen flex items-center px-6 py-24 bg-red-50"
        >
          <div className="max-w-4xl mx-auto w-full">
            <div className="about-reveal mb-10">
              <span className="text-sm font-semibold text-red-600 uppercase tracking-widest">Responsible AI</span>
              <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mt-3 mb-3 leading-snug">
                8-Layer AI Guardrails
              </h2>
              <p className="text-base text-gray-600 max-w-2xl leading-relaxed">
                Built for Indian NGOs handling sensitive beneficiary data — Aadhaar numbers, health records, tribal community information.
              </p>
            </div>

            <div className="grid sm:grid-cols-2 gap-5 about-reveal">
              {[
                { layer: 'Text Cleanup', desc: 'Removes hidden characters, unusual symbols, and tricks that could confuse the AI.', action: 'Pre-process' },
                { layer: 'Sensitive Data Protection', desc: 'Detects and hides Aadhaar, PAN, phone numbers, emails — the AI never sees them.', action: 'Hide' },
                { layer: 'Manipulation Blocker', desc: 'Stops attempts to trick the AI into ignoring rules or revealing internal instructions.', action: 'Block' },
                { layer: 'Custom Banned Words', desc: 'Per-organisation banned terms. E.g., "sonography" blocked for PCPNDT Act compliance.', action: 'Rephrase' },
                { layer: 'Response Safety Check', desc: 'Cleans leaked system instructions, harmful code. Uncertain answers get a disclaimer.', action: 'Clean' },
                { layer: 'Gender-Neutral Language', desc: 'Replaces biased terms — "manpower" → "workforce" across health and education contexts.', action: 'Fix' },
                { layer: 'Ethical AI Guidelines', desc: 'Never design discriminatory systems, always admit uncertainty, respect privacy.', action: 'Guide' },
                { layer: 'Complete Activity Log', desc: 'Every safety action logged — blocked, redacted, changed. Admins can review for compliance.', action: 'Monitor' },
              ].map(({ layer, desc, action }) => (
                <div key={layer} className="p-5 bg-white border border-red-100 rounded-xl">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-gray-900">{layer}</h3>
                    <span className="text-xs px-2.5 py-1 bg-red-100 text-red-700 rounded-full font-medium">{action}</span>
                  </div>
                  <p className="text-sm text-gray-600 leading-relaxed">{desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── SLIDE 8: Avni Compatibility ─── */}
        <section
          ref={el => { sectionRefs.current[7] = el; }}
          className="min-h-screen flex items-center px-6 py-24 bg-white"
        >
          <div className="max-w-4xl mx-auto w-full">
            <div className="about-reveal mb-10">
              <span className="text-sm font-semibold text-emerald-600 uppercase tracking-widest">Avni Compatibility</span>
              <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mt-3 leading-snug">
                Deep integration with the Avni ecosystem
              </h2>
            </div>

            <div className="grid md:grid-cols-2 gap-10">
              <div className="about-reveal">
                <h3 className="text-lg font-semibold text-gray-900 mb-5">Bundle Pipeline</h3>
                <div className="space-y-4">
                  {[
                    { step: 'SRS Input', desc: 'Excel (columns A–Q), PDF, plain text, or chat conversation' },
                    { step: 'Parse & Validate', desc: 'Rule-based parser extracts entities, fields, options, conditions' },
                    { step: 'LLM Enrichment', desc: '60+ field rules: allowNegative, allowDecimal, units' },
                    { step: 'Template Generation', desc: 'Deterministic UUID registry for idempotent re-uploads' },
                    { step: 'Auto-generated Forms', desc: 'Cancellation forms for encounters, exit forms for enrolments' },
                    { step: 'Bundle Validation', desc: '100+ checks: data types, form types, displayOrder, UUIDs' },
                    { step: 'Diff & Upload', desc: 'Compare against live org, then upload to avni-server' },
                  ].map(({ step, desc }, i) => (
                    <div key={step} className="flex items-start gap-4">
                      <div className="w-7 h-7 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">
                        {i + 1}
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-gray-900">{step}</p>
                        <p className="text-sm text-gray-600 mt-0.5">{desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="about-reveal">
                <h3 className="text-lg font-semibold text-gray-900 mb-5">Knowledge Corpus</h3>
                <div className="bg-gray-50 rounded-xl border border-gray-200 overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-100">
                        <th className="text-left py-3 px-4 font-medium text-gray-700">Collection</th>
                        <th className="text-right py-3 px-4 font-medium text-gray-700">Chunks</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {[
                        ['17 org bundles', '20,296'],
                        ['Concept definitions', '4,949'],
                        ['66 SRS Excel files', '4,386'],
                        ['108 skill documents', '3,210'],
                        ['avni-etl codebase', '1,604'],
                        ['avni-server codebase', '1,315'],
                        ['avni-webapp + client', '467'],
                        ['Forms + Rules + Support', '421'],
                        ['How-To Guides', '73'],
                      ].map(([source, count]) => (
                        <tr key={source}>
                          <td className="py-2.5 px-4 text-gray-700">{source}</td>
                          <td className="py-2.5 px-4 text-right font-mono text-gray-600">{count}</td>
                        </tr>
                      ))}
                      <tr className="bg-emerald-50 font-semibold">
                        <td className="py-2.5 px-4 text-emerald-700">Total</td>
                        <td className="py-2.5 px-4 text-right font-mono text-emerald-700">36,721</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <h3 className="text-lg font-semibold text-gray-900 mt-8 mb-3">MCP Integration</h3>
                <p className="text-sm text-gray-600 leading-relaxed">
                  20 CRUD tools via the Avni MCP Server for real-time entity management:
                  create/update/delete location types, locations, catchments, subject types,
                  programs, encounter types, and users.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ─── SLIDE 9: Security & Scale ─── */}
        <section
          ref={el => { sectionRefs.current[8] = el; }}
          className="min-h-screen flex items-center px-6 py-24 bg-gray-50"
        >
          <div className="max-w-4xl mx-auto w-full">
            <div className="about-reveal mb-10">
              <span className="text-sm font-semibold text-indigo-600 uppercase tracking-widest">Security & Scalability</span>
              <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mt-3 leading-snug">
                Production-ready from day one
              </h2>
            </div>

            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5 about-reveal">
              {[
                { title: 'JWT Auth + Token Rotation', desc: 'Access tokens (24h) + refresh tokens (30d). Server-side revocation. Single-use rotation on refresh.' },
                { title: '4-Role RBAC', desc: 'ngo_user → implementor → org_admin → platform_admin. 26 permissions. Route-level enforcement.' },
                { title: 'Resource Ownership', desc: 'Every session, BYOK key, and profile verified against authenticated user. 403 on mismatch.' },
                { title: 'BYOK Key Encryption', desc: 'API keys encrypted at rest with Fernet (AES-128-CBC). Derived from JWT_SECRET via SHA-256.' },
                { title: 'Rate Limiting', desc: 'Sliding window (Redis or in-memory). Per-user/IP. Login-specific: 5 attempts per email per minute.' },
                { title: 'Circuit Breaker', desc: 'Per-provider failure tracking. 3 failures → open (60s). Automatic recovery. 5-provider fallback.' },
                { title: 'Admin Panel', desc: 'User CRUD, role assignment, invite flow, org stats. First-user bootstrap. Soft-delete only.' },
                { title: 'Audit Trail', desc: 'Every admin action, guardrail trigger, bundle operation logged. Append-only. Compliance-ready.' },
                { title: 'Docker Compose', desc: 'All services with health checks, resource limits, nginx SSL, Prometheus + Grafana, automated backups.' },
              ].map(({ title, desc }) => (
                <div key={title} className="p-5 bg-white border border-gray-200 rounded-xl">
                  <h3 className="text-sm font-semibold text-gray-900 mb-2">{title}</h3>
                  <p className="text-sm text-gray-600 leading-relaxed">{desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── SLIDE 10: Use Cases ─── */}
        <section
          ref={el => { sectionRefs.current[9] = el; }}
          className="min-h-screen flex items-center px-6 py-24 bg-white"
        >
          <div className="max-w-4xl mx-auto w-full">
            <div className="about-reveal mb-10">
              <span className="text-sm font-semibold text-teal-600 uppercase tracking-widest">Use Cases</span>
              <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mt-3 leading-snug">
                Who uses it and how
              </h2>
            </div>

            <div className="grid md:grid-cols-2 gap-6 about-reveal">
              {[
                { persona: 'Implementor', role: 'Sets up Avni for new organisations', uses: [
                  'Upload a scoping sheet and get a ready-to-use configuration in minutes',
                  'Make changes by saying what you want — "rename this field" or "make this visit monthly"',
                  'Auto-generate rules like skip logic and visit schedules from plain English',
                  'Catch errors early — 100+ checks run automatically before anything goes live',
                ], color: 'border-blue-200 bg-blue-50' },
                { persona: 'Field Worker', role: 'Uses Avni daily in the field', uses: [
                  'Ask questions in plain language — "How do I register a new beneficiary?"',
                  'Get instant help when something goes wrong — "My app isn\'t syncing"',
                  'Speak observations aloud and the AI fills in the right form fields',
                  'Photograph a paper register and the AI extracts the data automatically',
                ], color: 'border-emerald-200 bg-emerald-50' },
                { persona: 'Organisation Admin', role: 'Manages their organisation\'s Avni setup', uses: [
                  'Invite team members, assign roles, and control access',
                  'Review changes before applying — see exactly what will be added or modified',
                  'Push new configurations to the live Avni server with one click',
                  'Track usage — who\'s using the AI, how much, and any safety flags',
                ], color: 'border-amber-200 bg-amber-50' },
                { persona: 'Platform Admin', role: 'Manages the entire AI platform', uses: [
                  'First person to sign up becomes the admin — no complex setup',
                  'Manage all users and organisations from one dashboard',
                  'Set content policies — block terms per organisation for compliance',
                  'Monitor system health — AI availability, usage limits, activity logs',
                ], color: 'border-purple-200 bg-purple-50' },
              ].map(({ persona, role, uses, color }) => (
                <div key={persona} className={`p-6 border rounded-xl ${color}`}>
                  <h3 className="text-base font-semibold text-gray-900">{persona}</h3>
                  <p className="text-sm text-gray-600 mb-4">{role}</p>
                  <ul className="space-y-2.5">
                    {uses.map((u, i) => (
                      <li key={i} className="flex items-start gap-2.5 text-sm text-gray-700 leading-relaxed">
                        <ChevronRight className="w-4 h-4 text-gray-400 mt-0.5 shrink-0" />
                        {u}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── SLIDE 11: Expected Impact ─── */}
        <section
          ref={el => { sectionRefs.current[10] = el; }}
          className="min-h-screen flex items-center px-6 py-24 bg-gradient-to-br from-primary-900 via-gray-900 to-emerald-900 text-white"
        >
          <div className="max-w-4xl mx-auto w-full">
            <div className="about-reveal text-center mb-14">
              <span className="text-sm font-semibold text-emerald-400 uppercase tracking-widest">Expected Impact</span>
              <h2 className="text-3xl sm:text-4xl font-bold mt-3 leading-snug">
                Where we expect to make a difference
              </h2>
            </div>

            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-14 about-reveal">
              {[
                { metric: '~1 day', label: 'Scoping sheet to spec', before: '2–4 days manually', icon: Clock, improvement: 'Significantly faster' },
                { metric: '~30%', label: 'Less configuration effort', before: 'Fully manual process', icon: TrendingUp, improvement: 'Partially automated' },
                { metric: 'Minutes', label: 'Bundle generation', before: 'Hours of manual work', icon: Zap, improvement: 'Near-instant' },
                { metric: '100+', label: 'Automated pre-checks', before: 'Manual review only', icon: CheckCircle2, improvement: 'Catches errors early' },
              ].map(({ metric, label, before, icon: Icon, improvement }) => (
                <div key={label} className="about-reveal text-center p-6 bg-white/5 border border-white/10 rounded-xl">
                  <Icon className="w-8 h-8 text-emerald-400 mx-auto mb-4" />
                  <p className="text-3xl font-bold text-white">{metric}</p>
                  <p className="text-sm text-gray-300 mt-2">{label}</p>
                  <div className="mt-4 pt-4 border-t border-white/10">
                    <p className="text-xs text-gray-400">Before: {before}</p>
                    <p className="text-xs text-emerald-400 font-medium mt-1">{improvement}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="grid sm:grid-cols-2 gap-6 about-reveal">
              <div className="p-6 bg-white/5 border border-white/10 rounded-xl">
                <Target className="w-6 h-6 text-amber-400 mb-4" />
                <h3 className="text-lg font-semibold mb-4">Reach</h3>
                <ul className="space-y-3 text-sm text-gray-300 leading-relaxed">
                  <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" /> Enable self-service for NGOs with smaller budgets</li>
                  <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" /> Reduce implementor dependency to "optional reviewer"</li>
                  <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" /> Support trial orgs with AI-generated specs</li>
                  <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" /> 24/7 AI assistant for field support</li>
                </ul>
              </div>
              <div className="p-6 bg-white/5 border border-white/10 rounded-xl">
                <BarChart3 className="w-6 h-6 text-blue-400 mb-4" />
                <h3 className="text-lg font-semibold mb-4">Quality</h3>
                <ul className="space-y-3 text-sm text-gray-300 leading-relaxed">
                  <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" /> 100+ validation checks before avni-server upload</li>
                  <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" /> Deterministic UUIDs for idempotent re-uploads</li>
                  <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" /> RAG grounded in 18 production implementations</li>
                  <li className="flex items-start gap-2.5"><CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" /> Feedback loop: corrections indexed into RAG</li>
                </ul>
              </div>
            </div>

            <div className="text-center mt-16 about-reveal">
              <button
                onClick={onClose}
                className="px-8 py-3.5 bg-white text-gray-900 font-semibold rounded-xl hover:bg-gray-100 transition-colors text-lg"
              >
                Start Using Avni AI
              </button>
              <div className="flex justify-center gap-6 mt-6 text-sm">
                <a href="https://avniproject.org" target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-white transition-colors">Avni Project</a>
                <a href="https://avni.readme.io" target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-white transition-colors">Docs</a>
                <a href="https://github.com/avniproject" target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-white transition-colors">GitHub</a>
              </div>
              <p className="text-sm text-gray-500 mt-4">Built with care for India's social sector</p>
            </div>
          </div>
        </section>
      </div>

      <style>{`
        .about-reveal {
          opacity: 0;
          transform: translateY(24px);
          transition: opacity 0.6s ease-out, transform 0.6s ease-out;
        }
        .about-visible .about-reveal,
        .about-visible.about-reveal {
          opacity: 1;
          transform: translateY(0);
        }
      `}</style>
    </div>
  );
}
