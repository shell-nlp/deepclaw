# DeepClaw 本机助手

Electron + React + TypeScript 桌面客户端。智能体仍运行在服务器；本机助手通过主动建立的 WSS 连接接收操作，不需要开放电脑入站端口。

## 运行与打包

需要 Node.js 24 和 pnpm。首次安装需下载 Electron。

```powershell
cd desktop
pnpm install
pnpm dev
```

```powershell
pnpm build
pnpm test
pnpm package:dir  # 生成 release/win-unpacked
pnpm package:win  # 生成 Windows NSIS 安装程序并发布到服务端下载目录
```

安装包默认未签名，正式发布需在企业构建环境配置代码签名。当前提供 Windows x64 打包配置，并使用 electron-updater 完成用户主动更新。

打包后自动复制到仓库的 `.deepclaw/downloads/DeepClaw-Setup-x64.exe`，网页「我的设备」可直接下载。已有安装包可运行 `node scripts/publish-installer.mjs` 单独发布；远程或容器部署的文件挂载方式见 [设备执行设计](../docs/local-devices.md#下载安装)。

## 版本更新

安装版在配对后立即检查当前服务器，之后每小时检查一次。新版本通过界面和一次系统通知提示；点击系统通知仅打开助手，点击「更新并重启」才下载和安装。不点击就不下载，退出也不会自动安装。下载失败可重新检查后重试；下载校验通过后关闭本机访问、停止未完成任务，再安装并重启。开发模式不执行更新。

发布前递增 `package.json` 的版本并执行 `pnpm package:win`，脚本会发布版本化 EXE、blockmap 与 `updates/latest.yml`（包含 SHA-512），最后原子替换清单。不允许用不同安装包覆盖同一版本。服务端需部署整个 `.deepclaw/downloads` 目录并支持范围请求，更新 API 为 `/api/devices/updates/*`。更新源由配对服务器指定，构建配置中的 `updates.invalid` 仅用于生成更新器配置，客户端不会访问该占位地址。

0.1.0 / 0.1.1 尚无自动更新能力，需要先手动安装 0.1.2 或更新版本一次。

## 使用

1. 登录网页，进入「我的设备」，点击「下载 Windows 本机助手」并安装，再点击「连接新设备」。
2. 在本机助手输入服务器根地址、一次性配对码和设备名。
3. 添加授权目录，按需允许修改文件或运行命令，然后打开总开关。
4. 在网页聊天输入区选择这台设备，向智能体提出本机任务。
5. 在「操作审批」选择请求批准或完全访问权限。请求批准是默认模式，写入和命令逐次询问；完全访问自动执行已开启的能力。模式变更会停止未完成任务。

远端服务器必须使用 HTTPS，并支持 `/api/devices/connect` WebSocket 升级。仅回环地址允许 HTTP 开发连接。关闭窗口保留托盘；退出、重启、断线后授权自动关闭，重连不会自动开启。

文件工具受真实路径目录校验限制；**命令以当前操作系统账户权限运行，工作目录不等于系统沙箱**。完全访问仍受总开关、能力开关和文件目录校验约束，命令可能访问目录外文件或网络。模式偏好保存在本机，重启、断线后仍须手动开启总开关。详情见 [设备执行设计](../docs/local-devices.md)。
