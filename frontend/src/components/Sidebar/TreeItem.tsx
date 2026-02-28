import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchTree, moveFolder, movePaper, renameFolder, renamePaper } from '../../api';
import { useConfirm } from '../../hooks/useConfirm';
import { useIsMobile } from '../../hooks/useIsMobile';
import { useLongPress } from '../../hooks/useLongPress';
import { useStore } from '../../store/useStore';
import type { DirNode, PaperNode, TreeNode } from '../../types';

interface TreeItemProps {
  node: TreeNode;
  depth: number;
  filter: string;
}

function normalizeSearchText(value: string | null | undefined): string {
  return (value || '').toLowerCase();
}

function matchesPaperFilter(node: PaperNode, filter: string): boolean {
  const keyword = normalizeSearchText(filter).trim();
  if (!keyword) return true;
  const haystack = [node.name, node.alias, node.aliasFullName]
    .map(normalizeSearchText)
    .join(' ');
  return haystack.includes(keyword);
}

export default function TreeItem({ node, depth, filter }: TreeItemProps) {
  const confirm = useConfirm();

  if (node.type === 'dir') {
    return <DirItem node={node} depth={depth} filter={filter} />;
  }

  return <FileItem node={node as PaperNode} depth={depth} filter={filter} confirm={confirm} />;
}

/*  File Item  */

interface FileItemProps {
  node: PaperNode;
  depth: number;
  filter: string;
  confirm: (msg: string, title?: string) => Promise<boolean>;
}

function FileItem({ node, depth, filter, confirm }: FileItemProps) {
  const {
    currentPaper, setCurrentPaper,
    isEditing, noteModified, setIsEditing, setNoteModified,
    showContextMenu,
    selectedItems, toggleSelectItem, clearSelection,
    renamingKey, setRenamingKey,
    setDragSource, setDropTarget,
    setSidebarCollapsed,
    setTreeData, notify,
  } = useStore();

  const isMobile = useIsMobile();

  const renameRef = useRef<HTMLInputElement>(null);
  const itemKey = `file:${node.id}`;
  const isRenaming = renamingKey === itemKey;
  const isSelected = selectedItems.has(itemKey);
  const filtered = !matchesPaperFilter(node, filter);

  const isActive = currentPaper?.id === node.id;

  // Long press → context menu (mobile)
  const longPress = useLongPress(
    useCallback((x: number, y: number) => {
      if (!isSelected || selectedItems.size <= 1) clearSelection();
      showContextMenu(x, y, node, null);
    }, [node, isSelected, selectedItems.size, clearSelection, showContextMenu]),
  );

  const handleClick = async (e: React.MouseEvent) => {
    if (isMobile && longPress.cancelClick()) return;
    if (isRenaming) return;

    // Multi-select with Ctrl (desktop only)
    if (!isMobile && (e.ctrlKey || e.metaKey)) {
      toggleSelectItem(itemKey, true);
      return;
    }

    if (isEditing && noteModified) {
      if (!(await confirm('当前笔记未保存，是否放弃更改？'))) return;
    }
    clearSelection();
    setIsEditing(false);
    setNoteModified(false);
    setCurrentPaper(node);
    document.title = node.name + ' - Paper Reader';
    // Mobile: auto-collapse sidebar after selecting a paper
    if (isMobile) setSidebarCollapsed(true);
  };

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // If this item is part of a multi-selection, preserve the selection
    if (!isSelected || selectedItems.size <= 1) {
      clearSelection();
    }
    showContextMenu(e.clientX, e.clientY, node, null);
  };

  // Drag handlers
  const handleDragStart = (e: React.DragEvent) => {
    // If dragging a selected item in multi-select, mark all for move
    if (isSelected && selectedItems.size > 1) {
      e.dataTransfer.setData('text/plain', '__multi__');
    } else {
      e.dataTransfer.setData('text/plain', itemKey);
    }
    e.dataTransfer.effectAllowed = 'move';
    setDragSource(itemKey);
  };

  const handleDragEnd = () => {
    setDragSource(null);
    setDropTarget(null);
  };

  // Inline rename
  const handleRenameSubmit = useCallback(async (newName: string) => {
    const trimmed = newName.trim();
    if (!trimmed || trimmed === node.name) {
      setRenamingKey(null);
      return;
    }
    try {
      await renamePaper(node.id, trimmed);
      notify('重命名成功', 'success');
      const data = await fetchTree();
      setTreeData(data);
    } catch (e: unknown) {
      notify((e as Error).message, 'error');
    }
    setRenamingKey(null);
  }, [node.id, node.name, setRenamingKey, notify, setTreeData]);

  useEffect(() => {
    if (isRenaming && renameRef.current) {
      renameRef.current.focus();
      renameRef.current.select();
    }
  }, [isRenaming]);

  const handleRenameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleRenameSubmit(e.currentTarget.value);
    } else if (e.key === 'Escape') {
      setRenamingKey(null);
    }
  };
  if (filtered) return null;
  return (
    <div className="tree-item">
      <div
        className={`tree-label${isActive ? ' active' : ''}${isSelected ? ' selected' : ''}`}
        style={{ paddingLeft: depth * 16 + 28 }}
        data-id={node.id}
        onClick={handleClick}
        onContextMenu={isMobile ? undefined : handleContextMenu}
        draggable={!isRenaming && !isMobile}
        onDragStart={isMobile ? undefined : handleDragStart}
        onDragEnd={isMobile ? undefined : handleDragEnd}
        {...(isMobile ? longPress.bindTouchProps() : {})}
      >
        <span className="tree-icon"></span>
        {isRenaming ? (
          <input
            ref={renameRef}
            className="tree-rename-input"
            defaultValue={node.name}
            onKeyDown={handleRenameKeyDown}
            onBlur={(e) => handleRenameSubmit(e.currentTarget.value)}
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span className="tree-name" title={node.name}>
            {[node.alias, node.aliasFullName, node.name].filter(Boolean).join(' - ')}
          </span>
        )}
        <span className="tree-badges">
          {(node.noteCount ?? 0) > 0 && (
            <span className="badge badge-note" title={`${node.noteCount} 笔记`}>N</span>
          )}
          {(node.hasImageZh || node.hasImageEn) && (
            <span className="badge badge-img" title={`${node.imageCount} 插图`}>I</span>
          )}
        </span>
      </div>
    </div>
  );
}

/*  Dir Item  */

function DirItem({ node, depth, filter }: { node: TreeNode; depth: number; filter: string }) {
  const {
    showContextMenu,
    selectedItems, toggleSelectItem, clearSelection,
    renamingKey, setRenamingKey,
    dragSource, setDragSource, dropTarget, setDropTarget,
    setTreeData, notify,
  } = useStore();

  const isMobile = useIsMobile();

  const [expanded, setExpanded] = useState(filter !== '' || depth < 1);
  const [creatingSubfolder, setCreatingSubfolder] = useState(false);
  const renameRef = useRef<HTMLInputElement>(null);
  const newFolderRef = useRef<HTMLInputElement>(null);

  const dirPath = node.path || '';
  const itemKey = `dir:${dirPath}`;
  const isRenaming = renamingKey === itemKey;
  const isSelected = selectedItems.has(itemKey);
  const isDragOver = dropTarget === dirPath;

  const children = node.children || [];

  useEffect(() => {
    if (filter) setExpanded(true);
  }, [filter]);

  // Listen for create-folder events targeting this directory
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.parent === dirPath) {
        setExpanded(true);
        setCreatingSubfolder(true);
      }
    };
    window.addEventListener('create-folder', handler);
    return () => window.removeEventListener('create-folder', handler);
  }, [dirPath]);

  useEffect(() => {
    if (creatingSubfolder && newFolderRef.current) {
      newFolderRef.current.focus();
    }
  }, [creatingSubfolder]);

  const handleNewSubfolderSubmit = useCallback(async (name: string) => {
    const trimmed = name.trim();
    setCreatingSubfolder(false);
    if (!trimmed) return;
    try {
      const { createFolder } = await import('../../api');
      await createFolder(dirPath, trimmed);
      notify('文件夹已创建', 'success');
      const data = await fetchTree();
      setTreeData(data);
    } catch (e: unknown) {
      notify((e as Error).message, 'error');
    }
  }, [dirPath, notify, setTreeData]);

  const handleNewSubfolderKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleNewSubfolderSubmit(e.currentTarget.value);
    } else if (e.key === 'Escape') {
      setCreatingSubfolder(false);
    }
  };

  const filteredChildren = useMemo(() => {
    if (!filter) return children;
    return children.filter((child) => {
      if (child.type === 'dir') return true;
      return matchesPaperFilter(child as PaperNode, filter);
    });
  }, [children, filter]);

  const hasVisibleChildren = useMemo(() => {
    if (!filter) return children.length > 0;
    return hasMatchingDescendant(node, filter);
  }, [node, filter, children]);

  const filteredDir = !!(filter && !hasVisibleChildren);

  // Long press → context menu (mobile)
  const longPress = useLongPress(
    useCallback((x: number, y: number) => {
      if (!isSelected || selectedItems.size <= 1) clearSelection();
      showContextMenu(x, y, null, node as DirNode);
    }, [node, isSelected, selectedItems.size, clearSelection, showContextMenu]),
  );

  const handleToggle = (e: React.MouseEvent) => {
    if (isMobile && longPress.cancelClick()) return;
    if (isRenaming) return;
    if (!isMobile && (e.ctrlKey || e.metaKey)) {
      toggleSelectItem(itemKey, true);
      return;
    }
    setExpanded(!expanded);
  };

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // If this item is part of a multi-selection, preserve the selection
    if (!isSelected || selectedItems.size <= 1) {
      clearSelection();
    }
    showContextMenu(e.clientX, e.clientY, null, node as DirNode);
  };

  // Drop target handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'move';
    setDropTarget(dirPath);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.stopPropagation();
    if (dropTarget === dirPath) setDropTarget(null);
  };

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDropTarget(null);

    const sourceKey = e.dataTransfer.getData('text/plain') || dragSource;
    if (!sourceKey) return;

    // Multi-select drag: move all selected papers
    if (sourceKey === '__multi__' && selectedItems.size > 0) {
      const paperKeys = Array.from(selectedItems).filter(k => k.startsWith('file:'));
      const folderKeys = Array.from(selectedItems).filter(k => k.startsWith('dir:'));
      if (paperKeys.length === 0 && folderKeys.length === 0) return;
      let errCount = 0;
      for (const key of paperKeys) {
        const pid = parseInt(key.slice(5));
        if (isNaN(pid)) continue;
        try { await movePaper(pid, dirPath); } catch { errCount++; }
      }
      for (const key of folderKeys) {
        const folderSrc = key.slice(4);
        if (folderSrc === dirPath || dirPath.startsWith(folderSrc + '/')) continue; // skip self/parent
        try { await moveFolder(folderSrc, dirPath); } catch { errCount++; }
      }
      clearSelection();
      const total = paperKeys.length + folderKeys.length;
      notify(errCount ? `移动完成，${errCount} 项失败` : `已移动 ${total} 项`, errCount ? 'error' : 'success');
      const data = await fetchTree();
      setTreeData(data);
      return;
    }

    // Single folder move
    if (sourceKey.startsWith('dir:')) {
      const srcFolder = sourceKey.slice(4);
      if (srcFolder === dirPath || dirPath.startsWith(srcFolder + '/')) return;
      try {
        await moveFolder(srcFolder, dirPath);
        notify('文件夹已移动', 'success');
        const data = await fetchTree();
        setTreeData(data);
      } catch (err: unknown) {
        notify((err as Error).message, 'error');
      }
      return;
    }

    // Single item move
    if (sourceKey.startsWith('file:')) {
      const paperId = parseInt(sourceKey.slice(5));
      if (isNaN(paperId)) return;
      try {
        await movePaper(paperId, dirPath);
        notify('移动成功', 'success');
        const data = await fetchTree();
        setTreeData(data);
      } catch (err: unknown) {
        notify((err as Error).message, 'error');
      }
    }
  }, [dirPath, dragSource, selectedItems, setDropTarget, clearSelection, notify, setTreeData]);

  // Drag folder itself
  const handleDirDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData('text/plain', itemKey);
    e.dataTransfer.effectAllowed = 'move';
    setDragSource(itemKey);
  };

  const handleDirDragEnd = () => {
    setDragSource(null);
    setDropTarget(null);
  };

  // Inline rename
  const handleRenameSubmit = useCallback(async (newName: string) => {
    const trimmed = newName.trim();
    if (!trimmed || trimmed === node.name) {
      setRenamingKey(null);
      return;
    }
    try {
      await renameFolder(dirPath, trimmed);
      notify('重命名成功', 'success');
      const data = await fetchTree();
      setTreeData(data);
    } catch (e: unknown) {
      notify((e as Error).message, 'error');
    }
    setRenamingKey(null);
  }, [dirPath, node.name, setRenamingKey, notify, setTreeData]);

  useEffect(() => {
    if (isRenaming && renameRef.current) {
      renameRef.current.focus();
      renameRef.current.select();
    }
  }, [isRenaming]);

  const handleRenameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleRenameSubmit(e.currentTarget.value);
    } else if (e.key === 'Escape') {
      setRenamingKey(null);
    }
  };
  if (filteredDir) return null;
  return (
    <div className="tree-item">
      <div
        className={`tree-label${isSelected ? ' selected' : ''}${isDragOver ? ' drag-over' : ''}`}
        style={{ paddingLeft: depth * 16 + 8 }}
        data-dir-path={dirPath}
        onClick={handleToggle}
        onContextMenu={isMobile ? undefined : handleContextMenu}
        draggable={!isRenaming && !isMobile}
        onDragStart={isMobile ? undefined : handleDirDragStart}
        onDragEnd={isMobile ? undefined : handleDirDragEnd}
        onDragOver={isMobile ? undefined : handleDragOver}
        onDragLeave={isMobile ? undefined : handleDragLeave}
        onDrop={isMobile ? undefined : handleDrop}
        {...(isMobile ? longPress.bindTouchProps() : {})}
      >
        <span className="tree-toggle">{expanded ? '' : ''}</span>
        <span className="tree-icon">{expanded ? '' : ''}</span>
        {isRenaming ? (
          <input
            ref={renameRef}
            className="tree-rename-input"
            defaultValue={node.name}
            onKeyDown={handleRenameKeyDown}
            onBlur={(e) => handleRenameSubmit(e.currentTarget.value)}
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span className="tree-name" title={node.path || node.name}>
            {node.name}
          </span>
        )}
      </div>
      {(expanded || creatingSubfolder) && (
        <div className="tree-children expanded">
          {creatingSubfolder && (
            <div className="tree-item">
              <div className="tree-label" style={{ paddingLeft: (depth + 1) * 16 + 8 }}>
                <span className="tree-icon">📁</span>
                <input
                  ref={newFolderRef}
                  className="tree-rename-input"
                  placeholder="新文件夹名称"
                  onKeyDown={handleNewSubfolderKeyDown}
                  onBlur={(e) => handleNewSubfolderSubmit(e.currentTarget.value)}
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
            </div>
          )}
          {filteredChildren.map((child, i) => (
            <TreeItem key={child.name + i} node={child} depth={depth + 1} filter={filter} />
          ))}
        </div>
      )}
    </div>
  );
}

function hasMatchingDescendant(node: TreeNode, filter: string): boolean {
  if (node.type === 'file') {
    return matchesPaperFilter(node as PaperNode, filter);
  }
  if (node.children) {
    return node.children.some((child) => hasMatchingDescendant(child, filter));
  }
  return false;
}