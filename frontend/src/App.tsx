import { useCallback } from 'react';
import './App.css';
import ConfirmDialog from './components/ConfirmDialog';
import ContextMenu from './components/ContextMenu';
import Lightbox from './components/Lightbox';
import { ImportModal, MoveModal, SettingsModal } from './components/Modals';
import Notification from './components/Notification';
import PDFPanel from './components/PDFPanel';
import RightPanel from './components/RightPanel';
import Sidebar from './components/Sidebar';
import { useStore } from './store/useStore';

export default function App() {
  const {
    pdfMode,
    sidebarCollapsed,
    rightCollapsed,
  } = useStore();

  const isCompare = pdfMode === 'compare';

  // Resize handler factory: targets a specific DOM element by ID
  const handleResize = useCallback(
    (elementId: string, side: 'left' | 'right') =>
      (e: React.MouseEvent) => {
        e.preventDefault();
        const target = document.getElementById(elementId);
        if (!target) return;

        const startX = e.clientX;
        const startW = target.offsetWidth;
        const minW = parseInt(getComputedStyle(target).minWidth) || 200;
        const maxW = parseInt(getComputedStyle(target).maxWidth) || 900;

        (e.currentTarget as HTMLElement).classList.add('active');
        document.body.classList.add('resizing');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';

        const handleEl = e.currentTarget as HTMLElement;
        let rafId = 0;

        const onMove = (ev: MouseEvent) => {
          cancelAnimationFrame(rafId);
          rafId = requestAnimationFrame(() => {
            const dx = side === 'left' ? ev.clientX - startX : startX - ev.clientX;
            target.style.width = Math.max(minW, Math.min(maxW, startW + dx)) + 'px';
          });
        };
        const onUp = () => {
          cancelAnimationFrame(rafId);
          handleEl.classList.remove('active');
          document.body.classList.remove('resizing');
          document.body.style.cursor = '';
          document.body.style.userSelect = '';
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
      },
    [],
  );

  return (
    <>
      <div id="app" className={isCompare ? 'compare-mode' : ''}>
        {/* Sidebar */}
        <Sidebar />

        {/* Sidebar resize handle */}
        {!sidebarCollapsed && !isCompare && (
          <div
            id="sidebar-resize"
            className="resize-handle"
            onMouseDown={handleResize('sidebar', 'left')}
          />
        )}

        {/* Main area */}
        <div id="main-area">
          <div id="content-area">
            <PDFPanel />

            {/* Right resize handle */}
            {!rightCollapsed && !isCompare && (
              <div
                id="right-resize"
                className="resize-handle"
                onMouseDown={handleResize('right-panel', 'right')}
              />
            )}

            {/* Right panel */}
            {!isCompare && <RightPanel />}
          </div>
        </div>
      </div>

      {/* Floating elements */}
      <Notification />
      <ConfirmDialog />
      <ImportModal />
      <MoveModal />
      <SettingsModal />
      <ContextMenu />
      <Lightbox />
    </>
  );
}
