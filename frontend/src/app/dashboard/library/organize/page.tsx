'use client';

import { useState, useEffect } from 'react';
import { isAxiosError } from 'axios';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { structuringApi } from '@/lib/api';
import { StructuringProposal, ProposedStructure, CreateNoteOperation } from '@/types';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Sparkles, CheckCircle, XCircle, MessageSquare, RefreshCw } from 'lucide-react';
import { format } from 'date-fns';
import { clsx } from 'clsx';

function proposalError(error: unknown, fallback: string): string {
  if (isAxiosError(error) && error.response?.status === 409 && typeof error.response.data?.detail === 'string') {
    return error.response.data.detail;
  }
  return fallback;
}

function StructureTree({ structure }: { structure: ProposedStructure }) {
  const creates: CreateNoteOperation[] = structure.operations
    ? structure.operations.filter((operation): operation is CreateNoteOperation => operation.action === 'create')
    : (structure.notes || []).map(note => ({ ...note, action: 'create' as const }));
  const updates = structure.operations?.filter(operation => operation.action === 'update') || [];
  return (
    <div className="space-y-4">
      {structure.folders.length > 0 && <div>
        <h4 className="font-medium mb-2">Proposed folders</h4>
        {structure.folders.map(folder => <p key={folder.path} className="text-sm">{folder.path}</p>)}
      </div>}
      {creates.map((note, index) => (
        <div key={`${note.title}-${index}`} className="rounded border border-gray-200 dark:border-gray-700 p-4 space-y-2">
          <h4 className="font-medium">Create: {note.title}</h4>
          <p className="text-sm text-gray-500">{note.folder_path}</p>
          {note.reason && <p className="text-sm">{note.reason}</p>}
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap text-sm bg-gray-50 dark:bg-gray-800 p-3 rounded">{note.content}</pre>
          <p className="text-xs text-gray-500">{note.tags.join(', ')}</p>
        </div>
      ))}
      {updates.map(operation => {
        const preview = structure._review?.updates.find(update => update.note_id === operation.note_id);
        return <div key={operation.note_id} className="rounded border border-primary-200 dark:border-primary-800 p-4 space-y-3">
          <h4 className="font-medium">Update: {preview?.title || operation.note_id}</h4>
          {preview && <p className="text-sm text-gray-500">{preview.folder_path}</p>}
          <p className="text-sm">{operation.reason}</p>
          {operation.edits.map((edit, index) => <p key={index} className="text-xs text-gray-500">
            {edit.action.replace('_', ' ')}{edit.target_section ? ` — ${edit.target_section}` : ''}
          </p>)}
          {preview ? <>
            <details open>
              <summary className="cursor-pointer text-sm font-medium">Changes</summary>
              <pre className="max-h-96 overflow-auto whitespace-pre-wrap text-sm bg-gray-50 dark:bg-gray-800 p-3 rounded mt-2">{preview.diff}</pre>
            </details>
            <div className="grid gap-3 md:grid-cols-2">
              <details><summary className="cursor-pointer text-sm">Before</summary>
                <pre className="max-h-96 overflow-auto whitespace-pre-wrap text-sm mt-2">{preview.before}</pre>
              </details>
              <details><summary className="cursor-pointer text-sm">After</summary>
                <pre className="max-h-96 overflow-auto whitespace-pre-wrap text-sm mt-2">{preview.after}</pre>
              </details>
            </div>
          </> : operation.edits.map((edit, index) => <div key={index}>
            <p className="text-sm">Anchor: {edit.anchor}</p>
            <pre className="whitespace-pre-wrap text-sm">{edit.content}</pre>
          </div>)}
        </div>;
      })}
    </div>
  );
}

function ProposalCard({ proposal, onAccept, onReject, onFeedback, onRefresh }: {
  proposal: StructuringProposal;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
  onFeedback: (id: string, feedback: string) => void;
  onRefresh: (id: string) => void;
}) {
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');
  const [isProcessing, setIsProcessing] = useState<'accept' | 'reject' | 'feedback' | 'refresh' | null>(null);

  const handleAccept = async () => {
    setIsProcessing('accept');
    try { await onAccept(proposal.id); } finally { setIsProcessing(null); }
  };

  const handleReject = async () => {
    setIsProcessing('reject');
    try { await onReject(proposal.id); } finally { setIsProcessing(null); }
  };

  const handleFeedbackSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!feedbackText.trim()) return;
    setIsProcessing('feedback');
    try { await onFeedback(proposal.id, feedbackText); } finally { setIsProcessing(null); setFeedbackText(''); setShowFeedback(false); }
  };

  const handleRefresh = async () => {
    setIsProcessing('refresh');
    try { await onRefresh(proposal.id); } finally { setIsProcessing(null); }
  };

  const statusColors = {
    pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    accepted: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    rejected: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  };

  const statusIcons = {
    pending: <Sparkles className="h-4 w-4" />,
    accepted: <CheckCircle className="h-4 w-4" />,
    rejected: <XCircle className="h-4 w-4" />,
  };

  if (proposal.status !== 'pending') {
    return (
      <Card className="border-l-4 border-l-gray-300 dark:border-l-gray-600">
        <CardContent className="py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className={clsx('px-2 py-1 rounded text-xs font-medium', statusColors[proposal.status])}>
                {statusIcons[proposal.status]}
                {proposal.status.charAt(0).toUpperCase() + proposal.status.slice(1)}
              </span>
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {format(new Date(proposal.created_at), 'MMM d, yyyy HH:mm')}
              </span>
            </div>
            {proposal.feedback && (
              <span className="text-xs text-gray-500 dark:text-gray-400">Refined: {proposal.feedback.slice(0, 50)}...</span>
            )}
          </div>
          <div className="mt-3 p-3 bg-gray-50 dark:bg-gray-800 rounded text-sm text-gray-600 dark:text-gray-400">
            <p className="font-medium mb-1">Original snippet:</p>
            <p>{proposal.input_snippet.slice(0, 200)}...</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-l-4 border-l-primary-500">
      <CardContent className="py-4">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className={clsx('px-2 py-1 rounded text-xs font-medium', statusColors.pending)}>
                {statusIcons.pending}
                Pending Review
              </span>
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {format(new Date(proposal.created_at), 'MMM d, yyyy HH:mm')}
              </span>
            </div>
            <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded text-sm text-gray-600 dark:text-gray-400 max-h-32 overflow-y-auto">
              <p className="font-medium mb-1">Input snippet:</p>
              <p>{proposal.input_snippet}</p>
            </div>
          </div>
        </div>

        <StructureTree structure={proposal.proposed_structure} />

        <div className="flex flex-wrap items-center gap-2 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <Button onClick={handleAccept} isLoading={isProcessing === 'accept'} className="w-full sm:w-auto">
            <CheckCircle className="h-4 w-4 mr-2" />
            Save to library
          </Button>
          <Button variant="secondary" onClick={handleReject} isLoading={isProcessing === 'reject'} className="w-full sm:w-auto">
            <XCircle className="h-4 w-4 mr-2" />
            Reject
          </Button>
          <Button variant="ghost" onClick={() => setShowFeedback(!showFeedback)} isLoading={isProcessing === 'feedback'} className="w-full sm:w-auto">
            <MessageSquare className="h-4 w-4 mr-2" />
            Feedback
          </Button>
          <Button variant="ghost" onClick={handleRefresh} isLoading={isProcessing === 'refresh'} className="w-full sm:w-auto ml-auto">
            <RefreshCw className={clsx('h-4 w-4 mr-2', isProcessing === 'refresh' && 'animate-spin')} />
            Regenerate
          </Button>
        </div>

        {showFeedback && (
          <form onSubmit={handleFeedbackSubmit} className="mt-4 space-y-2">
            <label className="label">Your feedback for revision</label>
            <textarea
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value)}
              placeholder="e.g., 'Create separate folders for frontend and backend', 'Add more technical details', 'Use simpler language'..."
              className="input min-h-[80px] resize-y"
              rows={3}
            />
            <div className="flex justify-end gap-2">
              <Button type="button" variant="secondary" onClick={() => { setShowFeedback(false); setFeedbackText(''); }}>Cancel</Button>
              <Button type="submit" isLoading={isProcessing === 'feedback'}>Submit Feedback</Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

export default function OrganizePage() {
  const router = useRouter();
  const [error, setError] = useState('');
  const [snippet, setSnippet] = useState('');
  const [context, setContext] = useState('');
  const [proposals, setProposals] = useState<StructuringProposal[]>([]);
  const [creating, setCreating] = useState(false);
  const [activeTab, setActiveTab] = useState<'create' | 'history'>('create');

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('review') === 'true') setActiveTab('history');
    loadProposals();
  }, []);

  const loadProposals = async () => {
    try {
      const res = await structuringApi.list();
      setProposals(res.data);
    } catch (error) {
      setError('Unable to load your proposals. Please try again.');
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!snippet.trim()) return;
    setCreating(true);
    setError('');
    try {
      const res = await structuringApi.create({ snippet, context: context || undefined });
      setProposals([res.data, ...proposals]);
      setActiveTab('history');
    } catch (error) {
      setError(proposalError(error, 'Unable to generate a structure. Please try again.'));
    } finally {
      setCreating(false);
    }
  };

  const handleAccept = async (id: string) => {
    try {
      const result = await structuringApi.accept(id);
      const saved = result.data.notes.map(note => note.id).join(',');
      router.push(`/dashboard/library${saved ? `?saved=${encodeURIComponent(saved)}` : ''}`);
    } catch (error) {
      setError(proposalError(error, 'Unable to accept the proposal. Please try again.'));
    }
  };

  const handleReject = async (id: string) => {
    try {
      await structuringApi.reject(id);
      setProposals(proposals.map(p => p.id === id ? { ...p, status: 'rejected' as const } : p));
    } catch (error) {
      setError('Unable to reject the proposal. Please try again.');
    }
  };

  const handleFeedback = async (id: string, feedback: string) => {
    try {
      const res = await structuringApi.feedback(id, feedback);
      setProposals(proposals.map(p => p.id === id ? res.data : p));
    } catch (error) {
      setError(proposalError(error, 'Unable to submit your feedback. Please try again.'));
    }
  };

  const handleRefresh = async (id: string) => {
    try {
      const proposal = proposals.find(p => p.id === id);
      if (!proposal) return;
      const res = await structuringApi.create({ snippet: proposal.input_snippet, context: proposal.proposed_structure._request_context || undefined });
      setProposals([res.data, ...proposals.filter(p => p.id !== id)]);
    } catch (error) {
      setError(proposalError(error, 'Unable to regenerate the proposal. Please try again.'));
    }
  };

  const pendingProposals = proposals.filter(p => p.status === 'pending');
  const processedProposals = proposals.filter(p => p.status !== 'pending');

  return (
    <div className="space-y-6">
      <div>
        <Link href="/dashboard/library" className="mb-4 inline-block text-sm text-primary-700 hover:underline">← Back to Library</Link>
        <h1 className="font-editorial text-4xl text-primary-900">Add to library</h1>
        <p className="text-gray-600 dark:text-gray-400">Drop in your thoughts, snippets, or rough notes. AI suggests structure and placement for you to review.</p>
      </div>

      {error && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</p>}
      <div className="grid gap-3 sm:grid-cols-3">{[
        ['01', 'Capture', 'Paste your rough notes or snippets.'],
        ['02', 'Connect', 'AI suggests notes, folders, and tags.'],
        ['03', 'Make it yours', 'Review and accept before anything is saved.'],
      ].map(([number, title, description]) => <div key={number} className="flex items-start gap-3 rounded-xl border border-gray-200/70 bg-white/60 p-4"><span className="text-xs font-semibold text-primary-500">{number}</span><div><p className="text-sm font-medium text-gray-700">{title}</p><p className="mt-1 text-xs leading-5 text-gray-500">{description}</p></div></div>)}</div>
      <div className="flex gap-4 border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setActiveTab('create')}
          className={clsx('px-4 py-2 text-sm font-medium border-b-2 transition-colors', activeTab === 'create' ? 'border-primary-500 text-primary-600' : 'border-transparent text-gray-500 hover:text-gray-700')}
        >
          <Sparkles className="h-4 w-4 inline mr-1" /> Your input
        </button>
        <button
          onClick={() => setActiveTab('history')}
          className={clsx('px-4 py-2 text-sm font-medium border-b-2 transition-colors', activeTab === 'history' ? 'border-primary-500 text-primary-600' : 'border-transparent text-gray-500 hover:text-gray-700')}
        >
          <Clock className="h-4 w-4 inline mr-1" /> Review & history ({proposals.length})
        </button>
      </div>

      {activeTab === 'create' && (
        <Card>
          <CardHeader>
            <CardTitle>What do you want to save?</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-1">
                <label className="label">Your notes or snippets</label>
                <textarea
                  value={snippet}
                  onChange={(e) => setSnippet(e.target.value)}
                  placeholder="A meeting recap, a code snippet, an idea you don’t want to lose… Paste it here and we’ll help you find the structure."
                  className="input min-h-[260px] resize-y leading-7 text-sm"
                  required
                />
              </div>
              <div className="space-y-1">
                <label className="label">Instructions (optional)</label>
                <textarea
                  value={context}
                  onChange={(e) => setContext(e.target.value)}
                  placeholder="For example: keep my wording, explain the code, or expand the explanation."
                  className="input min-h-[80px] resize-y"
                  rows={3}
                />
              </div>
              <Button type="submit" isLoading={creating} disabled={!snippet.trim()} className="w-full sm:w-auto">
                <Sparkles className="h-4 w-4 mr-2" />
                Organize my notes
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {activeTab === 'history' && (
        <div className="space-y-4">
          <Button variant="secondary" onClick={() => { setError(''); setActiveTab('create'); }}>← Back to input</Button>
          {pendingProposals.length > 0 && (
            <div>
              <h3 className="font-medium text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-yellow-500" />
                Pending Review ({pendingProposals.length})
              </h3>
              <div className="space-y-4">
                {pendingProposals.map(proposal => (
                  <ProposalCard
                    key={proposal.id}
                    proposal={proposal}
                    onAccept={handleAccept}
                    onReject={handleReject}
                    onFeedback={handleFeedback}
                    onRefresh={handleRefresh}
                  />
                ))}
              </div>
            </div>
          )}

          {processedProposals.length > 0 && (
            <div>
              <h3 className="font-medium text-gray-900 dark:text-white mb-3">History</h3>
              <div className="space-y-4">
                {processedProposals.map(proposal => (
                  <ProposalCard
                    key={proposal.id}
                    proposal={proposal}
                    onAccept={handleAccept}
                    onReject={handleReject}
                    onFeedback={handleFeedback}
                    onRefresh={handleRefresh}
                  />
                ))}
              </div>
            </div>
          )}

          {proposals.length === 0 && (
            <Card>
              <CardContent className="py-12 text-center">
                <Sparkles className="h-12 w-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
                <p className="text-gray-600 dark:text-gray-400">No proposals yet</p>
                <Button onClick={() => setActiveTab('create')} className="mt-4">
                  <Sparkles className="h-4 w-4 mr-2" />
                  Add your first notes
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

import { Clock } from 'lucide-react';