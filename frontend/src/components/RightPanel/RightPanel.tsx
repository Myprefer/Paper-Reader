import { useIsMobile } from '../../hooks/useIsMobile';
import { useStore } from '../../store/useStore';
import type { RightTab } from '../../types';
import ChatPane from './ChatPane';
import ImagePane from './ImagePane';
import NotePane from './NotePane';

export default function RightPanel() {
  const { rightCollapsed, setRightCollapsed, rightTab, setRightTab } = useStore();
  const isMobile = useIsMobile();

  const tabs: { key: RightTab; label: string }[] = [
    { key: 'note', label: '📝' },
    { key: 'image', label: '🖼️' },
    { key: 'chat', label: '💬' },
  ];

  return (
    <div id="right-panel" className={rightCollapsed ? 'collapsed' : ''}>
      <div id="right-tabs">
        {tabs.map((t) => (
          <button
            key={t.key}
            className={`right-tab${rightTab === t.key ? ' active' : ''}`}
            onClick={() => setRightTab(t.key)}
            disabled={rightCollapsed}
          >
            {t.label}
          </button>
        ))}
        {isMobile && (
          <button
            className="mobile-close-btn-right"
            onClick={() => setRightCollapsed(true)}
            title="关闭"
            aria-label="关闭右侧栏"
          >
            ✕
          </button>
        )}
      </div>
      <div id="right-content">
        <div className={`right-pane${rightTab === 'note' ? ' active' : ''}`} id="note-pane">
          <NotePane />
        </div>
        <div className={`right-pane${rightTab === 'image' ? ' active' : ''}`} id="image-pane">
          <ImagePane />
        </div>
        <div className={`right-pane${rightTab === 'chat' ? ' active' : ''}`} id="chat-pane">
          <ChatPane />
        </div>
      </div>
    </div>
  );
}
