import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { TokenPair, User, Folder, Note, StructuringProposal, StructureRequest } from '@/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

let accessToken: string | null = null;
let refreshToken: string | null = null;

export const setTokens = (tokens: TokenPair) => {
  accessToken = tokens.access_token;
  refreshToken = tokens.refresh_token;
  if (typeof window !== 'undefined') {
    localStorage.setItem('access_token', tokens.access_token);
    localStorage.setItem('refresh_token', tokens.refresh_token);
  }
};

export const getTokens = (): TokenPair | null => {
  if (typeof window !== 'undefined') {
    const at = localStorage.getItem('access_token');
    const rt = localStorage.getItem('refresh_token');
    if (at && rt) {
      accessToken = at;
      refreshToken = rt;
      return { access_token: at, refresh_token: rt, token_type: 'bearer' };
    }
  }
  return null;
};

export const clearTokens = () => {
  accessToken = null;
  refreshToken = null;
  if (typeof window !== 'undefined') {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }
};

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value: unknown) => void;
  reject: (reason: unknown) => void;
}> = [];

const processQueue = (error: Error | null, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !originalRequest._retry && refreshToken) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return api(originalRequest);
        }).catch((err) => {
          return Promise.reject(err);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const response = await axios.post(`${API_URL}/api/v1/auth/refresh`, {
          refresh_token: refreshToken,
        });
        const tokens = response.data;
        setTokens(tokens);
        processQueue(null, tokens.access_token);
        originalRequest.headers.Authorization = `Bearer ${tokens.access_token}`;
        return api(originalRequest);
      } catch (err) {
        processQueue(err as Error, null);
        clearTokens();
        if (typeof window !== 'undefined') {
          window.location.href = '/auth/login';
        }
        return Promise.reject(err);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export const authApi = {
  register: (email: string, password: string, full_name: string) =>
    api.post<TokenPair>('/auth/register', { email, password, full_name }),
  login: (email: string, password: string) =>
    api.post<TokenPair>('/auth/login', { email, password }),
  refresh: (refresh_token: string) =>
    api.post<TokenPair>('/auth/refresh', { refresh_token }),
  getMe: () => api.get<User>('/auth/me'),
  updateMe: (data: Partial<User>) => api.patch<User>('/auth/me', data),
};

export const folderApi = {
  list: () => api.get<Folder[]>('/folders'),
  create: (data: { name: string; parent_id?: string }) =>
    api.post<Folder>('/folders', data),
  get: (id: string) => api.get<Folder>(`/folders/${id}`),
  update: (id: string, data: { name?: string; parent_id?: string }) =>
    api.patch<Folder>(`/folders/${id}`, data),
  delete: (id: string) => api.delete(`/folders/${id}`),
};

export const noteApi = {
  list: (folderId?: string) =>
    api.get<Note[]>('/notes', { params: { folder_id: folderId } }),
  search: (query: string) =>
    api.get<Note[]>('/notes/search', { params: { q: query } }),
  create: (data: { title?: string; content: string; folder_id?: string; tags?: string[] }) =>
    api.post<Note>('/notes', data),
  get: (id: string) => api.get<Note>(`/notes/${id}`),
  update: (id: string, data: { title?: string; content?: string; folder_id?: string; tags?: string[] }) =>
    api.patch<Note>(`/notes/${id}`, data),
  delete: (id: string) => api.delete(`/notes/${id}`),
};

export const structuringApi = {
  create: (data: StructureRequest) =>
    api.post<StructuringProposal>('/structuring', data),
  list: (status?: string) =>
    api.get<StructuringProposal[]>('/structuring', { params: { status } }),
  get: (id: string) => api.get<StructuringProposal>(`/structuring/${id}`),
  accept: (id: string) =>
    api.post<{ folders: Folder[]; notes: Note[] }>(`/structuring/${id}/accept`),
  reject: (id: string) => api.post<StructuringProposal>(`/structuring/${id}/reject`),
  feedback: (id: string, feedback: string) =>
    api.post<StructuringProposal>(`/structuring/${id}/feedback`, { action: 'feedback', feedback }),
};

export default api;
