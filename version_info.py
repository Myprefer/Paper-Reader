# UTF-8
#
# PyInstaller Windows Version Info
# 右键 PaperReader.exe → 属性 → 详细信息 中显示的元数据
#

VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=(1, 0, 0, 0),
        prodvers=(1, 0, 0, 0),
        mask=0x3F,
        flags=0x0,
        OS=0x40004,          # VOS_NT_WINDOWS32
        fileType=0x1,        # VFT_APP
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    '080404b0',   # 0804 = 简体中文, 04b0 = Unicode
                    [
                        StringStruct('CompanyName', 'Myprefer'),
                        StringStruct('FileDescription', 'PaperReader - AI 论文阅读与笔记工具'),
                        StringStruct('FileVersion', '1.0.0.0'),
                        StringStruct('InternalName', 'PaperReader'),
                        StringStruct('LegalCopyright', 'Copyright © 2026 Myprefer. All rights reserved.'),
                        StringStruct('OriginalFilename', 'PaperReader.exe'),
                        StringStruct('ProductName', 'PaperReader'),
                        StringStruct('ProductVersion', '1.0.0.0'),
                        StringStruct('LegalTrademarks', 'PaperReader is a trademark of Myprefer.'),
                    ],
                ),
            ],
        ),
        VarFileInfo([VarStruct('Translation', [0x0804, 1200])]),
    ],
)
