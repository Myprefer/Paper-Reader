import { useState, useEffect, useRef } from 'react';
import { useStore } from '../../store/useStore';

export default function Notification() {
  const notification = useStore((s) => s.notification);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [visible, setVisible] = useState(false);
  const [msg, setMsg] = useState('');
  const [type, setType] = useState<string>('info');

  useEffect(() => {
    if (!notification) return;
    clearTimeout(timerRef.current);
    setMsg(notification.msg);
    setType(notification.type);
    setVisible(true);
    timerRef.current = setTimeout(() => setVisible(false), 2500);
  }, [notification]);

  return (
    <div
      id="notification"
      className={`${type}${visible ? ' show' : ''}`}
    >
      {msg}
    </div>
  );
}
