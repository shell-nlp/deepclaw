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

安装包默认未签名，正式发布需在企业构建环境配置代码签名。当前提供 Windows 打包配置，未接入自动更新。

打包后自动复制到仓库的 `.deepclaw/downloads/DeepClaw-Setup-x64.exe`，网页「我的设备」可直接下载。已有安装包可运行 `node scripts/publish-installer.mjs` 单独发布；远程或容器部署的文件挂载方式见 [设备执行设计](../docs/local-devices.md#下载安装)。

## 使用

1. 登录网页，进入「我的设备」，点击「下载 Windows 本机助手」并安装，再点击「连接新设备」。
2. 在本机助手输入服务器根地址、一次性配对码和设备名。
3. 添加授权目录，按需允许修改文件或运行命令，然后打开总开关。
4. 在网页聊天输入区选择这台设备，向智能体提出本机任务。
5. 写入和命令在本机展示完整参数，批准后才执行；可以拒绝或停止。

远端服务器必须使用 HTTPS，并支持 `/api/devices/connect` WebSocket 升级。仅回环地址允许 HTTP 开发连接。关闭窗口保留托盘；退出、重启、断线后授权自动关闭，重连不会自动开启。

文件工具受真实路径目录校验限制；**命令以当前操作系统账户权限运行，工作目录不等于系统沙箱**。只有了解程序和参数时才批准命令。详情见 [设备执行设计](../docs/local-devices.md)。
