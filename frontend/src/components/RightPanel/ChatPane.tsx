import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from '../../api';
import { useConfirm } from '../../hooks/useConfirm';
import { useStore } from '../../store/useStore';
import type { ChatMessage } from '../../types';
import { highlightCodeBlocks, renderMarkdown } from '../../utils/markdown';

/** AI 回复气泡（Markdown 渲染） */
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
    notify,
  } = useStore();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [streamingReply, setStreamingReply] = useState('');
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef(false);

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
    if (!currentChatSessionId || !inputValue.trim() || chatStreaming) return;

    const userMsg = inputValue.trim();
    setInputValue('');
    setChatStreaming(true);
    setStreamingReply('');
    abortRef.current = false;

    // 乐观地添加用户消息到列表
    const tempUserMsg: ChatMessage = {
      id: Date.now(),
      role: 'user',
      content: userMsg,
      created_at: new Date().toISOString(),
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
  }, [currentChatSessionId, inputValue, chatStreaming, currentPaper, chatSessions, setChatStreaming, setChatSessions, notify]);

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
                <div className="icon">🤖</div>
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
              {msg.role === 'user' ? '👤' : '🤖'}
            </div>
            <div className="chat-msg-bubble">
              {msg.role === 'user'
                ? <div className="chat-msg-text">{msg.content}</div>
                : <ModelBubble content={msg.content} />
              }
            </div>
          </div>
        ))}

        {/* 流式回复 */}
        {chatStreaming && streamingReply && (
          <div className="chat-msg chat-msg-model">
            <div className="chat-msg-avatar">🤖</div>
            <div className="chat-msg-bubble">
              <ModelBubble content={streamingReply} />
            </div>
          </div>
        )}

        {chatStreaming && !streamingReply && (
          <div className="chat-msg chat-msg-model">
            <div className="chat-msg-avatar">🤖</div>
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
        <div className="chat-input-area">
          <textarea
            ref={inputRef}
            className="chat-input"
            placeholder="输入问题… (Enter 发送, Shift+Enter 换行)"
            value={inputValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={chatStreaming}
            rows={1}
          />
          <button
            className="chat-send-btn"
            onClick={handleSend}
            disabled={chatStreaming || !inputValue.trim()}
            title="发送"
          >
            {chatStreaming ? '⏳' : '➤'}
          </button>
        </div>
      )}
    </div>
  );
}


