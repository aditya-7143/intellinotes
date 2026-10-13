import { ReactNode } from 'react';
import Link from 'next/link';
import { BookOpen, Sparkles, Check, ArrowUpRight } from 'lucide-react';

export function AuthLayout({ children }: { children: ReactNode }) {
  return <div className="grid min-h-screen bg-[#f7f8f4] lg:grid-cols-2">
    <aside className="relative hidden flex-col overflow-hidden bg-[#19392c] p-12 text-white lg:flex xl:p-16">
      <Link href="/" className="flex items-center gap-3 text-xl font-semibold tracking-tight"><BookOpen className="h-6 w-6 text-[#b6d6a4]" />IntelliNotes<span className="-ml-3 text-[#b6d6a4]">.</span></Link>
      <div className="my-auto py-14"><span className="text-xs font-medium uppercase tracking-[0.2em] text-[#b6d6a4]">Less noise. More clarity.</span><h1 className="mt-6 max-w-md font-editorial text-5xl leading-[1.12] xl:text-6xl">Good ideas deserve<br />a good home.</h1><p className="mt-6 max-w-sm text-sm leading-7 text-white/60">Capture the thought. Connect the dots. A quieter workspace for everything you want to remember.</p>
      <div aria-hidden="true" className="notebook-paper relative mt-10 max-w-sm -rotate-3 rounded-2xl p-7 text-[#19392c] shadow-xl"><div className="mb-6 flex items-center justify-between"><span className="font-editorial text-2xl">From scattered to structured</span><ArrowUpRight className="h-5 w-5" /></div><div className="space-y-5 text-sm"><p className="flex items-center gap-3"><Check className="h-4 w-4 text-primary-600" />Collect your ideas</p><p className="flex items-center gap-3"><Check className="h-4 w-4 text-primary-600" />Find the connections</p><p className="flex items-center gap-3"><Check className="h-4 w-4 text-primary-600" />Make space for what&apos;s next</p></div><div className="mt-6 inline-flex items-center gap-2 rounded-full bg-primary-100 px-3 py-1.5 text-xs text-primary-700"><Sparkles className="h-3.5 w-3.5" />A little help from AI</div></div></div>
      <p className="text-xs text-white/40">Your notes. Your structure. Your way.</p>
    </aside>
    <main className="flex flex-col items-center justify-center px-5 py-12 sm:px-10"><Link href="/" className="mb-10 flex items-center gap-2 text-xl font-semibold text-primary-900 lg:hidden"><BookOpen className="h-6 w-6" />IntelliNotes.</Link>{children}<p className="mt-8 text-center text-xs text-gray-400">A little space for your next big idea.</p></main>
  </div>;
}
