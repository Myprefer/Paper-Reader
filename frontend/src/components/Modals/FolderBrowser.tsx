import { useState, useEffect, useCallback } from 'react';
import { useStore } from '../../store/useStore';
import { fetchFolders } from '../../api';
import type { FolderEntry } from '../../types';

interface FolderBrowserProps {
  currentPath: string;
  onNavigate: (path: string) => void;
  excludeFolder?: string | null;
}

export default function FolderBrowser({ currentPath, onNavigate, excludeFolder }: FolderBrowserProps) {
  const [children, setChildren] = useState<FolderEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    fetchFolders(currentPath)
      .then((data) => {
        const filtered = excludeFolder != null
          ? data.filter((c) => c.path !== excludeFolder)
          : data;
        setChildren(filtered);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [currentPath, excludeFolder]);

  // Breadcrumb
  const parts = currentPath ? currentPath.split('/') : [];

  return (
    <div className="folder-browser">
      <div className="folder-breadcrumb">
        <span
          className={`bc-item${parts.length === 0 ? ' bc-current' : ''}`}
          onClick={() => parts.length > 0 && onNavigate('')}
          style={{ cursor: parts.length > 0 ? 'pointer' : 'default' }}
        >
          📂 根目录
        </span>
        {parts.map((seg, i) => {
          const accumulated = parts.slice(0, i + 1).join('/');
          const isLast = i === parts.length - 1;
          return (
            <span key={accumulated}>
              <span className="bc-sep"> ▸ </span>
              <span
                className={`bc-item${isLast ? ' bc-current' : ''}`}
                onClick={() => !isLast && onNavigate(accumulated)}
                style={{ cursor: isLast ? 'default' : 'pointer' }}
              >
                {seg}
              </span>
            </span>
          );
        })}
      </div>
      <div className="folder-list">
        {loading && <div className="folder-empty">加载中…</div>}
        {error && <div className="folder-empty" style={{ color: '#f38ba8' }}>加载失败</div>}
        {!loading && !error && children.length === 0 && (
          <div className="folder-empty">当前目录下没有子文件夹</div>
        )}
        {!loading &&
          !error &&
          children.map((child) => (
            <div
              key={child.path}
              className="folder-item"
              onClick={() => onNavigate(child.path)}
            >
              <span className="folder-icon">📁</span> {child.name}
              {child.hasChildren && <span className="folder-arrow">▸</span>}
            </div>
          ))}
      </div>
    </div>
  );
}
