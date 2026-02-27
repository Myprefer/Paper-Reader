import { useCallback } from 'react';
import { useStore } from '../store/useStore';

/**
 * 返回一个 confirm 函数，调用后弹出自定义确认对话框。
 * 用法：const confirm = useConfirm();
 *       if (await confirm('确定删除？')) { ... }
 */
export function useConfirm() {
  const showConfirm = useStore((s) => s.showConfirm);

  return useCallback(
    (message: string, title?: string): Promise<boolean> => {
      return new Promise((resolve) => {
        showConfirm(message, resolve, title);
      });
    },
    [showConfirm],
  );
}
