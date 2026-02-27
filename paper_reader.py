"""
论文阅读器 —— 入口文件

后端采用 Flask + SQLite 架构，前端使用 React + TypeScript。
启动方式: python paper_reader.py [--host HOST] [--port PORT]
"""

import argparse

from backend.app import create_app
from backend.config import IMAGE_EN_DIR, IMAGE_ZH_DIR, NOTE_DIR, PDF_DIR, PDF_ZH_DIR

app = create_app()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="论文阅读器后端服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="监听端口 (默认: 5000)")
    parser.add_argument("--debug", action="store_true", default=False, help="调试模式")
    args = parser.parse_args()

    print("=" * 50)
    print("  📚 论文阅读器")
    print("=" * 50)
    print(f"  PDF目录:      {PDF_DIR.resolve()}")
    print(f"  中文PDF目录:  {PDF_ZH_DIR.resolve()}")
    print(f"  笔记目录:     {NOTE_DIR.resolve()}")
    print(f"  英文图片目录: {IMAGE_EN_DIR.resolve()}")
    print(f"  中文图片目录: {IMAGE_ZH_DIR.resolve()}")
    print(f"\n  🌐 访问 http://{args.host}:{args.port}")
    print(f"  💡 其他设备可通过 http://<本机IP>:{args.port} 访问")
    print("=" * 50)
    app.run(host=args.host, port=args.port, debug=args.debug)
