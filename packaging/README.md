# Windows EXE 构建

在 Windows x64 的隔离虚拟环境中安装项目依赖和 PyInstaller，在仓库根目录执行：

```powershell
python -m pip install -e ".[dev]" pyinstaller
python -m PyInstaller --noconfirm packaging/LifeOS.spec
```

产物位于 `dist/LifeOS.exe`。spec 将 `migrations/` 与运行时依赖一起打入单文件；首次初始化或升级需用户明确同意，旧库升级前自动备份。用户可以使用 `LIFEOS_DATA_DIR` 覆盖数据目录。

在独立 PowerShell 会话中设置 `$env:LIFEOS_BUILD_PREVIEW = '1'` 后运行相同构建命令，生成 `dist/LifeOS-Preview.exe`。该程序默认使用 `%LOCALAPPDATA%\LifeOS Preview\data\`，也可通过 `LIFEOS_DATA_DIR` 指向要验证的旧库副本。

构建环境的 PATH 若包含与系统 ICU 不兼容的第三方 ICU DLL，PyInstaller 可能误收集它并造成 Qt 加载失败。此机器上的 Codex Poppler 目录存在此问题；构建时需仅在构建进程中从 PATH 移除对应目录，并验证 EXE，不能改动系统 DLL。

必须在独立临时数据目录验证首次启动、取消、升级和任务持久化，不使用正式库。当前构建在 Windows 11 x64 验证；并不代表其他平台已验证。
