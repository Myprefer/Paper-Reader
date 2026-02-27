declare module 'marked' {
  export const marked: {
    parse(src: string): string;
    setOptions(options: Record<string, unknown>): void;
  };
}
