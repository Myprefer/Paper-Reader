// TypeScript 类型定义

/** 论文目录树节点 */
export interface TreeNode {
  type: 'dir' | 'file';
  name: string;
  /** 目录的相对路径（仅 dir 节点） */
  path?: string;
  /** 论文数据库 ID（仅 file 节点） */
  id?: number;
  children?: TreeNode[];
  /** 笔记数量 */
  noteCount?: number;
  /** 插图数量 */
  imageCount?: number;
  hasPdfZh?: boolean;
  hasImageEn?: boolean;
  hasImageZh?: boolean;
  /** 论文别名（缩写） */
  alias?: string | null;
  /** 别名全称 */
  aliasFullName?: string | null;
}

/** 当前选中的论文 */
export type PaperNode = TreeNode & {
  type: 'file';
  id: number;
};

/** PDF 显示模式 */
export type PdfMode = 'en' | 'zh' | 'compare';

/** 图片语言 */
export type ImageLang = 'en' | 'zh';

/** 右侧面板标签页 */
export type RightTab = 'note' | 'image' | 'chat';

/** 文件夹条目 */
export interface FolderEntry {
  name: string;
  path: string;
  hasChildren: boolean;
}

/** SSE 导入步骤数据 */
export interface ImportStepData {
  step: string;
  status: 'working' | 'done' | 'warn' | 'error' | 'skip';
  msg?: string;
  paper_id?: number;
}

/** 目录节点 */
export type DirNode = TreeNode & {
  type: 'dir';
  path: string;
};

/** 右键菜单状态 */
export interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  target: PaperNode | null;
  dirTarget: DirNode | null;
}

/** 对比模式前的布局状态 */
export interface PreCompareLayout {
  sidebarCollapsed: boolean;
  rightCollapsed: boolean;
}

/** 笔记列表项 */
export interface NoteItem {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

/** 插图列表项 */
export interface ImageItem {
  id: number;
  title: string;
  has_zh: boolean;
  created_at: string;
}

/** AI 对话会话 */
export interface ChatSession {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

/** AI 对话消息 */
export interface ChatMessage {
  id: number;
  role: 'user' | 'model';
  content: string;
  created_at: string;
}
