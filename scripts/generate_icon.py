"""生成论文阅读器应用图标 (app.ico)"""
from PIL import Image, ImageDraw, ImageFont
import math

def generate_icon():
    sizes = [256, 128, 64, 48, 32, 16]
    images = []

    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 圆角背景
        pad = max(1, size // 16)
        r = size // 5
        bg_color = (108, 92, 231)  # 紫色
        # 简易圆角矩形
        draw.rounded_rectangle([pad, pad, size - pad - 1, size - pad - 1], radius=r, fill=bg_color)

        # 书本图标（简化几何绘制）
        cx, cy = size // 2, size // 2
        bw = int(size * 0.55)  # 书宽
        bh = int(size * 0.45)  # 书高
        spine_x = cx

        # 左页
        left = cx - bw // 2
        top = cy - bh // 2
        draw.polygon([
            (spine_x, top - size // 20),
            (left, top + size // 12),
            (left, top + bh),
            (spine_x, top + bh - size // 20),
        ], fill=(255, 255, 255, 230))

        # 右页
        right = cx + bw // 2
        draw.polygon([
            (spine_x, top - size // 20),
            (right, top + size // 12),
            (right, top + bh),
            (spine_x, top + bh - size // 20),
        ], fill=(220, 220, 255, 230))

        # 书页线
        line_color = (108, 92, 231, 180)
        lw = max(1, size // 64)
        for i in range(1, 4):
            ly = top + size // 12 + int((bh - size // 6) * i / 4.5)
            # 左侧线
            lx1 = left + size // 14
            lx2 = spine_x - size // 14
            if lx2 > lx1:
                draw.line([(lx1, ly), (lx2, ly)], fill=line_color, width=lw)
            # 右侧线
            rx1 = spine_x + size // 14
            rx2 = right - size // 14
            if rx2 > rx1:
                draw.line([(rx1, ly), (rx2, ly)], fill=line_color, width=lw)

        images.append(img)

    # 保存为 ICO
    images[0].save(
        "assets/app.ico",
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print(f"✅ 图标已生成: assets/app.ico ({len(sizes)} 种尺寸)")

if __name__ == "__main__":
    import os
    os.makedirs("assets", exist_ok=True)
    generate_icon()
