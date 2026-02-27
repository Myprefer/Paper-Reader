import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchTree, importPaperStream, uploadPaper } from '../../api';
import { useStore } from '../../store/useStore';
import type { PaperNode } from '../../types';
import { findNodeById } from '../../utils/helpers';
import FolderBrowser from './FolderBrowser';

type ImportMode = 'arxiv' | 'manual';

const STEP_LABELS: Record<string, string> = {
  title: '获取论文信息',
  pdf_en: '下载原文 PDF',
  alias: '提取论文别名',
  pdf_zh: '获取中文翻译 PDF',
  note: '生成笔记',
  image: '生成插图',
  finish: '导入完成',
};

const STEP_ICONS: Record<string, string> = {
  working: '⏳',
  done: '✅',
  warn: '⚠️',
  error: '❌',
  skip: '⏭️',
};

interface ImportStep {
  step: string;
  status: string;
  msg?: string;
}

export default function ImportModal() {
  const {
    importModalOpen,
    setImportModalOpen,
    importing,
    setImporting,
    setTreeData,
    setCurrentPaper,
    notify,
  } = useStore();

  const [mode, setMode] = useState<ImportMode>('arxiv');
  const [arxivId, setArxivId] = useState('');
  const [folderPath, setFolderPath] = useState('');
  const [steps, setSteps] = useState<ImportStep[]>([]);
  const [showForm, setShowForm] = useState(true);
  const [showDone, setShowDone] = useState(false);
  const importedPaperIdRef = useRef<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Manual mode state
  const [manualFile, setManualFile] = useState<File | null>(null);
  const [manualFileZh, setManualFileZh] = useState<File | null>(null);
  const [manualTitle, setManualTitle] = useState('');
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const fileZhInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (importModalOpen) {
      setArxivId('');
      setFolderPath('');
      setSteps([]);
      setShowForm(true);
      setShowDone(false);
      setManualFile(null);
      setManualFileZh(null);
      setManualTitle('');
      setDragging(false);
      importedPaperIdRef.current = null;
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [importModalOpen]);

  const close = useCallback(() => {
    if (!importing) setImportModalOpen(false);
  }, [importing, setImportModalOpen]);

  const upsertStep = useCallback((step: string, status: string, msg?: string) => {
    setSteps((prev) => {
      const idx = prev.findIndex((s) => s.step === step);
      const entry: ImportStep = { step, status, msg };
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = entry;
        return next;
      }
      return [...prev, entry];
    });
  }, []);

  // Reload tree and select the imported paper
  const reloadAndSelect = useCallback(async () => {
    try {
      const tree = await fetchTree();
      setTreeData(tree);
      if (importedPaperIdRef.current) {
        const node = findNodeById(tree, importedPaperIdRef.current);
        if (node && node.type === 'file') {
          setCurrentPaper(node as PaperNode);
          document.title = node.name + ' - PaperReader';
        }
      }
    } catch {
      // ignore
    }
  }, [setTreeData, setCurrentPaper]);

  // arXiv import handler
  const handleArxivStart = useCallback(async () => {
    if (!arxivId.trim()) {
      notify('请输入 arXiv ID', 'error');
      return;
    }

    setImporting(true);
    setShowForm(false);
    setSteps([]);
    setShowDone(false);
    importedPaperIdRef.current = null;

    // Track whether modal was closed early after PDF ready
    let closedEarly = false;

    try {
      await importPaperStream(arxivId.trim(), folderPath, (data) => {
        // Update progress UI (no-op after unmount, which is fine)
        upsertStep(data.step, data.status, data.msg);

        // When paper_id arrives (PDF downloaded + DB registered), close modal early
        if (data.paper_id && !closedEarly) {
          closedEarly = true;
          importedPaperIdRef.current = data.paper_id;
          setImporting(false);
          setImportModalOpen(false);
          reloadAndSelect();
        }
      });
      if (closedEarly) {
        // Background processing finished, refresh tree for updated badges
        notify('后台处理完成（笔记/插图/翻译）', 'success');
        reloadAndSelect();
      } else {
        // Fallback: stream ended without early close (e.g. error before DB registration)
        notify('论文导入完成！', 'success');
        setImporting(false);
        setShowDone(true);
        await reloadAndSelect();
      }
    } catch (e: any) {
      if (!closedEarly) {
        upsertStep('finish', 'error', '导入失败: ' + e.message);
        notify('导入失败: ' + e.message, 'error');
        setImporting(false);
        setShowDone(true);
      } else {
        // Error during background processing
        notify('后台处理出错: ' + (e as Error).message, 'error');
      }
    }
  }, [arxivId, folderPath, setImporting, setImportModalOpen, upsertStep, notify, reloadAndSelect]);

  // Manual upload handler
  const handleManualStart = useCallback(async () => {
    if (!manualFile) {
      notify('请选择 PDF 文件', 'error');
      return;
    }

    setImporting(true);
    setShowForm(false);
    setSteps([]);
    setShowDone(false);
    importedPaperIdRef.current = null;

    upsertStep('upload', 'working', '正在上传论文…');

    try {
      const result = await uploadPaper(
        manualFile,
        folderPath,
        manualTitle || undefined,
        manualFileZh || undefined,
      );
      importedPaperIdRef.current = result.paper_id ?? null;
      upsertStep('upload', 'done', `论文上传成功: ${result.title}`);
      if (manualFileZh) {
        upsertStep('upload_zh', 'done', '中文 PDF 已上传');
      }
      upsertStep('finish', 'done', '导入完成！');
      notify('论文导入完成！', 'success');
    } catch (e: any) {
      upsertStep('upload', 'error', '上传失败: ' + e.message);
      notify('上传失败: ' + e.message, 'error');
    } finally {
      setImporting(false);
      setShowDone(true);
    }

    await reloadAndSelect();
  }, [manualFile, manualFileZh, manualTitle, folderPath, setImporting, upsertStep, notify, reloadAndSelect]);

  const handleStart = mode === 'arxiv' ? handleArxivStart : handleManualStart;

  // Drag-and-drop handlers for manual mode
  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(true);
  };
  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(false);
  };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const pdfFiles = Array.from(files).filter((f) =>
        f.name.toLowerCase().endsWith('.pdf'),
      );
      if (pdfFiles.length === 0) {
        notify('仅支持 PDF 文件', 'error');
        return;
      }
      setManualFile(pdfFiles[0]);
      if (!manualTitle) {
        setManualTitle(pdfFiles[0].name.replace(/\.pdf$/i, ''));
      }
      // If two PDFs dropped, treat second as Chinese version
      if (pdfFiles.length >= 2) {
        setManualFileZh(pdfFiles[1]);
      }
    }
  };

  if (!importModalOpen) return null;

  return (
    <div
      className="modal-backdrop show"
      onClick={(e) => e.target === e.currentTarget && close()}
    >
      <div className="modal-box" style={{ maxWidth: 520 }}>
        <div className="modal-title">📥 导入论文</div>

        {showForm && (
          <div>
            {/* Mode tabs */}
            <div className="import-mode-tabs">
              <button
                className={`import-mode-tab${mode === 'arxiv' ? ' active' : ''}`}
                onClick={() => setMode('arxiv')}
              >
                arXiv 导入
              </button>
              <button
                className={`import-mode-tab${mode === 'manual' ? ' active' : ''}`}
                onClick={() => setMode('manual')}
              >
                手动导入
              </button>
            </div>

            {mode === 'arxiv' ? (
              /* arXiv mode */
              <div>
                <div className="modal-field">
                  <label>arXiv ID 或链接</label>
                  <input
                    ref={inputRef}
                    type="text"
                    placeholder="例如: 2406.12345 或 https://arxiv.org/abs/2406.12345"
                    value={arxivId}
                    onChange={(e) => setArxivId(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleStart()}
                  />
                </div>
              </div>
            ) : (
              /* Manual mode */
              <div>
                <div className="modal-field">
                  <label>论文 PDF（必选）</label>
                  <div
                    className={`drop-zone${dragging ? ' drag-over' : ''}${manualFile ? ' has-file' : ''}`}
                    onDragOver={onDragOver}
                    onDragLeave={onDragLeave}
                    onDrop={onDrop}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    {manualFile ? (
                      <div className="drop-zone-file">
                        <span className="drop-zone-icon">📄</span>
                        <span className="drop-zone-name">{manualFile.name}</span>
                        <span className="drop-zone-size">
                          ({(manualFile.size / 1024).toFixed(0)} KB)
                        </span>
                        <button
                          className="drop-zone-remove"
                          onClick={(e) => {
                            e.stopPropagation();
                            setManualFile(null);
                          }}
                        >
                          ✕
                        </button>
                      </div>
                    ) : (
                      <div className="drop-zone-placeholder">
                        <span className="drop-zone-icon">📂</span>
                        <span>拖拽 PDF 文件到此处，或点击选择</span>
                      </div>
                    )}
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf"
                      style={{ display: 'none' }}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          setManualFile(file);
                          if (!manualTitle) {
                            setManualTitle(file.name.replace(/\.pdf$/i, ''));
                          }
                        }
                        e.target.value = '';
                      }}
                    />
                  </div>
                </div>

                <div className="modal-field">
                  <label>中文 PDF（可选）</label>
                  <div
                    className={`drop-zone drop-zone-sm${manualFileZh ? ' has-file' : ''}`}
                    onClick={() => fileZhInputRef.current?.click()}
                  >
                    {manualFileZh ? (
                      <div className="drop-zone-file">
                        <span className="drop-zone-icon">📄</span>
                        <span className="drop-zone-name">{manualFileZh.name}</span>
                        <button
                          className="drop-zone-remove"
                          onClick={(e) => {
                            e.stopPropagation();
                            setManualFileZh(null);
                          }}
                        >
                          ✕
                        </button>
                      </div>
                    ) : (
                      <div className="drop-zone-placeholder">
                        <span>点击选择中文 PDF（可稍后上传）</span>
                      </div>
                    )}
                    <input
                      ref={fileZhInputRef}
                      type="file"
                      accept=".pdf"
                      style={{ display: 'none' }}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) setManualFileZh(file);
                        e.target.value = '';
                      }}
                    />
                  </div>
                </div>

                <div className="modal-field">
                  <label>论文标题（可选，默认取文件名）</label>
                  <input
                    type="text"
                    placeholder="留空则使用文件名作为标题"
                    value={manualTitle}
                    onChange={(e) => setManualTitle(e.target.value)}
                  />
                </div>
              </div>
            )}

            {/* Shared: folder selector */}
            <div className="modal-field">
              <label>保存到文件夹</label>
              <FolderBrowser
                currentPath={folderPath}
                onNavigate={setFolderPath}
              />
            </div>
            <div className="modal-actions">
              <button className="modal-btn modal-btn-cancel" onClick={close}>
                取消
              </button>
              <button className="modal-btn modal-btn-primary" onClick={handleStart}>
                开始导入
              </button>
            </div>
          </div>
        )}

        {/* Progress */}
        {steps.length > 0 && (
          <div className={`import-progress${!showForm ? ' active' : ''}`} style={{ display: !showForm ? 'block' : 'none' }}>
            {steps.map((s) => (
              <div key={s.step} className={`import-step ${s.status}`}>
                <span className="step-icon">
                  {s.status === 'working' ? (
                    <div className="step-spinner" />
                  ) : (
                    STEP_ICONS[s.status] || '⏳'
                  )}
                </span>
                <span>{s.msg || STEP_LABELS[s.step] || s.step}</span>
              </div>
            ))}
          </div>
        )}

        {showDone && (
          <div className="modal-actions">
            <button className="modal-btn modal-btn-primary" onClick={close}>
              完成
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
