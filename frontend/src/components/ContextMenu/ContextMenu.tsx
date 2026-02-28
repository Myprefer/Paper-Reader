import { useCallback, useEffect, useMemo } from 'react';
import { deleteFolder, deletePaper, extractAlias, fetchTree } from '../../api';
import { useConfirm } from '../../hooks/useConfirm';
import { useIsMobile } from '../../hooks/useIsMobile';
import { useStore } from '../../store/useStore';

export default function ContextMenu() {
  const {
    contextMenu,
    hideContextMenu,
    setMoveModalOpen,
    setMoveTargetId,
    setMoveTargetIds,
    setMoveTargetName,
    setRenamingKey,
    setTreeData,
    currentPaper,
    setCurrentPaper,
    selectedItems,
    clearSelection,
    notify,
  } = useStore();

  const confirm = useConfirm();
  const isMobile = useIsMobile();

  // Click outside to close
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!(e.target as HTMLElement)?.closest('#ctx-menu')) {
        hideContextMenu();
      }
    };
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, [hideContextMenu]);

  // Right-click outside tree labels to close
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!(e.target as HTMLElement)?.closest('.tree-label[data-id]') &&
          !(e.target as HTMLElement)?.closest('.tree-label[data-dir-path]')) {
        hideContextMenu();
      }
    };
    document.addEventListener('contextmenu', handler);
    return () => document.removeEventListener('contextmenu', handler);
  }, [hideContextMenu]);

  const refreshTree = useCallback(async () => {
    try {
      const data = await fetchTree();
      setTreeData(data);
    } catch { /* ignore */ }
  }, [setTreeData]);

  // Paper actions

  const handleMove = useCallback(() => {
    const target = contextMenu.target;
    if (!target) return;
    hideContextMenu();
    setMoveTargetId(target.id);
    setMoveTargetIds([]);
    setMoveTargetName(target.name);
    setMoveModalOpen(true);
  }, [contextMenu.target, hideContextMenu, setMoveModalOpen, setMoveTargetId, setMoveTargetIds, setMoveTargetName]);

  const handleRenamePaper = useCallback(() => {
    const target = contextMenu.target;
    if (!target) return;
    hideContextMenu();
    setRenamingKey(`file:${target.id}`);
  }, [contextMenu.target, hideContextMenu, setRenamingKey]);

  const handleDeletePaper = useCallback(async () => {
    const target = contextMenu.target;
    if (!target) return;
    hideContextMenu();
    if (!(await confirm(`确定删除论文「${target.name}」及其所有关联文件？`, '删除论文'))) return;
    try {
      await deletePaper(target.id);
      if (currentPaper?.id === target.id) {
        setCurrentPaper(null);
      }
      notify('论文已删除', 'success');
      refreshTree();
    } catch (e: unknown) {
      notify((e as Error).message, 'error');
    }
  }, [contextMenu.target, hideContextMenu, confirm, currentPaper, setCurrentPaper, notify, refreshTree]);

  const handleExtractAlias = useCallback(async () => {
    const target = contextMenu.target;
    if (!target) return;
    hideContextMenu();
    notify('正在提取别名…', 'info');
    try {
      const result = await extractAlias(target.id);
      if (result.status === 'ok') {
        const aliasText = [result.alias, result.alias_full].filter(Boolean).join(' - ');
        notify(aliasText ? `别名提取完成：${aliasText}` : '别名提取完成', 'success');
      } else {
        notify('未检测到可用别名', 'info');
      }
      refreshTree();
    } catch (e: unknown) {
      notify((e as Error).message, 'error');
    }
  }, [contextMenu.target, hideContextMenu, notify, refreshTree]);

  // Folder actions

  const handleRenameFolder = useCallback(() => {
    const dir = contextMenu.dirTarget;
    if (!dir) return;
    hideContextMenu();
    setRenamingKey(`dir:${dir.path}`);
  }, [contextMenu.dirTarget, hideContextMenu, setRenamingKey]);

  const handleDeleteFolder = useCallback(async () => {
    const dir = contextMenu.dirTarget;
    if (!dir) return;
    hideContextMenu();
    if (!(await confirm(`确定删除文件夹「${dir.name}」及其中所有论文？`, '删除文件夹'))) return;
    try {
      await deleteFolder(dir.path!);
      notify('文件夹已删除', 'success');
      refreshTree();
    } catch (e: unknown) {
      notify((e as Error).message, 'error');
    }
  }, [contextMenu.dirTarget, hideContextMenu, confirm, notify, refreshTree]);

  const handleNewSubfolder = useCallback(() => {
    const dir = contextMenu.dirTarget;
    if (!dir) return;
    hideContextMenu();
    window.dispatchEvent(new CustomEvent('create-folder', { detail: { parent: dir.path } }));
  }, [contextMenu.dirTarget, hideContextMenu]);

  const handleMoveFolder = useCallback(() => {
    const dir = contextMenu.dirTarget;
    if (!dir) return;
    hideContextMenu();
    setMoveTargetId(null);
    setMoveTargetIds([]);
    setMoveTargetName(dir.name);
    // Store folder path in moveTargetIds as a special marker
    // We'll use a negative convention: store in a separate state
    useStore.setState({ moveFolderPath: dir.path || '' });
    setMoveModalOpen(true);
  }, [contextMenu.dirTarget, hideContextMenu, setMoveTargetId, setMoveTargetIds, setMoveTargetName, setMoveModalOpen]);

  // ── Batch operations ──

  const handleBatchDelete = useCallback(async () => {
    const items = Array.from(selectedItems);
    hideContextMenu();
    if (!(await confirm(`确定删除选中的 ${items.length} 项？此操作不可撤销。`, '批量删除'))) return;
    const paperIds = items.filter(k => k.startsWith('file:')).map(k => parseInt(k.slice(5)));
    // Sort folder paths deepest first to avoid parent-before-child issues
    const folderPaths = items.filter(k => k.startsWith('dir:')).map(k => k.slice(4))
      .sort((a, b) => b.split('/').length - a.split('/').length);
    let errCount = 0;
    for (const id of paperIds) {
      try {
        await deletePaper(id);
        if (currentPaper?.id === id) setCurrentPaper(null);
      } catch { errCount++; }
    }
    for (const p of folderPaths) {
      try { await deleteFolder(p); } catch { errCount++; }
    }
    clearSelection();
    notify(errCount ? `删除完成，${errCount} 项失败` : `已删除 ${items.length} 项`, errCount ? 'error' : 'success');
    refreshTree();
  }, [selectedItems, hideContextMenu, confirm, currentPaper, setCurrentPaper, clearSelection, notify, refreshTree]);

  const handleBatchMove = useCallback(() => {
    const paperIds = Array.from(selectedItems)
      .filter(k => k.startsWith('file:'))
      .map(k => parseInt(k.slice(5)));
    if (paperIds.length === 0) return;
    hideContextMenu();
    setMoveTargetIds(paperIds);
    setMoveTargetName(`${paperIds.length} 篇论文`);
    setMoveModalOpen(true);
  }, [selectedItems, hideContextMenu, setMoveTargetIds, setMoveTargetName, setMoveModalOpen]);

  // On mobile, clamp menu position to stay within viewport
  // NOTE: useMemo must be called before any early return to respect Rules of Hooks
  const menuPos = useMemo(() => {
    let x = contextMenu.x;
    let y = contextMenu.y;
    if (isMobile) {
      x = Math.max(8, Math.min(x, window.innerWidth - 180));
      y = Math.max(8, Math.min(y, window.innerHeight - 220));
    }
    return { x, y };
  }, [contextMenu.x, contextMenu.y, isMobile]);

  if (!contextMenu.visible) return null;

  const isMulti = selectedItems.size > 1;
  const hasPaper = !!contextMenu.target;
  const hasDir = !!contextMenu.dirTarget;
  const multiHasPapers = isMulti && Array.from(selectedItems).some(k => k.startsWith('file:'));

  return (
    <div
      id="ctx-menu"
      className="ctx-menu show"
      style={{ left: menuPos.x, top: menuPos.y }}
    >
      {isMulti ? (
        <>
          {multiHasPapers && (
            <div className="ctx-menu-item" onClick={handleBatchMove}>
              <span className="ctx-icon"></span> 批量移动 ({selectedItems.size} 项)
            </div>
          )}
          <div className="ctx-menu-item ctx-menu-danger" onClick={handleBatchDelete}>
            <span className="ctx-icon"></span> 批量删除 ({selectedItems.size} 项)
          </div>
        </>
      ) : (
        <>
          {hasPaper && (
            <>
              <div className="ctx-menu-item" onClick={handleRenamePaper}>
                <span className="ctx-icon"></span> 重命名
              </div>
              <div className="ctx-menu-item" onClick={handleMove}>
                <span className="ctx-icon"></span> 移动到
              </div>
              <div className="ctx-menu-item" onClick={handleExtractAlias}>
                <span className="ctx-icon"></span> 提取别名
              </div>
              <div className="ctx-menu-item ctx-menu-danger" onClick={handleDeletePaper}>
                <span className="ctx-icon"></span> 删除论文
              </div>
            </>
          )}
          {hasDir && (
            <>
              <div className="ctx-menu-item" onClick={handleNewSubfolder}>
                <span className="ctx-icon"></span> 新建子文件夹
              </div>
              <div className="ctx-menu-item" onClick={handleRenameFolder}>
                <span className="ctx-icon"></span> 重命名
              </div>
              <div className="ctx-menu-item" onClick={handleMoveFolder}>
                <span className="ctx-icon"></span> 移动到
              </div>
              <div className="ctx-menu-item ctx-menu-danger" onClick={handleDeleteFolder}>
                <span className="ctx-icon"></span> 删除文件夹
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
