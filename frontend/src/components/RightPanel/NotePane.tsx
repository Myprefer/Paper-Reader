import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from '../../api';
import { useConfirm } from '../../hooks/useConfirm';
import { useStore } from '../../store/useStore';
import { highlightCodeBlocks, renderMarkdown } from '../../utils/markdown';

const NOTE_MODELS = [
  'gemini-3.1-pro-preview',
  'gemini-3-flash-preview',
  'gemini-2.5-pro',
  'gemini-2.5-flash',
];

export default function NotePane() {
  const confirm = useConfirm();
  const {
    currentPaper,
    notesList, setNotesList,
    currentNoteId, setCurrentNoteId,
    isEditing, setIsEditing,
    noteModified, setNoteModified,
    originalNoteContent, setOriginalNoteContent,
    generatingNote, setGeneratingNote,
    generatingNotePaperId, setGeneratingNotePaperId,
    noteModel, setNoteModel,
    notify,
  } = useStore();

  const isGeneratingCurrentPaper =
    generatingNote && !!currentPaper && generatingNotePaperId === currentPaper.id;

  const [noteHtml, setNoteHtml] = useState('');
  const [editorValue, setEditorValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [streamHtml, setStreamHtml] = useState('');
  const noteViewRef = useRef<HTMLDivElement>(null);
  const streamRef = useRef<HTMLDivElement>(null);

  // Load notes list when paper changes
  useEffect(() => {
    if (!currentPaper) {
      setNotesList([]);
      setCurrentNoteId(null);
      setNoteHtml('');
      setOriginalNoteContent('');
      return;
    }
    setIsEditing(false);
    setNoteModified(false);

    api.fetchNotes(currentPaper.id).then((notes) => {
      setNotesList(notes);
      if (notes.length > 0) {
        setCurrentNoteId(notes[0].id);
      } else {
        setCurrentNoteId(null);
        setOriginalNoteContent('');
        setNoteHtml(
          '<div class="empty-state"><div class="icon">📝</div><div class="text">暂无笔记</div><div class="sub">点击 生成笔记 或 编辑 手动创建</div></div>',
        );
      }
    }).catch(() => {
      setNoteHtml('<div class="empty-state" style="color:#ef4444"><div class="text">加载笔记列表失败</div></div>');
    });
  }, [currentPaper?.id]);

  // Load note content when currentNoteId changes
  useEffect(() => {
    if (!currentNoteId) {
      if (notesList.length === 0 && currentPaper) {
        setNoteHtml(
          '<div class="empty-state"><div class="icon">📝</div><div class="text">暂无笔记</div><div class="sub">点击 生成笔记 或 编辑 手动创建</div></div>',
        );
      }
      return;
    }
    setIsEditing(false);
    setNoteModified(false);

    api.fetchNote(currentNoteId).then((data) => {
      setOriginalNoteContent(data.content || '');
      if (data.content) {
        setNoteHtml(renderMarkdown(data.content));
      } else {
        setNoteHtml(
          '<div class="empty-state"><div class="icon">📝</div><div class="text">笔记为空</div><div class="sub">点击 ✏️ 编辑 开始撰写</div></div>',
        );
      }
    }).catch(() => {
      setNoteHtml('<div class="empty-state" style="color:#ef4444"><div class="text">加载笔记内容失败</div></div>');
    });
  }, [currentNoteId]);

  // Highlight code blocks after HTML update
  useEffect(() => {
    if (noteViewRef.current && noteHtml) {
      highlightCodeBlocks(noteViewRef.current);
    }
  }, [noteHtml]);

  useEffect(() => {
    if (streamRef.current && streamHtml) {
      highlightCodeBlocks(streamRef.current);
    }
  }, [streamHtml]);

  const enterEditMode = useCallback(() => {
    if (!currentNoteId && notesList.length === 0) {
      // Create a new note first, then edit
      handleCreateNote('');
      return;
    }
    setIsEditing(true);
    setEditorValue(originalNoteContent);
  }, [originalNoteContent, setIsEditing, currentNoteId, notesList.length]);

  const exitEditMode = useCallback(() => {
    setIsEditing(false);
    setNoteModified(false);
  }, [setIsEditing, setNoteModified]);

  const handleSave = useCallback(async () => {
    if (!currentNoteId) return;
    setSaving(true);
    try {
      const data = await api.updateNote(currentNoteId, editorValue);
      if (data.success) {
        setOriginalNoteContent(editorValue);
        setNoteModified(false);
        setNoteHtml(renderMarkdown(editorValue));
        exitEditMode();
        notify('笔记已保存', 'success');
      } else {
        notify('保存失败: ' + (data.error || ''), 'error');
      }
    } catch {
      notify('保存失败: 网络错误', 'error');
    } finally {
      setSaving(false);
    }
  }, [currentNoteId, editorValue, exitEditMode, notify, setOriginalNoteContent, setNoteModified]);

  const handleCancel = useCallback(async () => {
    if (noteModified && !(await confirm('放弃未保存的更改？'))) return;
    exitEditMode();
  }, [noteModified, exitEditMode, confirm]);

  const handleCreateNote = useCallback(async (content: string = '') => {
    if (!currentPaper) return;
    try {
      const data = await api.createNote(currentPaper.id, content);
      if (data.success) {
        // Reload notes list
        const notes = await api.fetchNotes(currentPaper.id);
        setNotesList(notes);
        setCurrentNoteId(data.id);
        if (content === '') {
          // Enter edit mode for new empty note
          setOriginalNoteContent('');
          setIsEditing(true);
          setEditorValue('');
        }
        notify('新笔记已创建', 'success');
      }
    } catch (e: any) {
      notify('创建笔记失败: ' + e.message, 'error');
    }
  }, [currentPaper, setNotesList, setCurrentNoteId, setOriginalNoteContent, setIsEditing, notify]);

  const handleGenerate = useCallback(async () => {
    if (!currentPaper || isGeneratingCurrentPaper) return;
    setGeneratingNote(true);
    setGeneratingNotePaperId(currentPaper.id);
    setStreamHtml('');

    let fullText = '';

    try {
      await api.generateNoteStream(
        currentPaper.id,
        (text) => {
          fullText += text;
          setStreamHtml(renderMarkdown(fullText));
        },
        (noteId, title) => {
          // done — update notes list
          const newNote = { id: noteId, title, created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
          setNotesList([...notesList, newNote]);
          setCurrentNoteId(noteId);
        },
        (msg) => {
          throw new Error(msg);
        },
        noteModel,
      );

      setOriginalNoteContent(fullText);
      setNoteHtml(renderMarkdown(fullText));
      notify('笔记生成完成', 'success');
    } catch (e: any) {
      notify('笔记生成失败: ' + e.message, 'error');
      setNoteHtml(
        `<div class="empty-state" style="color:#ef4444"><div class="text">生成失败: ${e.message}</div></div>`,
      );
    } finally {
      setGeneratingNote(false);
      setGeneratingNotePaperId(null);
      setStreamHtml('');
    }
  }, [
    currentPaper,
    isGeneratingCurrentPaper,
    notesList,
    setGeneratingNote,
    setGeneratingNotePaperId,
    setOriginalNoteContent,
    setNotesList,
    setCurrentNoteId,
    notify,
  ]);

  const handleDelete = useCallback(async () => {
    if (!currentNoteId || !currentPaper) return;
    if (!(await confirm('确定删除该笔记？此操作不可撤销。'))) return;
    try {
      await api.deleteNote(currentNoteId);
      // Reload notes list
      const notes = await api.fetchNotes(currentPaper.id);
      setNotesList(notes);
      if (notes.length > 0) {
        setCurrentNoteId(notes[0].id);
      } else {
        setCurrentNoteId(null);
        setOriginalNoteContent('');
        setNoteHtml(
          '<div class="empty-state"><div class="icon">📝</div><div class="text">暂无笔记</div><div class="sub">点击 生成笔记 或 编辑 手动创建</div></div>',
        );
      }
      notify('笔记已删除', 'success');
    } catch (e: any) {
      notify('删除失败: ' + e.message, 'error');
    }
  }, [currentNoteId, currentPaper, confirm, notify, setNotesList, setCurrentNoteId, setOriginalNoteContent]);

  // Keyboard: Ctrl+S to save
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 's') {
        e.preventDefault();
        if (isEditing) handleSave();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isEditing, handleSave]);

  const hasNote = !!originalNoteContent;

  // Editor input handler
  const handleEditorChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const val = e.target.value;
      setEditorValue(val);
      setNoteModified(val !== originalNoteContent);
    },
    [originalNoteContent, setNoteModified],
  );

  const handleEditorKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const textarea = e.currentTarget;
      const s = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const newVal = textarea.value.substring(0, s) + '    ' + textarea.value.substring(end);
      setEditorValue(newVal);
      requestAnimationFrame(() => {
        textarea.selectionStart = textarea.selectionEnd = s + 4;
      });
    }
  }, []);

  return (
    <>
      {/* Unified Toolbar */}
      <div id="note-toolbar">
        {notesList.length > 0 && (
          <select
            className="note-select"
            value={currentNoteId ?? ''}
            onChange={(e) => {
              const id = Number(e.target.value);
              if (id) setCurrentNoteId(id);
            }}
          >
            {notesList.map((n) => (
              <option key={n.id} value={n.id}>{n.title}</option>
            ))}
          </select>
        )}
        <select
          className="note-select"
          value={noteModel}
          onChange={(e) => setNoteModel(e.target.value)}
          title="笔记生成模型"
        >
          {NOTE_MODELS.map((model) => (
            <option key={model} value={model}>{model}</option>
          ))}
        </select>
        {!isGeneratingCurrentPaper && !isEditing && (
          <>
            {notesList.length > 0 && (
              <button className="note-btn" onClick={() => handleCreateNote('')} title="新建笔记">＋</button>
            )}
            <button className="note-btn" onClick={enterEditMode}>
              {notesList.length === 0 && !currentNoteId ? '新建' : '编辑'}
            </button>
            {hasNote && currentNoteId && (
              <button className="note-btn danger" onClick={handleDelete}>
                删除
              </button>
            )}
            <button className="note-btn primary" onClick={handleGenerate}>
              生成
            </button>
          </>
        )}
        {isEditing && (
          <>
            <button className="note-btn primary" onClick={handleSave} disabled={saving}>
              💾 保存
            </button>
            <button className="note-btn danger" onClick={handleCancel}>
              ✕ 取消
            </button>
          </>
        )}
        <span id="note-status">
          {saving ? '保存中…' : isGeneratingCurrentPaper ? '⏳ 正在生成…' : noteModified ? '● 未保存' : ''}
        </span>
      </div>

      {/* Generating bar */}
      {isGeneratingCurrentPaper && (
        <>
          <div className="note-generating-bar">
            <div className="spinner" />
            AI 正在生成笔记，请稍候…
          </div>
          <div
            ref={streamRef}
            className="markdown-body"
            style={{ padding: '18px 20px', flex: 1, overflowY: 'auto' }}
            dangerouslySetInnerHTML={{ __html: streamHtml }}
          />
        </>
      )}

      {/* Note view */}
      {!isGeneratingCurrentPaper && !isEditing && (
        <div
          id="note-view"
          className="markdown-body"
          ref={noteViewRef}
          dangerouslySetInnerHTML={{ __html: noteHtml || '<div class="empty-state"><div class="icon">📝</div><div class="text">选择论文后查看笔记</div></div>' }}
        />
      )}

      {/* Editor */}
      {isEditing && (
        <div id="note-editor-wrapper" style={{ display: 'flex' }}>
          <textarea
            id="note-editor"
            placeholder={'在此编写 Markdown 笔记…\n\n支持 KaTeX 数学公式（$...$  $$...$$）、代码高亮等'}
            value={editorValue}
            onChange={handleEditorChange}
            onKeyDown={handleEditorKeyDown}
            autoFocus
          />
        </div>
      )}
    </>
  );
}
