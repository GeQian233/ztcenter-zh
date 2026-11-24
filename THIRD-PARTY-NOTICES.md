# 第三方组件声明

本仓库的作者代码以 [MIT](LICENSE) 许可发布。以下组件由第三方提供，遵循各自的许可，
**不包含在本仓库中**（由构建脚本下载或用户自行安装）。

## ZeroTier One

- 提供方：ZeroTier, Inc.（https://www.zerotier.com/）
- 组件形式：Windows 安装包 `ZeroTierOne-<version>.msi`、服务 `zerotier-one_x64.exe`、虚拟网卡驱动
- 许可：Business Source License 1.1
  （https://github.com/zerotier/ZeroTierOne/blob/dev/LICENSE.txt）
- 与本项目的关系：
  - 本项目**不修改、不重新编译、不内嵌**其源码；
  - 仅通过官方本地 HTTP API（`127.0.0.1:9993`）与其服务通信；
  - 安装包在用户机器上调用官方 MSI 完成内核安装，属"安装"而非"再分发源码"。
- 分发注意：若你要公开分发内含官方 MSI 的安装包，请自行确认符合 BSL 1.1 与 ZeroTier 的商标政策，
  并随包附带其许可文本；更稳妥的做法是让安装程序在安装时从官方源下载。

## Python 依赖

| 组件 | 许可 | 用途 |
| --- | --- | --- |
| customtkinter | MIT | 界面控件与主题 |
| pystray | LGPL-3.0 | 系统托盘图标 |
| Pillow | HPND | 图标与位图生成 |
| PyInstaller | GPL-2.0（含例外条款，允许打包专有程序） | 打包为单文件 exe |

## 构建工具

| 组件 | 许可 | 用途 |
| --- | --- | --- |
| NSIS 3.10 | zlib/libpng | 生成 Windows 安装包 |

## 商标

ZeroTier® 是 ZeroTier, Inc. 的注册商标。本项目为**非官方第三方客户端**，
名称中提及 ZeroTier 仅用于说明兼容对象，不表示任何隶属、赞助或背书关系。
