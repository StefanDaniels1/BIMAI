import Link from 'next/link';
import { StartPrompt } from '@/components/mdx/copy-prompt';

const audiences = [
  {
    title: 'I work in BIM',
    text: 'Modeller, BIM coordinator, design coordinator or information manager. Set up your team and do your first session in 15 minutes.',
    href: '/docs/start/install',
    cta: 'Get started',
  },
  {
    title: 'I decide on tools',
    text: 'BIM manager, project director or CEO. What bimai does, what it costs, how it keeps people in control, and how to run a pilot.',
    href: '/docs/why',
    cta: 'Why bimai',
  },
  {
    title: 'I build tools',
    text: 'Connect Revit, Civil 3D, OpenRoads, Bonsai or your own API. One contract, and your tool works with every BIM team.',
    href: '/docs/build',
    cta: 'Build on bimai',
  },
];

const features = [
  ['A team that fits your role', 'A short interview and your BEP decide which agents join your team. A modeller gets a different team than a design manager.'],
  ['Your BEP becomes the rules', 'Naming, tools and versions, responsibilities and milestones are read from the BIM execution plan, with page references.'],
  ['Meetings to tasks', 'Drop a Teams or Zoom transcript. Minutes, decisions and everyone’s tasks come out; anything unclear is asked first.'],
  ['People stay in control', 'Agents read by default. Every change to a model, ACC or a shared rule waits for a person to approve it.'],
  ['No git, no code', 'bimai saves, shares and restores your work in plain language. Git runs underneath; you never see it.'],
  ['Open source, open BIM', 'MIT licensed. Autodesk and Bentley today, IFC, IDS, BCF and OpenUSD as the long-term backbone.'],
];

export default function HomePage() {
  return (
    <main className="flex flex-1 flex-col">
      <section className="crt px-4 py-16 md:py-24">
        <div className="mx-auto flex max-w-5xl flex-col items-center gap-8 text-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.svg" alt="bimai — a BIM team at your command" className="w-full max-w-2xl" />
          <p className="max-w-2xl text-lg md:text-xl" style={{ textShadow: 'none', color: '#f5e6c8' }}>
            An open-source BIM team that lives in your editor. It coordinates, tracks requirements and risks,
            turns meetings into tasks and plans your week, and it asks before it changes anything.
          </p>
          <StartPrompt variant="hero" />
          <div className="flex flex-wrap justify-center gap-3" style={{ textShadow: 'none' }}>
            <Link href="/docs/start/install" className="rounded-md border border-[#ffb000] px-5 py-2.5 font-semibold text-[#ffb000]">
              Get started
            </Link>
            <Link href="/docs/example-project" className="rounded-md border border-[#ffb000] px-5 py-2.5 font-semibold text-[#ffb000]">
              See an example project
            </Link>
          </div>
          <p className="font-mono text-xs opacity-70">Pre-alpha: designed in the open, being built now.</p>
        </div>
      </section>

      <section className="mx-auto grid w-full max-w-5xl gap-4 px-4 py-12 md:grid-cols-3">
        {audiences.map((a) => (
          <Link key={a.title} href={a.href} className="group rounded-xl border bg-fd-card p-6 transition-colors hover:border-fd-primary">
            <h2 className="mb-2 text-lg font-semibold">{a.title}</h2>
            <p className="mb-4 text-sm text-fd-muted-foreground">{a.text}</p>
            <span className="font-mono text-sm font-semibold text-fd-primary">{a.cta} →</span>
          </Link>
        ))}
      </section>

      <section className="mx-auto w-full max-w-5xl px-4 pb-12">
        <h2 className="mb-6 text-2xl font-bold">What a session looks like</h2>
        <pre className="crt overflow-x-auto rounded-xl p-6 font-mono text-sm leading-relaxed">{`You: "Prepare Thursday's coordination meeting."

  🧭 Coordinator      workflow: weekly-coordination → 6 steps, 2 parallel lanes
  📋 Issue Manager    47 open ACC issues · 9 overdue · 3 clusters found
  🔍 Model Checker    delivery check on 3 models: 2 findings
  ✋ You              review the findings → approve
  ✍️  Scribe           agenda written · 4 open decisions · evidence cited

  Saved and shared with the team ✓`}</pre>
      </section>

      <section className="mx-auto grid w-full max-w-5xl gap-6 px-4 pb-20 md:grid-cols-3">
        {features.map(([title, text]) => (
          <div key={title}>
            <h3 className="mb-1 font-semibold">{title}</h3>
            <p className="text-sm text-fd-muted-foreground">{text}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
