import type { ChatMessage, ChatSession, FolderEntry, ImageItem, NoteItem, TreeNode } from '../types';

const BACKEND_URL_KEY = 'paper-reader:backend-url';

/** 获取当前后端 BASE URL（空字符串表示同源） */
export function getBackendUrl(): string {
  try {
    return localStorage.getItem(BACKEND_URL_KEY) || '';
  } catch {
    return '';
  }
}

/** 设置后端 BASE URL，空字符串表示使用同源 */
export function setBackendUrl(url: string): void {
  const trimmed = url.trim().replace(/\/+$/, ''); // 去除尾部斜杠
  try {
    if (trimmed) {
      localStorage.setItem(BACKEND_URL_KEY, trimmed);
    } else {
      localStorage.removeItem(BACKEND_URL_KEY);
    }
  } catch { /* ignore */ }
}

/** 测试后端连接是否可用 */
export async function testBackendConnection(url: string): Promise<boolean> {
  const base = url.trim().replace(/\/+$/, '');
  try {
    const resp = await fetch(`${base}/api/tree`, { signal: AbortSignal.timeout(5000) });
    return resp.ok;
  } catch {
    return false;
  }
}

function BASE(): string {
  return getBackendUrl();
}

// ── Tree ──

export async function fetchTree(): Promise<TreeNode> {
  const resp = await fetch(`${BASE()}/api/tree`);
  return resp.json();
}

// ── Folder Management ──

export async function createFolder(
  parent: string,
  name: string,
): Promise<{ success?: boolean; path?: string; name?: string; error?: string }> {
  const resp = await fetch(`${BASE()}/api/folders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parent, name }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '创建失败');
  return data;
}

export async function renameFolder(
  oldPath: string,
  newName: string,
): Promise<{ success?: boolean; error?: string }> {
  const resp = await fetch(`${BASE()}/api/folders/rename`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ old_path: oldPath, new_name: newName }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '重命名失败');
  return data;
}

export async function deleteFolder(
  path: string,
): Promise<{ success?: boolean; error?: string }> {
  const resp = await fetch(`${BASE()}/api/folders/delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '删除失败');
  return data;
}

export async function moveFolder(
  srcPath: string,
  destParent: string,
): Promise<{ success?: boolean; error?: string }> {
  const resp = await fetch(`${BASE()}/api/folders/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ src_path: srcPath, dest_parent: destParent }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '移动失败');
  return data;
}

// ── Paper Management ──

export async function deletePaper(
  paperId: number,
): Promise<{ success?: boolean; error?: string }> {
  const resp = await fetch(`${BASE()}/api/papers/${paperId}`, { method: 'DELETE' });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '删除失败');
  return data;
}

export async function extractAlias(
  paperId: number,
): Promise<{ status: 'ok' | 'empty'; alias: string | null; alias_full: string | null }> {
  const resp = await fetch(`${BASE()}/api/papers/${paperId}/extract-alias`, { method: 'POST' });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '提取别名失败');
  return data;
}

export async function renamePaper(
  paperId: number,
  newName: string,
): Promise<{ success?: boolean; new_name?: string; error?: string }> {
  const resp = await fetch(`${BASE()}/api/papers/${paperId}/rename`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_name: newName }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '重命名失败');
  return data;
}

// ── PDF ──

export function pdfUrl(lang: string, paperId: number): string {
  return `${BASE()}/api/papers/${paperId}/pdf/${lang}`;
}

export async function checkPdfExists(lang: string, paperId: number): Promise<boolean> {
  try {
    const resp = await fetch(`${BASE()}/api/papers/${paperId}/pdf-exists/${lang}`);
    const data = await resp.json();
    return !!data.exists;
  } catch {
    return false;
  }
}

// ── Notes ──

export async function fetchNotes(paperId: number): Promise<NoteItem[]> {
  const resp = await fetch(`${BASE()}/api/papers/${paperId}/notes`);
  return resp.json();
}

export async function fetchNote(noteId: number): Promise<{ content: string; exists: boolean; id: number; title: string }> {
  const resp = await fetch(`${BASE()}/api/notes/${noteId}`);
  return resp.json();
}

export async function createNote(
  paperId: number,
  content: string,
  title?: string,
): Promise<{ success: boolean; id: number; title: string }> {
  const resp = await fetch(`${BASE()}/api/papers/${paperId}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, title }),
  });
  return resp.json();
}

export async function updateNote(
  noteId: number,
  content: string,
): Promise<{ success?: boolean; error?: string }> {
  const resp = await fetch(`${BASE()}/api/notes/${noteId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  return resp.json();
}

export async function deleteNote(noteId: number): Promise<{ success?: boolean; error?: string }> {
  const resp = await fetch(`${BASE()}/api/notes/${noteId}`, { method: 'DELETE' });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '删除失败');
  return data;
}

// ── Generate Note (SSE) ──

export async function generateNoteStream(
  paperId: number,
  onChunk: (text: string) => void,
  onDone: (noteId: number, title: string) => void,
  onError: (msg: string) => void,
  model?: string,
): Promise<void> {
  const resp = await fetch(`${BASE()}/api/papers/${paperId}/generate-note`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  });
  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.error || '生成失败');
  }

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop()!;

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const data = JSON.parse(line.slice(6));
        if (data.type === 'chunk') {
          onChunk(data.text);
        } else if (data.type === 'done') {
          onDone(data.note_id, data.title);
        } else if (data.type === 'error') {
          onError(data.message);
        }
      } catch {
        // ignore parse errors
      }
    }
  }
}

// ── Images ──

export async function fetchImages(paperId: number): Promise<ImageItem[]> {
  const resp = await fetch(`${BASE()}/api/papers/${paperId}/images`);
  return resp.json();
}

export function imageUrl(imageId: number, lang: string): string {
  return `${BASE()}/api/images/${imageId}/${lang}`;
}

export async function generateImage(
  paperId: number,
  model?: string,
): Promise<{ success: boolean; id: number; title: string }> {
  const resp = await fetch(`${BASE()}/api/papers/${paperId}/generate-image`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '生成失败');
  return data;
}

export async function translateImage(imageId: number): Promise<{ success?: boolean; error?: string }> {
  const resp = await fetch(`${BASE()}/api/images/${imageId}/translate`, { method: 'POST' });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '翻译失败');
  return data;
}

export async function deleteImage(imageId: number): Promise<{ success?: boolean; deleted?: string[]; error?: string }> {
  const resp = await fetch(`${BASE()}/api/images/${imageId}`, { method: 'DELETE' });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '删除失败');
  return data;
}

// ── arXiv fetch Chinese PDF ──

export async function fetchZhPdf(
  paperId: number,
  arxivId: string,
): Promise<{ success?: boolean; error?: string }> {
  const resp = await fetch(`${BASE()}/api/papers/${paperId}/fetch-zh-pdf`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ arxiv_id: arxivId }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '获取失败');
  return data;
}

// ── Upload Chinese PDF ──

export async function uploadZhPdf(
  paperId: number,
  file: File,
): Promise<{ success?: boolean; error?: string; size?: number }> {
  const form = new FormData();
  form.append('file', file);
  const resp = await fetch(`${BASE()}/api/papers/${paperId}/upload-zh-pdf`, {
    method: 'POST',
    body: form,
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '上传失败');
  return data;
}

// ── Upload / Manual Import Paper ──

export async function uploadPaper(
  file: File,
  folder: string,
  title?: string,
  fileZh?: File,
): Promise<{ success?: boolean; paper_id?: number; title?: string; error?: string }> {
  const form = new FormData();
  form.append('file', file);
  form.append('folder', folder);
  if (title) form.append('title', title);
  if (fileZh) form.append('file_zh', fileZh);
  const resp = await fetch(`${BASE()}/api/upload-paper`, {
    method: 'POST',
    body: form,
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '导入失败');
  return data;
}

// ── Folders ──

export async function fetchFolders(parent: string = ''): Promise<FolderEntry[]> {
  const normalizedParent = (parent || '').replace(/\\+/g, '/').replace(/^\/+/, '');
  const resp = await fetch(`${BASE()}/api/folders?parent=${encodeURIComponent(normalizedParent)}`);
  if (!resp.ok) {
    let errMsg = '目录加载失败';
    try {
      const err = await resp.json();
      errMsg = err?.error || errMsg;
    } catch {
      // ignore non-json error body
    }
    throw new Error(errMsg);
  }
  const data = await resp.json();
  return Array.isArray(data) ? data : [];
}

// ── Import Paper (SSE) ──

export async function importPaperStream(
  arxivId: string,
  folder: string,
  onStep: (data: { step: string; status: string; msg?: string; paper_id?: number }) => void,
): Promise<void> {
  const resp = await fetch(`${BASE()}/api/import-paper`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ arxiv_id: arxivId, folder }),
  });

  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.error || '导入失败');
  }

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop()!;

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const data = JSON.parse(line.slice(6));
        onStep(data);
      } catch {
        // ignore
      }
    }
  }
}

// ── Move Paper ──

export async function movePaper(
  paperId: number,
  destFolder: string,
): Promise<{ success?: boolean; error?: string }> {
  const resp = await fetch(`${BASE()}/api/papers/${paperId}/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dest_folder: destFolder }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '移动失败');
  return data;
}

// ── Chat Sessions ──

export async function fetchChatSessions(paperId: number): Promise<ChatSession[]> {
  const resp = await fetch(`${BASE()}/api/papers/${paperId}/chat-sessions`);
  return resp.json();
}

export async function createChatSession(
  paperId: number,
  title?: string,
): Promise<{ success: boolean; id: number; title: string }> {
  const resp = await fetch(`${BASE()}/api/papers/${paperId}/chat-sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  return resp.json();
}

export async function updateChatSession(
  sessionId: number,
  title: string,
): Promise<{ success?: boolean; error?: string }> {
  const resp = await fetch(`${BASE()}/api/chat-sessions/${sessionId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  return resp.json();
}

export async function deleteChatSession(
  sessionId: number,
): Promise<{ success?: boolean; error?: string }> {
  const resp = await fetch(`${BASE()}/api/chat-sessions/${sessionId}`, { method: 'DELETE' });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '删除失败');
  return data;
}

// ── Chat Messages ──

export async function fetchChatMessages(sessionId: number): Promise<ChatMessage[]> {
  const resp = await fetch(`${BASE()}/api/chat-sessions/${sessionId}/messages`);
  const data = await resp.json();
  return (data || []).map((item: any) => ({
    ...item,
    imageUrls: (item.image_urls || []).map((url: string) => `${BASE()}${url}`),
  }));
}

export async function sendChatMessage(
  sessionId: number,
  message: string,
  onChunk: (text: string) => void,
  onDone: (title?: string) => void,
  onError: (msg: string) => void,
  imageFiles?: File[],
  model?: string,
): Promise<void> {
  const hasImage = !!imageFiles && imageFiles.length > 0;
  const requestInit: RequestInit = { method: 'POST' };

  if (hasImage) {
    const formData = new FormData();
    formData.append('message', message);
    if (model) formData.append('model', model);
    imageFiles!.forEach((file) => formData.append('images', file));
    requestInit.body = formData;
  } else {
    requestInit.headers = { 'Content-Type': 'application/json' };
    requestInit.body = JSON.stringify({ message, model });
  }

  const resp = await fetch(`${BASE()}/api/chat-sessions/${sessionId}/chat`, requestInit);

  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.error || '发送失败');
  }

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop()!;

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const data = JSON.parse(line.slice(6));
        if (data.type === 'chunk') {
          onChunk(data.text);
        } else if (data.type === 'done') {
          onDone(data.title);
        } else if (data.type === 'error') {
          onError(data.message);
        }
      } catch {
        // ignore
      }
    }
  }
}

