from __future__ import annotations

import sys
from pathlib import Path


def version_info(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError("version must contain three numeric components")
    numbers = ", ".join([*parts, "0"])
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({numbers}),
    prodvers=({numbers}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404b0',
        [
          StringStruct('CompanyName', 'Poggi-Tang'),
          StringStruct('FileDescription', 'MyBot2 Launcher'),
          StringStruct('FileVersion', '{version}'),
          StringStruct('InternalName', 'MyBot2'),
          StringStruct('LegalCopyright', 'Copyright (c) Poggi-Tang'),
          StringStruct('OriginalFilename', 'MyBot2.exe'),
          StringStruct('ProductName', 'MyBot2'),
          StringStruct('ProductVersion', '{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: generate_windows_version.py version output.txt")
    Path(sys.argv[2]).write_text(version_info(sys.argv[1]), encoding="utf-8")
