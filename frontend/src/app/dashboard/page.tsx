'use client';

import { useEffect, useState } from 'react';
import { useAuthStore } from '@/features/auth/authStore';
import { noteApi, folderApi, structuringApi } from '@/lib/api';
import { Note } from '@/types';
import Link from 'next/link';
import { FileText, FolderOpen, Sparkles, ArrowRight, Plus, ArrowUpRight, BookOpen, RefreshCw } from 'lucide-react';
import { format } from 'date-fns';

export default function DashboardPage() {
  const { user } = useAuthStore();
  const [notes, setNotes] = useState<Note[]>([]);
  const [counts, setCounts] = useState({ notes: 0, folders: 0, proposals: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const load = async () => {
    setLoading(true);
    setError(false);
    try {
      const [n, f, p] = await Promise.all([noteApi.list(), folderApi.list(), structuringApi.list()]);
      setNotes([...n.data].sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()).slice(0, 4));
      setCounts({ notes: n.data.length, folders: f.data.length, proposals: p.data.filter(item => item.status === 'pending').length });
    } catch { setError(true); } finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  const stats = [
    { label: 'Total notes', value: counts.notes, icon: FileText, href: '/dashboard/library', detail: 'Your growing collection', color: 'bg-[#edf2e8] text-primary-700' },
    { label: 'Folders', value: counts.folders, icon: FolderOpen, href: '/dashboard/library', detail: 'Everything in its place', color: 'bg-[#fbf0db] text-amber-700' },
    { label: 'Pending proposals', value: counts.proposals, icon: Sparkles, href: '/dashboard/library/organize?review=true', detail: 'Ready for your review', color: 'bg-[#eeeafa] text-violet-600' },
  ];
  return <div className="space-y-8">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-primary-600">A space for your thoughts</p><h1 className="font-editorial text-4xl text-[#19392c] sm:text-5xl">Welcome back, {user?.full_name?.split(' ')[0] || 'there'}.</h1><p className="mt-3 text-sm text-gray-500">Pick up where you left off, or start with a fresh idea.</p></div>
      <Link href="/dashboard/library/organize" className="btn-primary gap-2"><Plus className="h-4 w-4" />Add to library</Link>
    </div>
    {error && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">We couldn&apos;t load your workspace. Please try again.<button onClick={load} className="flex items-center gap-2 font-semibold"><RefreshCw className="h-4 w-4" />Retry</button></div>}
    <div className="grid gap-4 sm:grid-cols-3">{stats.map(({ label, value, icon: Icon, href, detail, color }) => <Link key={label} href={href} className="group rounded-2xl border border-gray-200/80 bg-white p-5 transition-all hover:-translate-y-0.5 hover:border-primary-200 hover:shadow-md"><div className="flex items-center justify-between"><span className={`flex h-10 w-10 items-center justify-center rounded-xl ${color}`}><Icon className="h-5 w-5" /></span><ArrowUpRight className="h-4 w-4 text-gray-300 group-hover:text-primary-600" /></div><div className="mt-5 flex items-baseline gap-3"><span className="text-3xl font-semibold tracking-tight text-[#19392c]">{loading ? '…' : error ? '—' : value}</span><span className="text-sm text-gray-600">{label}</span></div><p className="mt-2 text-xs text-gray-400">{detail}</p></Link>)}</div>
    <section className="relative overflow-hidden rounded-2xl border border-[#dce5cf] bg-[#eaf0de] p-7 sm:p-9">
      <div className="relative z-10 max-w-lg"><span className="inline-flex items-center gap-2 rounded-full border border-primary-600/15 bg-white/50 px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-primary-700"><Sparkles className="h-3 w-3" />Your thinking, organized</span><h2 className="mt-5 font-editorial text-3xl text-[#19392c] sm:text-4xl">Big ideas. Less clutter.</h2><p className="mt-3 max-w-sm text-sm leading-6 text-primary-800/70">Drop in your rough notes, code snippets, or a stream of thoughts. Let AI find the structure, then make it yours.</p><Link href="/dashboard/library/organize" className="btn-primary mt-6 gap-3">Add to library<ArrowRight className="h-4 w-4" /></Link></div>
      <div aria-hidden="true" className="notebook-paper absolute -right-8 top-14 hidden h-60 w-64 rotate-12 rounded-xl border border-primary-900/10 p-7 shadow-lg xl:block"><div className="mb-7 flex items-center gap-2 text-primary-700"><BookOpen className="h-5 w-5" /><span className="font-editorial text-xl">A clearer picture</span></div><div className="space-y-5"><div className="h-2 w-4/5 rounded bg-primary-200" /><div className="h-2 w-full rounded bg-primary-100" /><div className="h-2 w-2/3 rounded bg-primary-100" /></div><span className="mt-7 inline-flex items-center gap-2 rounded-lg bg-primary-100 px-3 py-2 text-xs text-primary-700"><Sparkles className="h-3 w-3" />Ideas, connected</span></div>
    </section>
    <section><div className="mb-5 flex items-center justify-between"><h2 className="text-lg font-semibold text-[#19392c]">Recently updated</h2><Link href="/dashboard/library" className="flex items-center gap-2 text-xs font-medium text-primary-700">View all notes<ArrowRight className="h-3.5 w-3.5" /></Link></div>
      {loading ? <div className="grid gap-4 sm:grid-cols-2">{[1,2].map(i => <div key={i} className="h-40 animate-pulse rounded-2xl bg-gray-200/60" />)}</div> : error ? <p className="rounded-2xl border border-gray-200 bg-white p-6 text-sm text-gray-500">Your recent notes will appear here when your workspace is available.</p> : notes.length ? <div className="grid gap-4 sm:grid-cols-2">{notes.map(note => <Link key={note.id} href={`/dashboard/library?edit=${note.id}`} className="group rounded-2xl border border-gray-200/80 bg-white p-5 transition-colors hover:border-primary-300"><div className="flex items-start gap-3"><FileText className="mt-1 h-4 w-4 shrink-0 text-primary-500" /><h3 className="truncate font-medium text-gray-800">{note.title}</h3><ArrowUpRight className="ml-auto h-4 w-4 shrink-0 text-gray-300" /></div><p className="mt-3 line-clamp-2 text-sm leading-6 text-gray-500">{note.content}</p><div className="mt-5 flex items-center justify-between gap-3 text-xs text-gray-400"><span className="truncate">{note.folder_path === '/' ? 'Unfiled' : note.folder_path}</span><span className="shrink-0">{format(new Date(note.updated_at), 'MMM d, yyyy')}</span></div></Link>)}</div> : <div className="flex flex-col items-center rounded-2xl border border-dashed border-gray-300 bg-white/50 px-6 py-10 text-center"><span className="mb-4 rounded-2xl bg-[#edf2e8] p-4"><FileText className="h-6 w-6 text-primary-600" /></span><h3 className="font-medium text-gray-800">Your next idea belongs here.</h3><p className="mt-2 text-sm text-gray-500">Create your first note and start building your collection.</p><Link href="/dashboard/library/organize" className="mt-5 flex items-center gap-2 text-sm font-semibold text-primary-700"><Plus className="h-4 w-4" />Add to library</Link></div>}
    </section>
  </div>;
}
