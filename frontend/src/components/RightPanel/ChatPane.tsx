import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from '../../api';
import { useConfirm } from '../../hooks/useConfirm';
import { useStore } from '../../store/useStore';
import type { ChatMessage } from '../../types';
import { highlightCodeBlocks, renderMarkdown } from '../../utils/markdown';

const CHAT_MODELS = [
  'gemini-3.1-pro-preview',
  'gemini-3-flash-preview',
  'gemini-2.5-pro',
  'gemini-2.5-flash',
];

/** AI 回复气泡（Markdown 渲染） */
function GeminiIcon() {
  return (
    <svg width="128" height="128" viewBox="0 0 128 128" fill="none" xmlns="http://www.w3.org/2000/svg">
      <mask id="mask0_10019_819" style={{ maskType: 'alpha' }} maskUnits="userSpaceOnUse" x="8" y="8" width="112" height="112">
        <path d="M63.892 8C62.08 38.04 38.04 62.08 8 63.892V64.108C38.04 65.92 62.08 89.96 63.892 120H64.108C65.92 89.96 89.96 65.92 120 64.108V63.892C89.96 62.08 65.92 38.04 64.108 8H63.892Z" fill="url(#paint0_linear_10019_819)" />
      </mask>
      <g mask="url(#mask0_10019_819)">
        <path d="M64 0C99.3216 0 128 28.6784 128 64C128 99.3216 99.3216 128 64 128C28.6784 128 0 99.3216 0 64C0 28.6784 28.6784 0 64 0Z" fill="url(#paint1_linear_10019_819)" />
      </g>
      <defs>
        <linearGradient id="paint0_linear_10019_819" x1="100.892" y1="30.04" x2="22.152" y2="96.848" gradientUnits="userSpaceOnUse"><stop stop-color="#217BFE" /><stop offset="0.14" stop-color="#1485FC" />
          <stop offset="0.27" stop-color="#078EFB" />
          <stop offset="0.52" stop-color="#548FFD" />
          <stop offset="0.78" stop-color="#A190FF" />
          <stop offset="0.89" stop-color="#AF94FE" />
          <stop offset="1" stop-color="#BD99FE" />
        </linearGradient>
        <linearGradient id="paint1_linear_10019_819" x1="47.988" y1="82.52" x2="96.368" y2="32.456" gradientUnits="userSpaceOnUse">
          <stop stop-color="#217BFE" />
          <stop offset="0.14" stop-color="#1485FC" />
          <stop offset="0.27" stop-color="#078EFB" />
          <stop offset="0.52" stop-color="#548FFD" />
          <stop offset="0.78" stop-color="#A190FF" />
          <stop offset="0.89" stop-color="#AF94FE" />
          <stop offset="1" stop-color="#BD99FE" />
        </linearGradient>
      </defs>
    </svg>
  );
}

function ModelBubble({ content }: { content: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) highlightCodeBlocks(ref.current);
  }, [content]);
  return (
    <div
      ref={ref}
      className="chat-msg-text markdown-body"
      dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
    />
  );
}

export default function ChatPane() {
  const confirm = useConfirm();
  const {
    currentPaper,
    chatSessions, setChatSessions,
    currentChatSessionId, setCurrentChatSessionId,
    chatStreaming, setChatStreaming,
    chatModel, setChatModel,
    notify,
  } = useStore();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [selectedImages, setSelectedImages] = useState<File[]>([]);
  const [selectedImagePreviewUrls, setSelectedImagePreviewUrls] = useState<string[]>([]);
  const [dragOverInputArea, setDragOverInputArea] = useState(false);
  const [streamingReply, setStreamingReply] = useState('');
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef(false);

  useEffect(() => {
    if (selectedImages.length === 0) {
      setSelectedImagePreviewUrls([]);
      return;
    }
    const urls = selectedImages.map((file) => URL.createObjectURL(file));
    setSelectedImagePreviewUrls(urls);
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [selectedImages]);

  // 加载会话列表
  useEffect(() => {
    if (!currentPaper) {
      setChatSessions([]);
      setCurrentChatSessionId(null);
      setMessages([]);
      return;
    }
    api.fetchChatSessions(currentPaper.id).then(async (sessions) => {
      if (sessions.length > 0) {
        setChatSessions(sessions);
        setCurrentChatSessionId(sessions[0].id);
      } else {
        // 自动创建第一个对话
        try {
          const data = await api.createChatSession(currentPaper.id);
          if (data.success) {
            const updated = await api.fetchChatSessions(currentPaper.id);
            setChatSessions(updated);
            setCurrentChatSessionId(data.id);
          }
        } catch {
          setChatSessions([]);
          setCurrentChatSessionId(null);
        }
        setMessages([]);
      }
    }).catch(() => {
      notify('加载会话列表失败', 'error');
    });
  }, [currentPaper?.id]);

  // 加载消息
  useEffect(() => {
    if (!currentChatSessionId) {
      setMessages([]);
      return;
    }
    setMessages([]); // 切换会话时先清空，防止布局跳动
    api.fetchChatMessages(currentChatSessionId).then((msgs) => {
      setMessages(msgs);
    }).catch(() => {
      notify('加载消息失败', 'error');
    });
  }, [currentChatSessionId]);

  // 自动滚动到底部（使用 scrollTop 避免 scrollIntoView 导致父容器位移）
  useEffect(() => {
    const el = messagesContainerRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }
  }, [messages, streamingReply]);

  // 新建会话
  const handleNewSession = useCallback(async () => {
    if (!currentPaper) return;
    try {
      const data = await api.createChatSession(currentPaper.id);
      if (data.success) {
        const sessions = await api.fetchChatSessions(currentPaper.id);
        setChatSessions(sessions);
        setCurrentChatSessionId(data.id);
        setMessages([]);
        notify('新对话已创建', 'success');
      }
    } catch (e: any) {
      notify('创建对话失败: ' + e.message, 'error');
    }
  }, [currentPaper, setChatSessions, setCurrentChatSessionId, notify]);

  // 删除会话
  const handleDeleteSession = useCallback(async () => {
    if (!currentChatSessionId || !currentPaper) return;
    if (!(await confirm('确定删除该对话？所有消息将被清除。'))) return;
    try {
      await api.deleteChatSession(currentChatSessionId);
      const sessions = await api.fetchChatSessions(currentPaper.id);
      setChatSessions(sessions);
      if (sessions.length > 0) {
        setCurrentChatSessionId(sessions[0].id);
      } else {
        setCurrentChatSessionId(null);
        setMessages([]);
      }
      notify('对话已删除', 'success');
    } catch (e: any) {
      notify('删除失败: ' + e.message, 'error');
    }
  }, [currentChatSessionId, currentPaper, confirm, setChatSessions, setCurrentChatSessionId, notify]);

  // 发送消息
  const handleSend = useCallback(async () => {
    if (!currentChatSessionId || chatStreaming) return;

    const userMsg = inputValue.trim();
    if (!userMsg && selectedImages.length === 0) return;

    const imagesForSend = selectedImages;
    const imagePreviewUrlsForSend = selectedImagePreviewUrls;
    setInputValue('');
    setSelectedImages([]);
    setChatStreaming(true);
    setStreamingReply('');
    abortRef.current = false;

    // 乐观地添加用户消息到列表
    const tempUserMsg: ChatMessage = {
      id: Date.now(),
      role: 'user',
      content: userMsg,
      created_at: new Date().toISOString(),
      imageUrls: imagesForSend.length ? imagePreviewUrlsForSend : undefined,
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    let fullReply = '';
    let errorMsg = '';

    try {
      await api.sendChatMessage(
        currentChatSessionId,
        userMsg,
        (text) => {
          if (abortRef.current) return;
          fullReply += text;
          setStreamingReply(fullReply);
        },
        (title) => {
          if (title && currentPaper) {
            setChatSessions(
              chatSessions.map((s) =>
                s.id === currentChatSessionId ? { ...s, title } : s
              )
            );
          }
        },
        (msg) => {
          errorMsg = msg;
        },
        imagesForSend,
        chatModel,
      );

      if (errorMsg) {
        throw new Error(errorMsg);
      }

      // 完成后，添加 AI 回复到消息列表
      if (fullReply) {
        const aiMsg: ChatMessage = {
          id: Date.now() + 1,
          role: 'model',
          content: fullReply,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, aiMsg]);
      }
    } catch (e: any) {
      notify('发送失败: ' + e.message, 'error');
      // 移除乐观添加的用户消息
      setMessages((prev) => prev.filter((m) => m.id !== tempUserMsg.id));
    } finally {
      setChatStreaming(false);
      setStreamingReply('');
    }
  }, [currentChatSessionId, inputValue, selectedImages, selectedImagePreviewUrls, chatStreaming, currentPaper, chatSessions, setChatStreaming, setChatSessions, notify, chatModel]);

  const handlePickImage = useCallback(() => {
    imageInputRef.current?.click();
  }, []);

  const appendImages = useCallback((files: File[]) => {
    if (files.length === 0) return;

    const invalid = files.find((file) => !file.type.startsWith('image/'));
    if (invalid) {
      notify('仅支持图片文件', 'error');
      return;
    }

    setSelectedImages((prev) => {
      const remaining = Math.max(0, 10 - prev.length);
      const next = [...prev, ...files.slice(0, remaining)];
      if (files.length > remaining) {
        notify('每条消息最多上传 10 张图片', 'info');
      }
      return next;
    });
  }, [notify]);

  const handleImageChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    appendImages(files);
    e.currentTarget.value = '';
  }, [appendImages]);

  const handlePaste = useCallback((e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = Array.from(e.clipboardData?.items || []);
    const pastedImages = items
      .filter((item) => item.type.startsWith('image/'))
      .map((item) => item.getAsFile())
      .filter((file): file is File => !!file);

    if (pastedImages.length > 0) {
      e.preventDefault();
      appendImages(pastedImages);
    }
  }, [appendImages]);

  const handleDragOverInputArea = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!dragOverInputArea) setDragOverInputArea(true);
  }, [dragOverInputArea]);

  const handleDragLeaveInputArea = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setDragOverInputArea(false);
  }, []);

  const handleDropInputArea = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOverInputArea(false);
    const files = Array.from(e.dataTransfer.files || []);
    appendImages(files);
  }, [appendImages]);

  const handleClearImage = useCallback((index: number) => {
    setSelectedImages((prev) => prev.filter((_, i) => i !== index));
  }, []);

  // 快捷键发送
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  // 自动调整输入框高度
  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
  }, []);

  if (!currentPaper) {
    return (
      <div className="chat-empty">
        <div className="icon">💬</div>
        <div className="text">选择论文后开始 AI 问答</div>
      </div>
    );
  }

  return (
    <div className="chat-pane">
      {/* 会话选择器 + 工具栏 */}
      <div className="chat-toolbar">
        <select
          className="chat-session-select"
          value={currentChatSessionId ?? ''}
          onChange={(e) => {
            const id = Number(e.target.value);
            if (id) setCurrentChatSessionId(id);
          }}
        >
          {chatSessions.length === 0 && (
            <option value="">无对话</option>
          )}
          {chatSessions.map((s) => (
            <option key={s.id} value={s.id}>{s.title}</option>
          ))}
        </select>
        <select
          className="note-select"
          value={chatModel}
          onChange={(e) => setChatModel(e.target.value)}
          title="AI问答模型"
        >
          {CHAT_MODELS.map((model) => (
            <option key={model} value={model}>{model}</option>
          ))}
        </select>
        <button className="note-btn" onClick={handleNewSession} title="新建对话">＋</button>
        {currentChatSessionId && (
          <button className="note-btn danger" onClick={handleDeleteSession} title="删除对话">🗑️</button>
        )}
      </div>

      {/* 消息列表 */}
      <div className="chat-messages" ref={messagesContainerRef}>
        {messages.length === 0 && !chatStreaming && (
          <div className="chat-empty-hint">
            {currentChatSessionId ? (
              <>
                <div className="icon"><GeminiIcon /></div>
                <div className="text">开始提问吧</div>
                <div className="sub">第一条消息将自动附带论文 PDF<br />AI 将基于论文内容回答您的问题</div>
              </>
            ) : (
              <>
                <div className="icon">💬</div>
                <div className="text">点击 ＋ 创建新对话</div>
              </>
            )}
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`chat-msg chat-msg-${msg.role}`}>
            <div className="chat-msg-avatar">
              {msg.role === 'user' ? '👤' : <GeminiIcon />}
            </div>
            <div className="chat-msg-bubble">
              {msg.role === 'user'
                ? <>
                  {!!msg.imageUrls?.length && (
                    <div className="chat-msg-images">
                      {msg.imageUrls.map((url, idx) => (
                        <img key={`${msg.id}-${idx}`} className="chat-msg-image" src={url} alt="uploaded" />
                      ))}
                    </div>
                  )}
                  {!!msg.content && <div className="chat-msg-text">{msg.content}</div>}
                </>
                : <ModelBubble content={msg.content} />
              }
            </div>
          </div>
        ))}

        {/* 流式回复 */}
        {chatStreaming && streamingReply && (
          <div className="chat-msg chat-msg-model">
            <div className="chat-msg-avatar"><GeminiIcon /></div>
            <div className="chat-msg-bubble">
              <ModelBubble content={streamingReply} />
            </div>
          </div>
        )}

        {chatStreaming && !streamingReply && (
          <div className="chat-msg chat-msg-model">
            <div className="chat-msg-avatar"><GeminiIcon /></div>
            <div className="chat-msg-bubble">
              <div className="chat-thinking">
                <div className="spinner" /> 思考中…
              </div>
            </div>
          </div>
        )}

      </div>

      {/* 输入区 */}
      {currentChatSessionId && (
        <div
          className={`chat-input-area${dragOverInputArea ? ' drag-over' : ''}`}
          onDragOver={handleDragOverInputArea}
          onDragLeave={handleDragLeaveInputArea}
          onDrop={handleDropInputArea}
        >
          <input
            ref={imageInputRef}
            type="file"
            accept="image/*"
            multiple
            style={{ display: 'none' }}
            onChange={handleImageChange}
          />
          <button
            className="chat-attach-btn"
            onClick={handlePickImage}
            disabled={chatStreaming}
            title="上传图片"
          >
            🖼️
          </button>
          {!!selectedImagePreviewUrls.length && (
            <div className="chat-image-preview-list">
              {selectedImagePreviewUrls.map((url, index) => (
                <div key={`preview-${index}`} className="chat-image-preview-wrap">
                  <img className="chat-image-preview" src={url} alt="preview" />
                  <button
                    className="chat-image-remove-btn"
                    onClick={() => handleClearImage(index)}
                    disabled={chatStreaming}
                    title="移除图片"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
          <textarea
            ref={inputRef}
            className="chat-input"
            placeholder="输入问题…（可粘贴/拖拽图片，或点击🖼️上传）"
            value={inputValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            disabled={chatStreaming}
            rows={1}
          />
          <button
            className="chat-send-btn"
            onClick={handleSend}
            disabled={chatStreaming || (!inputValue.trim() && selectedImages.length === 0)}
            title="发送"
          >
            {chatStreaming ? '⏳' : '➤'}
          </button>
        </div>
      )}
    </div>
  );
}


