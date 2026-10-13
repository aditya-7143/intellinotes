export interface User {
  id: string;
  email: string;
  full_name: string;
  settings: Record<string, unknown>;
  created_at: string;
}

export interface Folder {
  id: string;
  user_id: string;
  name: string;
  parent_id: string | null;
  path: string;
  created_at: string;
  updated_at: string;
  children: Folder[];
}

export interface Note {
  id: string;
  user_id: string;
  folder_id: string | null;
  title: string;
  content: string;
  folder_path: string;
  tags: string[];
  storage_key: string | null;
  created_at: string;
  updated_at: string;
}

export interface StructuringProposal {
  id: string;
  user_id: string;
  input_snippet: string;
  proposed_structure: ProposedStructure;
  status: 'pending' | 'accepted' | 'rejected';
  feedback: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProposedStructure {
  folders: Array<{
    name: string;
    path: string;
  }>;
  notes: Array<{
    title: string;
    content: string;
    folder_path: string;
    tags: string[];
  }>;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface StructureRequest {
  snippet: string;
  context?: string;
}

export interface ProposalAction {
  action: 'accept' | 'reject' | 'feedback';
  feedback?: string;
}