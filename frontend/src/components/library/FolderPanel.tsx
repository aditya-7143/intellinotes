'use client';

import { useState } from 'react';
import { Folder } from '@/types';
import { folderApi } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { FolderOpen, Plus, Edit, Trash2, Files, Inbox } from 'lucide-react';

export function flattenFolders(folders: Folder[]): Folder[] {
  const unique = new Map<string, Folder>();
  const visit = (items: Folder[]) => items.forEach(folder => {
    if (unique.has(folder.path)) return;
    unique.set(folder.path, folder);
    visit(folder.children || []);
  });
  visit(folders);
  return Array.from(unique.values());
}

export function FolderPanel({ folders, selected, onSelect, onRefresh }: {
  folders: Folder[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  onRefresh: () => Promise<void>;
}) {
  const [form, setForm] = useState<{ path?: string; name: string; parent_path: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const allFolders = flattenFolders(folders);
  const openForm = (folder?: Folder) => {
    setError('');
    setForm(folder ? { path: folder.path, name: folder.name, parent_path: folder.parent_path || '' } : {
      name: '', parent_path: selected && selected !== 'unfiled' ? selected : '',
    });
  };
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!form) return;
    setBusy(true);
    setError('');
    try {
      if (form.path) {
        const updated = await folderApi.update(form.path, { name: form.name.trim() });
        if (selected === form.path) onSelect(updated.data.path);
        else if (selected?.startsWith(form.path + '/')) onSelect(updated.data.path + selected.slice(form.path.length));
      }
      else await folderApi.create({ name: form.name.trim(), parent_path: form.parent_path || '/' });
      setForm(null);
      await onRefresh();
    } catch {
      setError('Unable to save this folder. Check the name and try again.');
    } finally { setBusy(false); }
  };
  const remove = async (folder: Folder) => {
    if (!confirm(`Delete "${folder.name}"? Only empty folders can be deleted. Move or delete its notes and subfolders first.`)) return;
    setError('');
    try {
      await folderApi.delete(folder.path);
      if (selected === folder.path) onSelect(null);
      await onRefresh();
    } catch { setError('Unable to delete this folder. Move or delete its notes and subfolders first, then try again.'); }
  };
  const render = (parent: string | null, depth = 0, visited = new Set<string>()): React.ReactNode =>
    allFolders.filter(folder => folder.parent_path === (parent || '/')).map(folder => {
      if (visited.has(folder.path)) return null;
      const next = new Set(visited).add(folder.path);
      return <div key={folder.path}>
        <div className={`group flex items-center gap-1 rounded-xl pr-2 ${selected === folder.path ? 'bg-primary-50 text-primary-800' : 'text-gray-600 hover:bg-gray-50'}`} style={{ paddingLeft: 8 + depth * 12 }}>
          <button type="button" onClick={() => onSelect(folder.path)} aria-pressed={selected === folder.path} className="flex min-w-0 flex-1 items-center gap-2 py-3 text-left text-sm">
            <FolderOpen className="h-4 w-4 shrink-0" /><span className="truncate" title={folder.path}>{folder.name}</span>
          </button>
          <button type="button" aria-label={`Rename ${folder.name}`} onClick={() => openForm(folder)} className="rounded p-1.5 hover:bg-primary-100"><Edit className="h-3.5 w-3.5" /></button>
          <button type="button" aria-label={`Delete ${folder.name}`} onClick={() => remove(folder)} className="rounded p-1.5 text-red-500 hover:bg-red-50"><Trash2 className="h-3.5 w-3.5" /></button>
        </div>
        {render(folder.path, depth + 1, next)}
      </div>;
    });

  return <>
    <aside aria-label="Library folders" className="self-start rounded-2xl border border-gray-200/80 bg-white p-3 lg:sticky lg:top-24">
      <div className="mb-3 flex items-center justify-between px-2"><h2 className="text-sm font-semibold text-primary-900">Your library</h2><button type="button" aria-label="Create folder" onClick={() => openForm()} className="rounded-lg p-2 text-primary-700 hover:bg-primary-50"><Plus className="h-4 w-4" /></button></div>
      {[{ id: null, label: 'All notes', Icon: Files }, { id: 'unfiled', label: 'Unfiled', Icon: Inbox }].map(({ id, label, Icon }) => <button key={label} type="button" aria-pressed={selected === id} onClick={() => onSelect(id)} className={`mb-1 flex w-full items-center gap-2 rounded-xl px-3 py-3 text-sm ${selected === id ? 'bg-primary-50 font-medium text-primary-800' : 'text-gray-600 hover:bg-gray-50'}`}><Icon className="h-4 w-4" />{label}</button>)}
      <div className="my-3 border-t border-gray-100" />
      <div className="max-h-72 overflow-auto lg:max-h-[55vh]">{render(null)}</div>
      {!allFolders.length && <p className="px-3 py-4 text-xs leading-5 text-gray-500">Create a folder to group related notes.</p>}
      <Button variant="ghost" size="sm" className="mt-3 w-full justify-start" onClick={() => openForm()}><Plus className="mr-2 h-4 w-4" />New folder</Button>
      {error && !form && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-xs text-red-700">{error}</p>}
    </aside>
    {form && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
      <Card className="w-full max-w-md" role="dialog" aria-modal="true" aria-labelledby="folder-dialog-title">
        <CardHeader><CardTitle id="folder-dialog-title">{form.path ? 'Rename folder' : 'New folder'}</CardTitle></CardHeader>
        <CardContent><form onSubmit={save} className="space-y-4">
          {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          <Input label="Folder name" required autoFocus value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
          {!form.path && <div><label htmlFor="folder-parent" className="label">Parent folder</label><select id="folder-parent" className="input" value={form.parent_path} onChange={e => setForm({ ...form, parent_path: e.target.value })}><option value="">Root level</option>{allFolders.map(folder => <option key={folder.path} value={folder.path}>{folder.path}</option>)}</select></div>}
          <div className="flex justify-end gap-2"><Button type="button" variant="secondary" disabled={busy} onClick={() => setForm(null)}>Cancel</Button><Button type="submit" isLoading={busy} disabled={!form.name.trim()}>Save folder</Button></div>
        </form></CardContent>
      </Card>
    </div>}
  </>;
}
