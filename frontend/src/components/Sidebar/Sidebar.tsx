import { useCallback, useEffect, useRef, useState } from 'react';
import { createFolder, fetchTree, moveFolder, movePaper } from '../../api';
import { useIsMobile } from '../../hooks/useIsMobile';
import { useStore } from '../../store/useStore';
import type { PaperNode, TreeNode } from '../../types';
import TreeItem from './TreeItem';

/** 从树中按 ID 查找论文节点 */
function findPaperById(node: TreeNode, id: number): PaperNode | null {
  if (node.type === 'file' && node.id === id) return node as PaperNode;
  if (node.children) {
    for (const child of node.children) {
      const found = findPaperById(child, id);
      if (found) return found;
    }
  }
  return null;
}

export default function Sidebar() {
  const {
    treeData, setTreeData,
    currentPaper, setCurrentPaper,
    sidebarCollapsed, setSidebarCollapsed,
    setImportModalOpen,
    setSettingsOpen,
    selectedItems, clearSelection,
    notify,
  } = useStore();

  const isMobile = useIsMobile();

  const [creatingFolder, setCreatingFolder] = useState<{ parent: string } | null>(null);
  const newFolderRef = useRef<HTMLInputElement>(null);
  const restoredRef = useRef(false);

  const loadTree = useCallback(async () => {
    try {
      const data = await fetchTree();
      setTreeData(data);
    } catch (e) {
      console.error('loadTree error:', e);
    }
  }, [setTreeData]);

  useEffect(() => {
    loadTree();
  }, [loadTree]);

  // 树加载后恢复上次查看的论文
  useEffect(() => {
    if (!treeData || restoredRef.current) return;
    restoredRef.current = true;

    // currentPaper 已由 persist 中间件从 localStorage 恢复，
    // 但该对象引用可能已过时（如 noteCount 等字段），需从新树中重新获取
    const saved = currentPaper;
    if (saved?.id) {
      const fresh = findPaperById(treeData, saved.id);
      if (fresh) {
        setCurrentPaper(fresh);
        document.title = fresh.name + ' - Paper Reader';
      } else {
        // 论文已被删除
        setCurrentPaper(null);
      }
    }
  }, [treeData]);

  // Listen for create-folder events from context menu
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      setCreatingFolder({ parent: detail?.parent ?? '' });
    };
    window.addEventListener('create-folder', handler);
    return () => window.removeEventListener('create-folder', handler);
  }, []);

  useEffect(() => {
    if (creatingFolder && newFolderRef.current) {
      newFolderRef.current.focus();
    }
  }, [creatingFolder]);

  const handleNewFolderSubmit = useCallback(async (name: string) => {
    const trimmed = name.trim();
    if (!trimmed) {
      setCreatingFolder(null);
      return;
    }
    try {
      await createFolder(creatingFolder?.parent ?? '', trimmed);
      notify('文件夹已创建', 'success');
      loadTree();
    } catch (e: unknown) {
      notify((e as Error).message, 'error');
    }
    setCreatingFolder(null);
  }, [creatingFolder, notify, loadTree]);

  const handleNewFolderKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleNewFolderSubmit(e.currentTarget.value);
    } else if (e.key === 'Escape') {
      setCreatingFolder(null);
    }
  };

  const handleSidebarClick = (e: React.MouseEvent) => {
    // Click on empty area to clear selection
    if ((e.target as HTMLElement).id === 'tree-container' ||
        (e.target as HTMLElement).id === 'sidebar') {
      clearSelection();
    }
  };

  const handleNewRootFolder = () => {
    setCreatingFolder({ parent: '' });
  };

  // Drop on root tree container
  const handleRootDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleRootDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    const sourceKey = e.dataTransfer.getData('text/plain');

    // Multi-select drag: move all selected papers to root
    if (sourceKey === '__multi__' && selectedItems.size > 0) {
      const paperKeys = Array.from(selectedItems).filter(k => k.startsWith('file:'));
      if (paperKeys.length === 0) return;
      let errCount = 0;
      for (const key of paperKeys) {
        const pid = parseInt(key.slice(5));
        if (isNaN(pid)) continue;
        try { await movePaper(pid, ''); } catch { errCount++; }
      }
      clearSelection();
      notify(errCount ? `移动完成，${errCount} 项失败` : `已移动 ${paperKeys.length} 篇论文到根目录`, errCount ? 'error' : 'success');
      loadTree();
      return;
    }

    if (sourceKey?.startsWith('dir:')) {
      const srcPath = sourceKey.slice(4);
      if (srcPath) {
        try {
          await moveFolder(srcPath, '');
          notify('已移动文件夹到根目录', 'success');
          loadTree();
        } catch (err: unknown) {
          notify((err as Error).message, 'error');
        }
      }
      return;
    }

    if (sourceKey?.startsWith('file:')) {
      const paperId = parseInt(sourceKey.slice(5));
      if (!isNaN(paperId)) {
        try {
          await movePaper(paperId, '');
          notify('已移动到根目录', 'success');
          loadTree();
        } catch (err: unknown) {
          notify((err as Error).message, 'error');
        }
      }
    }
  }, [selectedItems, clearSelection, notify, loadTree]);

  return (
    <div
      id="sidebar"
      className={sidebarCollapsed ? 'collapsed' : ''}
      style={!isMobile && sidebarCollapsed ? { marginLeft: '-300px' } : undefined}
      onClick={handleSidebarClick}
    >
      <div id="sidebar-header">
        <button
          className="mobile-close-btn"
          onClick={() => setSidebarCollapsed(true)}
          title="关闭"
        >
          ←
        </button>
        <span className="sidebar-title"> Paper Reader</span>
        <div className="sidebar-actions">
          <button
            className="sidebar-btn"
            onClick={handleNewRootFolder}
            title="新建文件夹"
          >
            +
          </button>
          <button
            id="btn-import-paper"
            onClick={() => setImportModalOpen(true)}
            title="导入论文（arXiv 或本地文件）"
          >
             导入
          </button>
          <button
            className="sidebar-btn"
            onClick={() => setSettingsOpen(true)}
            title="设置"
          >
            ⚙️
          </button>
        </div>
      </div>
      <SearchBox />
      <TreeContainer
        treeData={treeData}
        creatingFolder={creatingFolder}
        newFolderRef={newFolderRef}
        onNewFolderKeyDown={handleNewFolderKeyDown}
        onNewFolderBlur={(e) => handleNewFolderSubmit(e.currentTarget.value)}
        onRootDragOver={isMobile ? undefined : handleRootDragOver}
        onRootDrop={isMobile ? undefined : handleRootDrop}
      />
    </div>
  );
}

function SearchBox() {
  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    window.dispatchEvent(new CustomEvent('paper-search', { detail: value }));
  }, []);

  return (
    <div id="search-box">
      <input
        type="text"
        id="search-input"
        placeholder="搜索论文名称 / 别名"
        onChange={handleChange}
      />
    </div>
  );
}

interface TreeContainerProps {
  treeData: TreeNode | null;
  creatingFolder: { parent: string } | null;
  newFolderRef: React.RefObject<HTMLInputElement | null>;
  onNewFolderKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  onNewFolderBlur: (e: React.FocusEvent<HTMLInputElement>) => void;
  onRootDragOver?: (e: React.DragEvent) => void;
  onRootDrop?: (e: React.DragEvent) => void;
}

function TreeContainer({
  treeData,
  creatingFolder,
  newFolderRef,
  onNewFolderKeyDown,
  onNewFolderBlur,
  onRootDragOver,
  onRootDrop,
}: TreeContainerProps) {
  const [filter, setFilter] = useState('');

  useEffect(() => {
    const handler = (e: Event) => {
      setFilter((e as CustomEvent).detail || '');
    };
    window.addEventListener('paper-search', handler);
    return () => window.removeEventListener('paper-search', handler);
  }, []);

  if (!treeData) {
    return (
      <div id="tree-container">
        <div style={{ padding: 16, color: '#6c7086' }}>加载中</div>
      </div>
    );
  }

  const children = treeData.children || [];
  const showNewFolder = creatingFolder && creatingFolder.parent === '';

  return (
    <div
      id="tree-container"
      onDragOver={onRootDragOver}
      onDrop={onRootDrop}
    >
      {showNewFolder && (
        <div className="tree-item">
          <div className="tree-label" style={{ paddingLeft: 8 }}>
            <span className="tree-icon"></span>
            <input
              ref={newFolderRef}
              className="tree-rename-input"
              placeholder="新文件夹名称"
              onKeyDown={onNewFolderKeyDown}
              onBlur={onNewFolderBlur}
            />
          </div>
        </div>
      )}
      {children.map((child, i) => (
        <TreeItem key={child.name + i} node={child} depth={0} filter={filter} />
      ))}
    </div>
  );
}