import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchZhPdf as apiFetchZhPdf, checkPdfExists, pdfUrl, uploadZhPdf } from '../../api';
import { loadPdfPage, savePdfPage, useStore } from '../../store/useStore';
import type { PdfMode } from '../../types';

export default function PDFPanel() {
  const {
    currentPaper,
    pdfMode,
    setPdfMode,
    sidebarCollapsed,
    setSidebarCollapsed,
    rightCollapsed,
    setRightCollapsed,
    preCompareLayout,
    setPreCompareLayout,
    notify,
  } = useStore();

  const isCompare = pdfMode === 'compare';

  const handleModeChange = useCallback(
    (mode: PdfMode) => {
      if (mode === pdfMode) return;

      if (mode === 'compare') {
        // Save current layout before entering compare
        setPreCompareLayout({
          sidebarCollapsed,
          rightCollapsed,
        });
      } else if (pdfMode === 'compare' && preCompareLayout) {
        // Restore layout when leaving compare
        setSidebarCollapsed(preCompareLayout.sidebarCollapsed);
        setRightCollapsed(preCompareLayout.rightCollapsed);
        setPreCompareLayout(null);
      }

      setPdfMode(mode);
    },
    [pdfMode, sidebarCollapsed, rightCollapsed, preCompareLayout,
     setPdfMode, setPreCompareLayout, setSidebarCollapsed, setRightCollapsed],
  );

  return (
    <div id="pdf-panel">
      {/* Floating overlay controls */}
      <div id="pdf-overlay">
        <div className="ov-left">
          <button
            className={`ov-btn${isCompare ? ' disabled' : ''}`}
            id="btn-toggle-sidebar"
            title="显示/隐藏左侧目录"
            onClick={() => !isCompare && setSidebarCollapsed(!sidebarCollapsed)}
          >
            ☰
          </button>
          <span id="paper-title">
            {currentPaper ? currentPaper.name : '请从左侧目录选择论文'}
          </span>
        </div>
        <div className="ov-center">
          <div id="pdf-mode-switch">
            {(['en', 'zh', 'compare'] as PdfMode[]).map((mode) => (
              <button
                key={mode}
                className={`ov-btn pdf-mode-btn${pdfMode === mode ? ' active' : ''}`}
                data-pdf-mode={mode}
                onClick={() => handleModeChange(mode)}
              >
                {mode === 'en' ? '英文' : mode === 'zh' ? '中文' : '中英对照'}
              </button>
            ))}
          </div>
        </div>
        <div className="ov-right">
          <button
            className={`ov-btn${isCompare ? ' disabled' : ''}`}
            id="btn-toggle-right"
            title="显示/隐藏右侧面板"
            onClick={() => !isCompare && setRightCollapsed(!rightCollapsed)}
          >
            ☰
          </button>
        </div>
      </div>

      {/* PDF views */}
      {pdfMode !== 'compare' ? (
        <PDFSingleView />
      ) : (
        <PDFCompareView />
      )}
    </div>
  );
}

function PDFSingleView() {
  const { currentPaper, pdfMode, notify } = useStore();
  const [exists, setExists] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pdfSrc, setPdfSrc] = useState('');
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const pageTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const lang = pdfMode === 'zh' ? 'zh' : 'en';

  useEffect(() => {
    if (!currentPaper) {
      setExists(false);
      setPdfSrc('');
      return;
    }
    setLoading(true);
    checkPdfExists(lang, currentPaper.id).then((ex) => {
      setExists(ex);
      if (ex) {
        // 恢复上次阅读页码，并设置自适应宽度
        const savedPage = loadPdfPage(currentPaper.id);
        const base = pdfUrl(lang, currentPaper.id);
        setPdfSrc(savedPage
          ? `${base}#page=${savedPage}&zoom=page-width`
          : `${base}#zoom=page-width`);
      } else {
        setPdfSrc('');
      }
      setLoading(false);
    });
  }, [currentPaper, lang]);

  // 定期保存当前页码（通过 iframe URL hash 检测）
  useEffect(() => {
    if (!currentPaper || !pdfSrc) return;

    const saveCurrentPage = () => {
      try {
        const iframe = iframeRef.current;
        if (!iframe) return;
        // 尝试读取 iframe URL hash（同源才可访问）
        const hash = iframe.contentWindow?.location?.hash;
        if (hash) {
          const match = hash.match(/page=(\d+)/);
          if (match) {
            savePdfPage(currentPaper.id, parseInt(match[1]));
          }
        }
      } catch {
        // 跨域无法访问，忽略
      }
    };

    // 每 3 秒检查一次
    pageTimerRef.current = setInterval(saveCurrentPage, 3000);

    return () => {
      // 离开时保存一次
      saveCurrentPage();
      if (pageTimerRef.current) clearInterval(pageTimerRef.current);
    };
  }, [currentPaper?.id, pdfSrc]);

  if (!currentPaper || loading) {
    return (
      <div id="pdf-single-view" className="pdf-view active">
        <div className="empty-state">
          <div className="icon">📄</div>
          <div className="text">{loading ? '加载中…' : '选择一篇论文开始阅读'}</div>
          {!loading && <div className="sub">从左侧目录树中点击论文名</div>}
        </div>
      </div>
    );
  }

  if (!exists) {
    return (
      <div id="pdf-single-view" className="pdf-view active">
        {lang === 'zh' ? (
          <ArxivFetchPlaceholder />
        ) : (
          <div className="empty-state">
            <div className="icon">📄</div>
            <div className="text">暂无英文 PDF</div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div id="pdf-single-view" className="pdf-view active">
      <iframe ref={iframeRef} id="pdf-viewer" src={pdfSrc} style={{ width: '100%', height: '100%', border: 'none' }} />
    </div>
  );
}

function ArxivFetchPlaceholder() {
  const { currentPaper, notify, setPdfMode, pdfMode } = useStore();
  const [arxivId, setArxivId] = useState('');
  const [fetching, setFetching] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFetch = async () => {
    if (!currentPaper || !arxivId.trim()) {
      notify('请输入 arXiv ID 或链接', 'error');
      return;
    }
    setFetching(true);
    try {
      await apiFetchZhPdf(currentPaper.id, arxivId.trim());
      notify('中文 PDF 下载成功', 'success');
      // Re-trigger load by toggling mode
      setPdfMode('en');
      setTimeout(() => setPdfMode('zh'), 50);
    } catch (e: any) {
      notify('获取失败: ' + e.message, 'error');
    } finally {
      setFetching(false);
    }
  };

  const handleUploadFile = async (file: File) => {
    if (!currentPaper) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      notify('仅支持 PDF 文件', 'error');
      return;
    }
    setFetching(true);
    try {
      await uploadZhPdf(currentPaper.id, file);
      notify('中文 PDF 上传成功', 'success');
      setPdfMode('en');
      setTimeout(() => setPdfMode('zh'), 50);
    } catch (e: any) {
      notify('上传失败: ' + e.message, 'error');
    } finally {
      setFetching(false);
    }
  };

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
    const file = e.dataTransfer.files?.[0];
    if (file) handleUploadFile(file);
  };

  return (
    <div
      className={`empty-state zh-upload-zone${dragging ? ' drag-over' : ''}`}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <div className="icon">📄</div>
      <div className="text">暂无中文 PDF</div>
      <div className="zh-upload-hint">拖拽中文 PDF 到此处上传，或</div>
      <div className="zh-upload-actions" style={{ marginTop: 8 }}>
        <button
          className="arxiv-fetch-btn"
          disabled={fetching}
          onClick={() => fileInputRef.current?.click()}
        >
          选择文件上传
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          style={{ display: 'none' }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleUploadFile(file);
            e.target.value = '';
          }}
        />
      </div>
      <div className="zh-upload-divider">
        <span>或通过 arXiv 获取</span>
      </div>
      <div className="arxiv-input-row">
        <input
          type="text"
          className="arxiv-input"
          placeholder="输入 arXiv ID 获取中文翻译…"
          value={arxivId}
          onChange={(e) => setArxivId(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleFetch()}
        />
        <button
          className="arxiv-fetch-btn"
          disabled={fetching}
          onClick={handleFetch}
        >
          {fetching ? '处理中…' : '获取'}
        </button>
      </div>
    </div>
  );
}

function PDFCompareView() {
  const { currentPaper, notify } = useStore();
  const [hasEn, setHasEn] = useState(false);
  const [hasZh, setHasZh] = useState(false);
  const [enSrc, setEnSrc] = useState('');
  const [zhSrc, setZhSrc] = useState('');
  const [arxivId, setArxivId] = useState('');
  const [fetching, setFetching] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!currentPaper) return;
    const savedPage = loadPdfPage(currentPaper.id);
    Promise.all([
      checkPdfExists('en', currentPaper.id),
      checkPdfExists('zh', currentPaper.id),
    ]).then(([en, zh]) => {
      setHasEn(en);
      setHasZh(zh);
      const pageHash = savedPage
        ? `#page=${savedPage}&zoom=page-width`
        : '#zoom=page-width';
      setEnSrc(en ? pdfUrl('en', currentPaper.id) + pageHash : '');
      setZhSrc(zh ? pdfUrl('zh', currentPaper.id) + pageHash : '');
    });
  }, [currentPaper]);

  const handleFetchZh = async () => {
    if (!currentPaper || !arxivId.trim()) {
      notify('请输入 arXiv ID', 'error');
      return;
    }
    setFetching(true);
    try {
      await apiFetchZhPdf(currentPaper.id, arxivId.trim());
      setHasZh(true);
      setZhSrc(pdfUrl('zh', currentPaper.id));
      notify('中文 PDF 下载成功', 'success');
    } catch (e: any) {
      notify('获取失败: ' + e.message, 'error');
    } finally {
      setFetching(false);
    }
  };

  const handleUploadFile = async (file: File) => {
    if (!currentPaper) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      notify('仅支持 PDF 文件', 'error');
      return;
    }
    setFetching(true);
    try {
      await uploadZhPdf(currentPaper.id, file);
      setHasZh(true);
      setZhSrc(pdfUrl('zh', currentPaper.id) + '?t=' + Date.now());
      notify('中文 PDF 上传成功', 'success');
    } catch (e: any) {
      notify('上传失败: ' + e.message, 'error');
    } finally {
      setFetching(false);
    }
  };

  const onDragOver = (e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setDragging(true); };
  const onDragLeave = (e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setDragging(false); };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleUploadFile(file);
  };

  return (
    <div id="pdf-compare-view" className="pdf-view active" style={{ display: 'flex' }}>
      <div className="pdf-col">
        <div className="pdf-col-header">英文 PDF</div>
        <div className="pdf-col-body">
          {hasEn ? (
            <iframe src={enSrc} style={{ width: '100%', height: '100%', border: 'none' }} />
          ) : (
            <div className="pdf-missing" style={{ display: 'flex' }}>英文 PDF 缺失</div>
          )}
        </div>
      </div>
      <div className="pdf-col">
        <div className="pdf-col-header">中文 PDF</div>
        <div className="pdf-col-body">
          {hasZh ? (
            <iframe src={zhSrc} style={{ width: '100%', height: '100%', border: 'none' }} />
          ) : (
            <div
              className={`pdf-missing${dragging ? ' drag-over' : ''}`}
              style={{ display: 'flex' }}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
            >
              <div className="arxiv-fetch-box">
                <div style={{ fontSize: 14, color: '#d1d5db', marginBottom: 10 }}>
                  中文 PDF 缺失
                </div>
                <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 10 }}>
                  拖拽中文 PDF 到此处，或
                  <button
                    className="arxiv-fetch-btn"
                    style={{ marginLeft: 6, fontSize: 12, padding: '2px 8px' }}
                    disabled={fetching}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    选择文件
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf"
                    style={{ display: 'none' }}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleUploadFile(file);
                      e.target.value = '';
                    }}
                  />
                </div>
                <div className="zh-upload-divider" style={{ marginBottom: 10 }}>
                  <span>或通过 arXiv 获取</span>
                </div>
                <div className="arxiv-input-row">
                  <input
                    type="text"
                    className="arxiv-input"
                    placeholder="输入 arXiv ID 获取中文翻译…"
                    value={arxivId}
                    onChange={(e) => setArxivId(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleFetchZh()}
                  />
                  <button
                    className="arxiv-fetch-btn"
                    disabled={fetching}
                    onClick={handleFetchZh}
                  >
                    {fetching ? '处理中…' : '获取'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
