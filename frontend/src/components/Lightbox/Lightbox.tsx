import { useCallback, useEffect, useRef, useState } from 'react';
import { imageUrl } from '../../api';
import { useStore } from '../../store/useStore';
import type { ImageLang } from '../../types';

export default function Lightbox() {
  const {
    lightboxOpen,
    setLightboxOpen,
    currentImageId,
    imageLang,
    setImageLang,
  } = useStore();

  const [zoomed, setZoomed] = useState(false);
  const [info, setInfo] = useState('');
  const imgRef = useRef<HTMLImageElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Drag state for panning when zoomed
  const dragState = useRef({ dragging: false, startX: 0, startY: 0, scrollX: 0, scrollY: 0 });

  const src = currentImageId ? imageUrl(currentImageId, imageLang) : '';

  useEffect(() => {
    if (lightboxOpen && src) {
      setZoomed(false);
      wrapRef.current?.scrollTo(0, 0);
      // Get dimensions
      const img = new Image();
      img.onload = () => setInfo(`${img.naturalWidth} × ${img.naturalHeight}`);
      img.src = src;
    }
  }, [lightboxOpen, src]);

  // Escape to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && lightboxOpen) {
        setLightboxOpen(false);
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [lightboxOpen, setLightboxOpen]);

  // Mouse drag for panning
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const ds = dragState.current;
      if (!ds.dragging) return;
      if (wrapRef.current) {
        wrapRef.current.scrollLeft = ds.scrollX - (e.clientX - ds.startX);
        wrapRef.current.scrollTop = ds.scrollY - (e.clientY - ds.startY);
      }
    };
    const onUp = () => {
      dragState.current.dragging = false;
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, []);

  const handleImgMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (!zoomed) return;
      dragState.current = {
        dragging: true,
        startX: e.clientX,
        startY: e.clientY,
        scrollX: wrapRef.current?.scrollLeft || 0,
        scrollY: wrapRef.current?.scrollTop || 0,
      };
      e.preventDefault();
    },
    [zoomed],
  );

  const handleImgClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      setZoomed(!zoomed);
    },
    [zoomed],
  );

  const handleBgClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget || (e.target as HTMLElement).id === 'lightbox-img-wrap') {
        setLightboxOpen(false);
      }
    },
    [setLightboxOpen],
  );

  const handleLangToggle = useCallback(
    (lang: ImageLang) => {
      setImageLang(lang);
    },
    [setImageLang],
  );

  if (!lightboxOpen) return null;

  return (
    <div id="lightbox" className="show" onClick={handleBgClick}>
      <div id="lightbox-toolbar">
        <div className="lang-toggle">
          {(['zh', 'en'] as ImageLang[]).map((lang) => (
            <button
              key={lang}
              className={`lang-btn lb-lang${imageLang === lang ? ' active' : ''}`}
              data-lang={lang}
              onClick={(e) => {
                e.stopPropagation();
                handleLangToggle(lang);
              }}
            >
              {lang === 'zh' ? '中文' : 'English'}
            </button>
          ))}
        </div>
        <button
          id="lightbox-close"
          onClick={() => setLightboxOpen(false)}
        >
          ✕
        </button>
      </div>
      <div id="lightbox-img-wrap" ref={wrapRef} onClick={handleBgClick}>
        <img
          id="lightbox-img"
          ref={imgRef}
          src={src}
          alt="论文插图"
          className={zoomed ? 'lb-zoomed' : ''}
          onClick={handleImgClick}
          onMouseDown={handleImgMouseDown}
        />
      </div>
      <div id="lightbox-info">{info}</div>
    </div>
  );
}
