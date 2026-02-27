import { useCallback, useEffect, useState } from 'react';
import { getBackendUrl, setBackendUrl, testBackendConnection } from '../../api';
import { useStore } from '../../store/useStore';

export default function SettingsModal() {
  const { settingsOpen, setSettingsOpen, notify } = useStore();
  const [url, setUrl] = useState('');
  const [testing, setTesting] = useState(false);
  const [status, setStatus] = useState<'idle' | 'ok' | 'fail'>('idle');

  // 打开时读取当前值
  useEffect(() => {
    if (settingsOpen) {
      setUrl(getBackendUrl());
      setStatus('idle');
    }
  }, [settingsOpen]);

  const handleTest = useCallback(async () => {
    const target = url.trim();
    if (!target) {
      setStatus('idle');
      notify('URL 为空时将使用本机后端', 'info');
      return;
    }
    setTesting(true);
    setStatus('idle');
    const ok = await testBackendConnection(target);
    setStatus(ok ? 'ok' : 'fail');
    setTesting(false);
    notify(ok ? '连接成功' : '连接失败，请检查地址和网络', ok ? 'success' : 'error');
  }, [url, notify]);

  const handleSave = useCallback(() => {
    setBackendUrl(url);
    setSettingsOpen(false);
    notify('后端地址已保存，刷新页面后生效', 'success');
    // 自动刷新以应用新的后端地址
    setTimeout(() => window.location.reload(), 800);
  }, [url, setSettingsOpen, notify]);

  const handleClose = useCallback(() => {
    setSettingsOpen(false);
  }, [setSettingsOpen]);

  if (!settingsOpen) return null;

  return (
    <div className="modal-backdrop show" onClick={handleClose}>
      <div className="modal-box settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">⚙️ 设置</div>

        <div className="settings-section">
          <label className="settings-label">后端服务器地址</label>
          <p className="settings-hint">
            留空表示使用本机后端。填写远程地址可实现多设备同步（如 <code>http://192.168.1.100:5000</code>）。
          </p>
          <div className="settings-url-row">
            <input
              className="settings-input"
              type="text"
              value={url}
              onChange={(e) => { setUrl(e.target.value); setStatus('idle'); }}
              placeholder="http://服务器IP:端口"
              spellCheck={false}
            />
            <button
              className="modal-btn modal-btn-cancel settings-test-btn"
              onClick={handleTest}
              disabled={testing}
            >
              {testing ? '测试中...' : '测试连接'}
            </button>
          </div>
          {status === 'ok' && <span className="settings-status ok">✅ 连接成功</span>}
          {status === 'fail' && <span className="settings-status fail">❌ 连接失败</span>}
        </div>

        <div className="settings-info">
          <h4>💡 多设备同步使用说明</h4>
          <ol>
            <li>在一台电脑上运行后端服务：<code>python run.py --host 0.0.0.0 --port 5000</code></li>
            <li>在其他设备上，打开此应用的设置页面</li>
            <li>填入服务器的 IP 地址和端口（如 <code>http://192.168.1.100:5000</code>）</li>
            <li>测试连接成功后保存即可</li>
          </ol>
        </div>

        <div className="modal-actions">
          <button className="modal-btn modal-btn-cancel" onClick={handleClose}>取消</button>
          <button className="modal-btn modal-btn-primary" onClick={handleSave}>保存</button>
        </div>
      </div>
    </div>
  );
}
