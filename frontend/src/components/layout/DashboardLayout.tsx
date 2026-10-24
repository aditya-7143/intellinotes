'use client';

import { ReactNode, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuthStore } from '@/features/auth/authStore';
import { LayoutDashboard, Sparkles, LogOut, Menu, X, ArrowUpRight, BookOpen, ChevronRight } from 'lucide-react';
import { clsx } from 'clsx';

const navItems = [
  { href: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { href: '/dashboard/library', label: 'Library', icon: BookOpen },
];

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const { user, logout } = useAuthStore();
  return (
    <aside id="workspace-navigation" aria-label="Main navigation" className={clsx('fixed inset-y-0 left-0 z-50 flex w-64 flex-col bg-[#19392c] text-white transition-transform duration-200 lg:translate-x-0', open ? 'translate-x-0' : '-translate-x-full')}>
      <div className="flex h-24 items-center justify-between px-7">
        <Link href="/dashboard" onClick={onClose} className="flex items-center gap-3 text-xl font-semibold tracking-tight">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/10"><BookOpen className="h-5 w-5 text-[#b6d6a4]" /></span>
          IntelliNotes<span className="text-[#b6d6a4] -ml-3">.</span>
        </Link>
        <button onClick={onClose} aria-label="Close navigation" className="rounded-lg p-2 hover:bg-white/10 lg:hidden"><X className="h-5 w-5" /></button>
      </div>
      <nav className="flex-1 space-y-1.5 px-4 pt-5">
        <p className="mb-4 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-white/45">Your workspace</p>
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href !== '/dashboard' && pathname.startsWith(href + '/'));
          return <Link key={href} href={href} onClick={onClose} aria-current={active ? 'page' : undefined} className={clsx('flex items-center gap-3 rounded-xl px-3 py-3 text-sm transition-colors', active ? 'bg-[#dceacb] font-semibold text-[#19392c]' : 'text-white/65 hover:bg-white/10 hover:text-white')}><Icon className="h-[18px] w-[18px]" />{label}{active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary-600" />}</Link>;
        })}
      </nav>
      <div className="mx-4 mb-6 rounded-2xl border border-white/10 bg-white/5 p-4">
        <Sparkles className="mb-3 h-5 w-5 text-[#b6d6a4]" />
        <p className="text-sm font-medium">A little less chaos.</p>
        <p className="mt-2 text-xs leading-relaxed text-white/50">Turn scattered ideas into notes you can find again.</p>
        <Link href="/dashboard/library/organize" onClick={onClose} className="mt-4 flex items-center gap-2 text-xs font-medium text-[#dceacb]">Add to library <ArrowUpRight className="h-3.5 w-3.5" /></Link>
      </div>
      <div className="border-t border-white/10 p-5">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#dceacb] text-sm font-semibold text-primary-900">{user?.full_name?.charAt(0).toUpperCase() || 'U'}</span>
          <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{user?.full_name || 'My account'}</p><p className="mt-0.5 truncate text-xs text-white/45">{user?.email}</p></div>
          <button onClick={logout} aria-label="Sign out" title="Sign out" className="rounded-lg p-2 text-white/50 hover:bg-white/10 hover:text-white"><LogOut className="h-4 w-4" /></button>
        </div>
      </div>
    </aside>
  );
}

export function Header({ onMenuOpen, menuOpen }: { onMenuOpen: () => void; menuOpen: boolean }) {
  const pathname = usePathname();
  const current = navItems.find(item => item.href === pathname || (item.href !== '/dashboard' && pathname.startsWith(item.href + '/')))?.label || 'Workspace';
  return <header className="sticky top-0 z-30 flex h-20 items-center gap-4 border-b border-gray-200/70 bg-[#f7f8f4]/95 px-5 backdrop-blur-md lg:px-10">
    <button className="rounded-lg p-2 text-gray-600 hover:bg-gray-200 lg:hidden" onClick={onMenuOpen} aria-label="Open navigation" aria-expanded={menuOpen} aria-controls="workspace-navigation"><Menu className="h-5 w-5" /></button>
    <div className="flex flex-1 items-center gap-3 text-sm"><span className="hidden text-gray-400 sm:inline">Workspace</span><ChevronRight className="hidden h-3.5 w-3.5 text-gray-300 sm:block" /><span className="font-medium text-gray-700">{current}</span></div>
    <Link href="/dashboard/library/organize" className="flex items-center gap-2 rounded-full border border-primary-200 bg-primary-50 px-3 py-1.5 text-xs font-medium text-primary-700"><Sparkles className="h-3.5 w-3.5" />Make room for ideas</Link>
  </header>;
}

export function DashboardLayout({ children }: { children: ReactNode }) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  useEffect(() => {
    if (!mobileMenuOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setMobileMenuOpen(false); };
    window.addEventListener('keydown', close);
    return () => { document.body.style.overflow = previous; window.removeEventListener('keydown', close); };
  }, [mobileMenuOpen]);
  return <div className="min-h-screen bg-[#f7f8f4]">
    {mobileMenuOpen && <button className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden" onClick={() => setMobileMenuOpen(false)} aria-label="Close navigation" />}
    <Sidebar open={mobileMenuOpen} onClose={() => setMobileMenuOpen(false)} />
    <div className="lg:pl-64"><Header onMenuOpen={() => setMobileMenuOpen(true)} menuOpen={mobileMenuOpen} /><main id="main-content" className="mx-auto max-w-7xl px-5 py-8 sm:px-8 lg:px-10 lg:py-10">{children}</main></div>
  </div>;
}
