import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type {
    ChatSession,
    ContextMenuState,
    DirNode,
    ImageItem,
    ImageLang,
    NoteItem,
    PaperNode,
    PdfMode,
    PreCompareLayout,
    RightTab,
    TreeNode,
} from '../types';

// ── 持久化工具：保存/读取 PDF 页码 ──
const PDF_PAGE_KEY = 'paper-reader:pdf-pages';

export function savePdfPage(paperId: number, page: number) {
  try {
    const pages = JSON.parse(localStorage.getItem(PDF_PAGE_KEY) || '{}');
    pages[paperId] = page;
    localStorage.setItem(PDF_PAGE_KEY, JSON.stringify(pages));
  } catch { /* ignore */ }
}

export function loadPdfPage(paperId: number): number | null {
  try {
    const pages = JSON.parse(localStorage.getItem(PDF_PAGE_KEY) || '{}');
    return pages[paperId] ?? null;
  } catch { return null; }
}

interface AppState {
  // ── Tree ──
  treeData: TreeNode | null;
  setTreeData: (data: TreeNode | null) => void;

  // ── Current paper ──
  currentPaper: PaperNode | null;
  setCurrentPaper: (paper: PaperNode | null) => void;

  // ── PDF mode ──
  pdfMode: PdfMode;
  setPdfMode: (mode: PdfMode) => void;

  // ── Image language ──
  imageLang: ImageLang;
  setImageLang: (lang: ImageLang) => void;

  // ── Right panel tab ──
  rightTab: RightTab;
  setRightTab: (tab: RightTab) => void;

  // ── Notes (multi-note) ──
  notesList: NoteItem[];
  setNotesList: (notes: NoteItem[]) => void;
  currentNoteId: number | null;
  setCurrentNoteId: (id: number | null) => void;
  isEditing: boolean;
  setIsEditing: (v: boolean) => void;
  noteModified: boolean;
  setNoteModified: (v: boolean) => void;
  originalNoteContent: string;
  setOriginalNoteContent: (c: string) => void;
  generatingNote: boolean;
  setGeneratingNote: (v: boolean) => void;
  generatingNotePaperId: number | null;
  setGeneratingNotePaperId: (id: number | null) => void;

  // ── Images (multi-image) ──
  imagesList: ImageItem[];
  setImagesList: (images: ImageItem[]) => void;
  currentImageId: number | null;
  setCurrentImageId: (id: number | null) => void;
  generatingImage: boolean;
  setGeneratingImage: (v: boolean) => void;
  generatingImagePaperId: number | null;
  setGeneratingImagePaperId: (id: number | null) => void;

  // ── Chat ──
  chatSessions: ChatSession[];
  setChatSessions: (sessions: ChatSession[]) => void;
  currentChatSessionId: number | null;
  setCurrentChatSessionId: (id: number | null) => void;
  chatStreaming: boolean;
  setChatStreaming: (v: boolean) => void;
  noteModel: string;
  setNoteModel: (v: string) => void;
  imageModel: string;
  setImageModel: (v: string) => void;
  chatModel: string;
  setChatModel: (v: string) => void;

  // ── Layout ──
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (v: boolean) => void;
  rightCollapsed: boolean;
  setRightCollapsed: (v: boolean) => void;
  preCompareLayout: PreCompareLayout | null;
  setPreCompareLayout: (v: PreCompareLayout | null) => void;

  // ── Context menu ──
  contextMenu: ContextMenuState;
  showContextMenu: (x: number, y: number, target: PaperNode | null, dirTarget?: DirNode | null) => void;
  hideContextMenu: () => void;

  // ── Multi-select ──
  selectedItems: Set<string>;   // "file:id" or "dir:path"
  setSelectedItems: (items: Set<string>) => void;
  toggleSelectItem: (key: string, multi: boolean) => void;
  clearSelection: () => void;

  // ── Inline rename ──
  renamingKey: string | null; // "file:id" or "dir:path"
  setRenamingKey: (key: string | null) => void;

  // ── Drag-drop ──
  dragSource: string | null; // "file:id" or "dir:path"
  setDragSource: (key: string | null) => void;
  dropTarget: string | null; // "dir:path"
  setDropTarget: (key: string | null) => void;

  // ── Modals ──
  importModalOpen: boolean;
  setImportModalOpen: (v: boolean) => void;
  moveModalOpen: boolean;
  setMoveModalOpen: (v: boolean) => void;
  moveTargetId: number | null;
  setMoveTargetId: (v: number | null) => void;
  moveTargetIds: number[];
  setMoveTargetIds: (v: number[]) => void;
  moveFolderPath: string | null;
  setMoveFolderPath: (v: string | null) => void;
  moveTargetName: string;
  setMoveTargetName: (v: string) => void;

  // ── Import state ──
  importing: boolean;
  setImporting: (v: boolean) => void;

  // ── Lightbox ──
  lightboxOpen: boolean;
  setLightboxOpen: (v: boolean) => void;

  // ── Settings ──
  settingsOpen: boolean;
  setSettingsOpen: (v: boolean) => void;

  // ── Notification ──
  notification: { msg: string; type: 'success' | 'error' | 'info'; key: number } | null;
  notify: (msg: string, type?: 'success' | 'error' | 'info') => void;

  // ── Confirm Dialog ──
  confirmDialog: {
    visible: boolean;
    message: string;
    title: string;
    resolve: ((v: boolean) => void) | null;
  };
  showConfirm: (message: string, resolve: (v: boolean) => void, title?: string) => void;
  closeConfirm: (result: boolean) => void;
}

export const useStore = create<AppState>()(
  persist(
    (set) => ({
  // Tree
  treeData: null,
  setTreeData: (data) => set({ treeData: data }),

  // Current paper
  currentPaper: null,
  setCurrentPaper: (paper) => set({ currentPaper: paper }),

  // PDF mode
  pdfMode: 'en',
  setPdfMode: (mode) => set({ pdfMode: mode }),

  // Image language
  imageLang: 'zh',
  setImageLang: (lang) => set({ imageLang: lang }),

  // Right tab
  rightTab: 'note',
  setRightTab: (tab) => set({ rightTab: tab }),

  // Notes (multi-note)
  notesList: [],
  setNotesList: (notes) => set({ notesList: notes }),
  currentNoteId: null,
  setCurrentNoteId: (id) => set({ currentNoteId: id }),
  isEditing: false,
  setIsEditing: (v) => set({ isEditing: v }),
  noteModified: false,
  setNoteModified: (v) => set({ noteModified: v }),
  originalNoteContent: '',
  setOriginalNoteContent: (c) => set({ originalNoteContent: c }),
  generatingNote: false,
  setGeneratingNote: (v) => set({ generatingNote: v }),
  generatingNotePaperId: null,
  setGeneratingNotePaperId: (id) => set({ generatingNotePaperId: id }),

  // Images (multi-image)
  imagesList: [],
  setImagesList: (images) => set({ imagesList: images }),
  currentImageId: null,
  setCurrentImageId: (id) => set({ currentImageId: id }),
  generatingImage: false,
  setGeneratingImage: (v) => set({ generatingImage: v }),
  generatingImagePaperId: null,
  setGeneratingImagePaperId: (id) => set({ generatingImagePaperId: id }),

  // Chat
  chatSessions: [],
  setChatSessions: (sessions) => set({ chatSessions: sessions }),
  currentChatSessionId: null,
  setCurrentChatSessionId: (id) => set({ currentChatSessionId: id }),
  chatStreaming: false,
  setChatStreaming: (v) => set({ chatStreaming: v }),
  noteModel: 'gemini-3.1-pro-preview',
  setNoteModel: (v) => set({ noteModel: v }),
  imageModel: 'gemini-3-pro-image-preview',
  setImageModel: (v) => set({ imageModel: v }),
  chatModel: 'gemini-3.1-pro-preview',
  setChatModel: (v) => set({ chatModel: v }),

  // Layout
  sidebarCollapsed: false,
  setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
  rightCollapsed: false,
  setRightCollapsed: (v) => set({ rightCollapsed: v }),
  preCompareLayout: null,
  setPreCompareLayout: (v) => set({ preCompareLayout: v }),

  // Context menu
  contextMenu: { visible: false, x: 0, y: 0, target: null, dirTarget: null },
  showContextMenu: (x, y, target, dirTarget = null) =>
    set({ contextMenu: { visible: true, x, y, target, dirTarget } }),
  hideContextMenu: () =>
    set((s) => ({ contextMenu: { ...s.contextMenu, visible: false, target: null, dirTarget: null } })),

  // Multi-select
  selectedItems: new Set<string>(),
  setSelectedItems: (items) => set({ selectedItems: items }),
  toggleSelectItem: (key, multi) =>
    set((s) => {
      const next = new Set(multi ? s.selectedItems : []);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return { selectedItems: next };
    }),
  clearSelection: () => set({ selectedItems: new Set<string>() }),

  // Inline rename
  renamingKey: null,
  setRenamingKey: (key) => set({ renamingKey: key }),

  // Drag-drop
  dragSource: null,
  setDragSource: (key) => set({ dragSource: key }),
  dropTarget: null,
  setDropTarget: (key) => set({ dropTarget: key }),

  // Modals
  importModalOpen: false,
  setImportModalOpen: (v) => set({ importModalOpen: v }),
  moveModalOpen: false,
  setMoveModalOpen: (v) => set({ moveModalOpen: v }),
  moveTargetId: null,
  setMoveTargetId: (v) => set({ moveTargetId: v }),
  moveTargetIds: [],
  setMoveTargetIds: (v) => set({ moveTargetIds: v }),
  moveFolderPath: null,
  setMoveFolderPath: (v) => set({ moveFolderPath: v }),
  moveTargetName: '',
  setMoveTargetName: (v) => set({ moveTargetName: v }),

  // Import
  importing: false,
  setImporting: (v) => set({ importing: v }),

  // Lightbox
  lightboxOpen: false,
  setLightboxOpen: (v) => set({ lightboxOpen: v }),

  // Settings
  settingsOpen: false,
  setSettingsOpen: (v) => set({ settingsOpen: v }),

  // Notification
  notification: null,
  notify: (msg, type = 'info') =>
    set({ notification: { msg, type, key: Date.now() } }),

  // Confirm Dialog
  confirmDialog: { visible: false, message: '', title: '确认', resolve: null },
  showConfirm: (message, resolve, title) =>
    set({ confirmDialog: { visible: true, message, title: title || '确认', resolve } }),
  closeConfirm: (result) =>
    set((s) => {
      s.confirmDialog.resolve?.(result);
      return { confirmDialog: { visible: false, message: '', title: '确认', resolve: null } };
    }),
}),
    {
      name: 'paper-reader:app-state',
      partialize: (state) => ({
        currentPaper: state.currentPaper,
        pdfMode: state.pdfMode,
        rightTab: state.rightTab,
        imageLang: state.imageLang,
        noteModel: state.noteModel,
        imageModel: state.imageModel,
        chatModel: state.chatModel,
        sidebarCollapsed: state.sidebarCollapsed,
        rightCollapsed: state.rightCollapsed,
      }),
    },
  ),
);
