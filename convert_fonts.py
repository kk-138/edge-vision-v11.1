import os, glob
from fontTools.ttLib import TTFont

SRC_DIR = "fonts_src"
OUT_DIR = os.path.join("static", "fonts")
os.makedirs(OUT_DIR, exist_ok=True)

files = sorted(glob.glob(os.path.join(SRC_DIR, "*.otf")) + glob.glob(os.path.join(SRC_DIR, "*.ttf")))
if not files:
    print("fonts_src/ 裡找不到 .otf 或 .ttf")

for path in files:
    base = os.path.splitext(os.path.basename(path))[0]
    base = base.replace("TW", "")          # GenYoMin2TW-R -> GenYoMin2-R
    font = TTFont(path)
    font.flavor = "woff2"
    out_path = os.path.join(OUT_DIR, f"{base}.woff2")
    font.save(out_path)
    print(f"已輸出：{out_path}（{os.path.getsize(out_path)/1024/1024:.1f} MB）")

print("完成！")
