/**
 * Encode a file path for use in URLs.
 * Each segment is URI-encoded individually.
 */
export function encodePath(p: string): string {
  return p.split('/').map((s) => encodeURIComponent(s)).join('/');
}

/**
 * Find a node by paper ID in the tree (DFS).
 */
import type { TreeNode } from '../types';

export function findNodeById(tree: TreeNode | null, id: number): TreeNode | null {
  if (!tree) return null;
  if (tree.type === 'file' && tree.id === id) return tree;
  if (tree.children) {
    for (const child of tree.children) {
      const found = findNodeById(child, id);
      if (found) return found;
    }
  }
  return null;
}
