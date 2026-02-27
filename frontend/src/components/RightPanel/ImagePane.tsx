import { useCallback, useEffect, useState } from 'react';
import * as api from '../../api';
import { useConfirm } from '../../hooks/useConfirm';
import { useStore } from '../../store/useStore';
import type { ImageLang } from '../../types';

export default function ImagePane() {
  const confirm = useConfirm();
  const {
    currentPaper,
    imagesList, setImagesList,
    currentImageId, setCurrentImageId,
    imageLang, setImageLang,
    generatingImage, setGeneratingImage,
    setLightboxOpen,
    notify,
  } = useStore();

  const [imgSrc, setImgSrc] = useState('');
  const [hasImage, setHasImage] = useState(false);
  const [loading, setLoading] = useState(false);
  const [imgDimensions, setImgDimensions] = useState('');

  // Load images list when paper changes
  useEffect(() => {
    if (!currentPaper) {
      setImagesList([]);
      setCurrentImageId(null);
      setHasImage(false);
      setImgSrc('');
      return;
    }

    api.fetchImages(currentPaper.id).then((images) => {
      setImagesList(images);
      if (images.length > 0) {
        setCurrentImageId(images[0].id);
      } else {
        setCurrentImageId(null);
        setHasImage(false);
        setImgSrc('');
      }
    }).catch(() => {
      setImagesList([]);
      setCurrentImageId(null);
    });
  }, [currentPaper?.id]);

  // Load image when currentImageId or lang changes
  useEffect(() => {
    if (!currentImageId) {
      setHasImage(false);
      setImgSrc('');
      return;
    }
    setLoading(true);
    const url = api.imageUrl(currentImageId, imageLang);
    const img = new Image();
    img.onload = () => {
      setImgSrc(url);
      setHasImage(true);
      setImgDimensions(`${img.naturalWidth} × ${img.naturalHeight}`);
      setLoading(false);
    };
    img.onerror = () => {
      setHasImage(false);
      setImgSrc('');
      setImgDimensions('');
      setLoading(false);
    };
    img.src = url;
  }, [currentImageId, imageLang]);

  const currentImage = imagesList.find((i) => i.id === currentImageId);

  const handleGenerate = useCallback(async () => {
    if (!currentPaper || generatingImage) return;
    setGeneratingImage(true);
    try {
      const data = await api.generateImage(currentPaper.id);
      // Reload images list
      const images = await api.fetchImages(currentPaper.id);
      setImagesList(images);
      setCurrentImageId(data.id);
      setImageLang('en');
      notify('插图生成完成', 'success');
    } catch (e: any) {
      notify('插图生成失败: ' + e.message, 'error');
    } finally {
      setGeneratingImage(false);
    }
  }, [currentPaper, generatingImage, setGeneratingImage, setImageLang, setImagesList, setCurrentImageId, notify]);

  const handleTranslate = useCallback(async () => {
    if (!currentImageId || generatingImage) return;
    setGeneratingImage(true);
    try {
      await api.translateImage(currentImageId);
      // Reload images list
      if (currentPaper) {
        const images = await api.fetchImages(currentPaper.id);
        setImagesList(images);
      }
      notify('插图翻译完成', 'success');
      setImageLang('zh');
    } catch (e: any) {
      notify('插图翻译失败: ' + e.message, 'error');
    } finally {
      setGeneratingImage(false);
    }
  }, [currentImageId, currentPaper, generatingImage, setGeneratingImage, setImageLang, setImagesList, notify]);

  const handleDelete = useCallback(async () => {
    if (!currentImageId || !currentPaper) return;
    if (!(await confirm('确定删除该插图（包括所有语言版本）？此操作不可撤销。'))) return;
    try {
      const data = await api.deleteImage(currentImageId);
      // Reload images list
      const images = await api.fetchImages(currentPaper.id);
      setImagesList(images);
      if (images.length > 0) {
        setCurrentImageId(images[0].id);
      } else {
        setCurrentImageId(null);
        setHasImage(false);
        setImgSrc('');
        setImgDimensions('');
      }
      notify('插图已删除（' + (data.deleted?.length || 0) + ' 个文件）', 'success');
    } catch (e: any) {
      notify('删除失败: ' + e.message, 'error');
    }
  }, [currentImageId, currentPaper, confirm, notify, setImagesList, setCurrentImageId]);

  const handleLangToggle = useCallback(
    (lang: ImageLang) => {
      setImageLang(lang);
    },
    [setImageLang],
  );

  const showTranslate = currentImage && !currentImage.has_zh;

  return (
    <>
      {/* Image selector (shown when multiple images exist) */}
      {imagesList.length > 1 && (
        <div id="image-selector" style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          padding: '6px 12px', borderBottom: '1px solid var(--surface1)',
          fontSize: '13px',
        }}>
          <select
            value={currentImageId ?? ''}
            onChange={(e) => {
              const id = Number(e.target.value);
              if (id) setCurrentImageId(id);
            }}
            style={{
              flex: 1, padding: '4px 8px', borderRadius: '4px',
              border: '1px solid var(--surface2)', background: 'var(--surface0)',
              color: 'var(--text)', fontSize: '13px',
            }}
          >
            {imagesList.map((img) => (
              <option key={img.id} value={img.id}>{img.title}</option>
            ))}
          </select>
        </div>
      )}

      {/* Toolbar */}
      <div id="image-toolbar">
        <div className="lang-toggle">
          {(['zh', 'en'] as ImageLang[]).map((lang) => (
            <button
              key={lang}
              className={`lang-btn${imageLang === lang ? ' active' : ''}`}
              data-lang={lang}
              onClick={() => handleLangToggle(lang)}
            >
              {lang === 'zh' ? '中文' : 'EN'}
            </button>
          ))}
        </div>
        {!generatingImage && hasImage && currentImageId && (
          <>
            {showTranslate && (
              <button
                className="img-act-btn"
                title="翻译为中文版"
                onClick={handleTranslate}
              >
                🌐
              </button>
            )}
            <button
              className="img-act-btn img-act-delete"
              title="删除该插图"
              onClick={handleDelete}
            >
              🗑️
            </button>
          </>
        )}
        {!generatingImage && (
          <button
            className="img-act-btn img-act-generate"
            title="AI 生成新插图"
            onClick={handleGenerate}
          >
            🤖
          </button>
        )}
        <span id="image-zoom-info">{imgDimensions}</span>
      </div>

      {/* Image container */}
      <div id="image-container">
        {generatingImage && (
          <div className="empty-state">
            <div className="spinner" />
            <div className="text">正在生成插图，请稍候…</div>
            <div className="sub">AI 绘图可能需要 30 秒以上</div>
          </div>
        )}

        {!generatingImage && !hasImage && !loading && (
          <div className="empty-state">
            <div className="icon">🖼️</div>
            <div className="text">
              {currentPaper
                ? currentImageId
                  ? `暂无${imageLang === 'zh' ? '中文' : '英文'}版插图`
                  : '暂无插图'
                : '选择论文后查看插图'}
            </div>
            {currentPaper && (
              <button className="gen-btn-big" onClick={handleGenerate}>
                🤖 AI 生成插图
              </button>
            )}
          </div>
        )}

        {!generatingImage && hasImage && (
          <img
            id="paper-image"
            src={imgSrc}
            alt="论文插图"
            onClick={() => setLightboxOpen(true)}
            style={{ cursor: 'zoom-in' }}
          />
        )}

        {loading && !generatingImage && (
          <div className="empty-state">
            <div className="text">加载中…</div>
          </div>
        )}
      </div>
    </>
  );
}
