# 开发期工具：为 .ps1 补回 UTF-8 BOM（PowerShell 5.1 按 GBK 解析无 BOM 的中文，会报语法错）
#
# 用法：python fix_ps1_bom.py <file1.ps1> [file2.ps1 ...]
# 规则：先循环剥掉所有前导 BOM，再写一个 —— 双 BOM 会让 PS 5.1 解析 param 块直接失败。
import sys

BOM = b"\xef\xbb\xbf"


def fix(path):
    with open(path, "rb") as f:
        data = f.read()
    while data.startswith(BOM):
        data = data[len(BOM):]
    with open(path, "wb") as f:
        f.write(BOM + data)
    print("bom ok:", path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python fix_ps1_bom.py <file.ps1> ...")
        sys.exit(1)
    for p in sys.argv[1:]:
        fix(p)
