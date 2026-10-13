import { redirect } from 'next/navigation';

export default function NotesPage({ searchParams }: { searchParams: { create?: string; edit?: string } }) {
  const params = new URLSearchParams();
  if (searchParams.create) params.set('create', searchParams.create);
  if (searchParams.edit) params.set('edit', searchParams.edit);
  redirect(`/dashboard/library${params.size ? `?${params}` : ''}`);
}
