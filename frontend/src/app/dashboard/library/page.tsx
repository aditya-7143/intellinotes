'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { noteApi, folderApi } from '@/lib/api';
import { Note, Folder } from '@/types';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { FileText, Plus, Search, Edit, Trash2, Folder as FolderIcon, Tag, Sparkles } from 'lucide-react';
import { format } from 'date-fns';
import { FolderPanel, flattenFolders } from '@/components/library/FolderPanel';

export default function LibraryPage() {
  const router = useRouter();
  const [savedIds, setSavedIds] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [notes, setNotes] = useState<Note[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingNote, setEditingNote] = useState<Note | null>(null);
  const [savingNote, setSavingNote] = useState(false);
  const [formData, setFormData] = useState({ title: '', content: '', folder_path: '', tags: '' });

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError('');
    try {
      const [notesRes, foldersRes] = await Promise.all([
        noteApi.list(),
        folderApi.list(),
      ]);
      setNotes(notesRes.data);
      setFolders(flattenFolders(foldersRes.data));
    } catch (error) {
      setError('Unable to load your notes. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleOpenEditModal = (note: Note) => {
    setError('');
    setEditingNote(note);
    setFormData({
      title: note.title,
      content: note.content,
      folder_path: note.folder_path || '',
      tags: note.tags ? note.tags.join(', ') : '',
    });
    setShowEditModal(true);
  };

  useEffect(() => {
    if (isLoading) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get('saved')) {
      setSavedIds(params.get('saved')!.split(','));
      window.history.replaceState(null, '', '/dashboard/library');
    } else if (params.get('add') === 'true' || params.get('create') === 'true') {
      router.replace('/dashboard/library/organize');
    } else if (params.get('edit')) {
      const note = notes.find(item => item.id === params.get('edit'));
      if (note) {
        setEditingNote(note);
        setFormData({ title: note.title, content: note.content, folder_path: note.folder_path || '', tags: note.tags.join(', ') });
        setShowEditModal(true);
        window.history.replaceState(null, '', '/dashboard/library');
      }
    }
  }, [isLoading, notes, router]);

  const handleSaveNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingNote) return;
    setError('');
    setSavingNote(true);
    try {
      const payload = {
        title: formData.title.trim() || undefined,
        content: formData.content,
        folder_path: formData.folder_path || '/',
        tags: formData.tags.split(',').map((t) => t.trim()).filter(Boolean),
      };
      const response = await noteApi.update(editingNote.id, payload);
      setSavedIds([response.data.id]);
      setShowEditModal(false);
      setEditingNote(null);
      setFormData({ title: '', content: '', folder_path: '', tags: '' });
      loadData();
    } catch (error) {
      setError('Unable to save this note. Please try again.');
    } finally {
      setSavingNote(false);
    }
  };

  const handleDeleteNote = async (id: string) => {
    if (!confirm('Are you sure you want to delete this note?')) return;
    try {
      await noteApi.delete(id);
      loadData();
    } catch (error) {
      setError('Unable to delete this note. Please try again.');
    }
  };

  const filteredNotes = notes.filter(note =>
    (selectedFolder === null || (selectedFolder === 'unfiled' ? note.folder_path === '/' : note.folder_path === selectedFolder)) && (
    note.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    note.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
    note.tags.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase())))
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-editorial text-4xl text-primary-900">Your library</h1>
          <p className="text-gray-600 dark:text-gray-400">Your notes and folders, together in one place.</p>
        </div>
        <Button onClick={() => router.push('/dashboard/library/organize')}>
          <Plus className="h-4 w-4 mr-2" />
          Add to library
        </Button>
      </div>

      {savedIds.length > 0 && <p role="status" className="rounded-xl border border-primary-200 bg-primary-50 p-3 text-sm text-primary-800">Saved to your library. Your saved notes are highlighted below.</p>}
      <Link href="/dashboard/library/organize?review=true" className="inline-flex items-center gap-2 text-sm text-primary-700 hover:underline"><Sparkles className="h-4 w-4" />Review AI proposals</Link>
      <div className="grid items-start gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
        <FolderPanel folders={folders} selected={selectedFolder} onSelect={setSelectedFolder} onRefresh={loadData} />
        <section aria-label="Notes" className="min-w-0 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-primary-900">{selectedFolder === 'unfiled' ? 'Unfiled' : folders.find(folder => folder.path === selectedFolder)?.path || 'All notes'}</h2>
            <span className="shrink-0 text-xs text-gray-500">{isLoading ? 'Loading…' : `${filteredNotes.length} ${filteredNotes.length === 1 ? 'note' : 'notes'}`}</span>
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input type="search" aria-label="Search notes in this view" placeholder="Search titles, content, or tags…" value={searchQuery} onChange={event => setSearchQuery(event.target.value)} className="input pl-10" />
          </div>

      {error && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <Card key={i} className="animate-pulse">
              <CardContent>
                <div className="h-4 bg-gray-200 rounded w-3/4 mb-2 dark:bg-gray-700" />
                <div className="h-4 bg-gray-200 rounded w-1/2 dark:bg-gray-700" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : error && notes.length === 0 ? (
        <Button variant="secondary" onClick={loadData}>Try again</Button>
      ) : filteredNotes.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <FileText className="h-12 w-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
            <p className="text-gray-600 dark:text-gray-400">{searchQuery || selectedFolder ? 'No matching notes. Try another search or folder.' : 'Your collection starts with a single thought.'}</p>
            <Button onClick={() => router.push('/dashboard/library/organize')} className="mt-4">
              <Plus className="h-4 w-4 mr-2" />
              Add to library
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {filteredNotes.map(note => (
            <Card key={note.id} className={`transition-all hover:border-primary-200 hover:shadow-md ${savedIds.includes(note.id) ? 'border-primary-300 ring-2 ring-primary-100' : ''}`}>
              <CardContent className="flex flex-col sm:flex-row sm:items-start gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-semibold text-gray-900 dark:text-white truncate">{note.title}</h3>
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" aria-label={`Edit ${note.title}`} onClick={() => handleOpenEditModal(note)}>
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="sm" aria-label={`Delete ${note.title}`} onClick={() => handleDeleteNote(note.id)}>
                        <Trash2 className="h-4 w-4 text-red-600" />
                      </Button>
                    </div>
                  </div>
                  <p className="text-gray-600 dark:text-gray-400 text-sm mt-3 leading-6 line-clamp-3">{note.content}</p>
                  <div className="flex flex-wrap items-center gap-2 mt-3 text-xs text-gray-500 dark:text-gray-400">
                    {note.folder_path !== '/' && (
                      <span className="flex items-center gap-1 px-2 py-0.5 bg-gray-100 dark:bg-gray-800 rounded">
                        <FolderIcon className="h-3 w-3" />
                        {note.folder_path}
                      </span>
                    )}
                    {note.tags.map(tag => (
                      <span key={tag} className="flex items-center gap-1 px-2 py-0.5 bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 rounded">
                        <Tag className="h-3 w-3" />
                        {tag}
                      </span>
                    ))}
                    <span className="ml-auto">
                      {format(new Date(note.updated_at), 'MMM d, yyyy HH:mm')}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

        </section>
      </div>

      {showEditModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <CardHeader>
              <CardTitle>Edit note</CardTitle>
            </CardHeader>
            <CardContent>
              {error && <p role="alert" className="mb-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
              <form onSubmit={handleSaveNote} className="space-y-4">
                <Input label="Title" placeholder="Note title" value={formData.title} onChange={(e) => setFormData({ ...formData, title: e.target.value })} required maxLength={500} />
                <div className="space-y-1">
                  <label className="label">Content</label>
                  <textarea
                    value={formData.content}
                    onChange={(e) => setFormData({ ...formData, content: e.target.value })}
                    className="input min-h-[200px] resize-y"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="label">Folder (optional)</label>
                  <select
                    value={formData.folder_path || '/'}
                    onChange={(e) => setFormData({ ...formData, folder_path: e.target.value })}
                    className="input"
                  >
                    <option value="/">No Folder (Root /)</option>
                    {folders.map((f) => (
                      <option key={f.path} value={f.path}>
                        {f.path || f.name}
                      </option>
                    ))}
                  </select>
                </div>
                <Input label="Tags (comma separated)" placeholder="tag1, tag2, tag3" value={formData.tags} onChange={(e) => setFormData({ ...formData, tags: e.target.value })} />
                <div className="flex justify-end gap-2 pt-4">
                  <Button type="button" variant="secondary" onClick={() => setShowEditModal(false)}>Back to Library</Button>
                  <Button type="submit" isLoading={savingNote}>Save changes</Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
