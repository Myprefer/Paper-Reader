import { useCallback, useEffect } from 'react';
import { useStore } from '../../store/useStore';

export default function ConfirmDialog() {
  const { confirmDialog, closeConfirm } = useStore();

  const handleConfirm = useCallback(() => closeConfirm(true), [closeConfirm]);
  const handleCancel = useCallback(() => closeConfirm(false), [closeConfirm]);

  // Esc 关闭
  useEffect(() => {
    if (!confirmDialog.visible) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleCancel();
      if (e.key === 'Enter') handleConfirm();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [confirmDialog.visible, handleCancel, handleConfirm]);

  if (!confirmDialog.visible) return null;

  return (
    <div className="confirm-overlay" onClick={handleCancel}>
      <div className="confirm-box" onClick={(e) => e.stopPropagation()}>
        <div className="confirm-title">
          <span className="confirm-icon">⚠️</span>
          {confirmDialog.title}
        </div>
        <div className="confirm-message">{confirmDialog.message}</div>
        <div className="confirm-actions">
          <button className="confirm-btn confirm-btn-cancel" onClick={handleCancel}>
            取消
          </button>
          <button className="confirm-btn confirm-btn-ok" onClick={handleConfirm} autoFocus>
            确定
          </button>
        </div>
      </div>
    </div>
  );
}
