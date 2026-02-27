import { useCallback, useEffect, useState } from 'react';
import { fetchTree, moveFolder, movePaper } from '../../api';
import { useStore } from '../../store/useStore';
import type { PaperNode } from '../../types';
import { findNodeById } from '../../utils/helpers';
import FolderBrowser from './FolderBrowser';

export default function MoveModal() {
  const {
    moveModalOpen,
    setMoveModalOpen,
    moveTargetId,
    setMoveTargetId,
    moveTargetIds,
    setMoveTargetIds,
    moveFolderPath,
    setMoveFolderPath,
    moveTargetName,
    currentPaper,
    setCurrentPaper,
    setTreeData,
    clearSelection,
    notify,
  } = useStore();

  const [folderPath, setFolderPath] = useState('');
  const [moving, setMoving] = useState(false);

  useEffect(() => {
    if (moveModalOpen) {
      setFolderPath('');
    }
  }, [moveModalOpen]);

  const close = useCallback(() => {
    setMoveModalOpen(false);
    setMoveTargetId(null);
    setMoveTargetIds([]);
    setMoveFolderPath(null);
  }, [setMoveModalOpen, setMoveTargetId, setMoveTargetIds, setMoveFolderPath]);

  const handleConfirm = useCallback(async () => {
    setMoving(true);
    try {
      // Folder move
      if (moveFolderPath !== null) {
        await moveFolder(moveFolderPath, folderPath);
        close();
        clearSelection();
        notify('文件夹已移动', 'success');
        const tree = await fetchTree();
        setTreeData(tree);
        return;
      }

      // Paper move (single or batch)
      const ids = moveTargetIds.length > 0 ? moveTargetIds : moveTargetId ? [moveTargetId] : [];
      if (ids.length === 0) return;

      let errCount = 0;
      for (const id of ids) {
        try {
          await movePaper(id, folderPath);
        } catch { errCount++; }
      }
      close();
      clearSelection();
      if (errCount) {
        notify(`移动完成，${errCount} 项失败`, 'error');
      } else {
        notify(ids.length > 1 ? `已移动 ${ids.length} 篇论文` : '论文已移动', 'success');
      }

      // Reload tree
      const tree = await fetchTree();
      setTreeData(tree);

      // If the moved paper was selected, update the selection
      if (currentPaper && ids.includes(currentPaper.id)) {
        const node = findNodeById(tree, currentPaper.id);
        if (node && node.type === 'file') {
          setCurrentPaper(node as PaperNode);
        }
      }
    } catch (e: any) {
      notify('移动失败: ' + e.message, 'error');
    } finally {
      setMoving(false);
    }
  }, [moveTargetId, moveTargetIds, moveFolderPath, folderPath, currentPaper, close, clearSelection, notify, setTreeData, setCurrentPaper]);

  if (!moveModalOpen) return null;

  return (
    <div
      className="modal-backdrop show"
      onClick={(e) => e.target === e.currentTarget && close()}
    >
      <div className="modal-box">
        <div className="modal-title">📁 {moveFolderPath !== null ? '移动文件夹' : '移动论文'}</div>
        <div className="modal-field">
          <label>{moveFolderPath !== null ? '📂' : '📄'} {moveTargetName}</label>
        </div>
        <div className="modal-field">
          <label>选择目标文件夹</label>
          <FolderBrowser
            currentPath={folderPath}
            onNavigate={setFolderPath}
          />
        </div>
        <div className="modal-actions">
          <button className="modal-btn modal-btn-cancel" onClick={close}>
            取消
          </button>
          <button
            className="modal-btn modal-btn-primary"
            disabled={moving}
            onClick={handleConfirm}
          >
            {moving ? '移动中…' : '移动'}
          </button>
        </div>
      </div>
    </div>
  );
}
