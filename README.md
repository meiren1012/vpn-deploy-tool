# VPN 一键部署工具（VPN One-Click Deployer）

把「境外服务器 IP + root 密码」一键变成可用的 **Shadowsocks 2022** 翻墙节点。不需要懂 Linux、不需要敲命令。

## 功能

- **一键部署**：自动测通 → SSH → 装 Xray → 配 SS2022 → 生成 ss:// 链接 + 二维码 + 存档
- **追加节点**：保留现有节点，给家人/多设备各开一个独立端口（独立密码）
- **旋转密钥**：节点泄露时一键换密码，旧链接立即作废
- **删除节点**：精确移除指定端口 + 关闭防火墙，其他节点不受影响
- **查看节点列表**：只读列出服务器上所有 SS 节点（端口/方法/密码）
- **各节点流量**：按端口统计入站/出站/合计（iptables 计数）
- **国内可达性预检**：部署后自动检测 IP 有没有被墙，提前提示换机
- **批量部署**：一个 JSON 文件一次部署多台服务器

## 环境要求

- Python 3.8+
- `pip install paramiko`（唯一的第三方依赖）
- Windows / macOS / Linux 均可（GUI 版需要 tkinter，Windows 自带）

## 使用

### 命令行

```bash
# 单台部署
python deploy_vpn_tool.py --host 1.2.3.4 --password 'root密码' --port 10086 --name my-node

# 追加节点（保留现有）
python deploy_vpn_tool.py --append-ss --host 1.2.3.4 --password 'root密码' --port 10087 --name family-1

# 旋转密钥（旧链接作废）
python deploy_vpn_tool.py --rotate-ss --host 1.2.3.4 --password 'root密码' --port 10086

# 删除节点
python deploy_vpn_tool.py --remove-ss --host 1.2.3.4 --password 'root密码' --port 10086

# 查看节点列表 / 各节点流量
python deploy_vpn_tool.py --list-ss --host 1.2.3.4 --password 'root密码'
python deploy_vpn_tool.py --traffic --host 1.2.3.4 --password 'root密码'

# 批量部署
python deploy_vpn_tool.py --batch servers.json
```

### 图形界面

```bash
python deploy_vpn_gui.py
```

顶部"操作"下拉选择要做的事（部署/追加/旋转/删除/列表/流量），每个操作都有说明文字。

## 输出

- `ss://` 分享链接（v2rayNG / Shadowrocket / 其它 SS 客户端直接导入）
- 二维码 PNG（可选，在线服务不可用时用客户端导入）
- 节点信息存档 `ss_node_<ip>.txt`

## 安全说明

- 代码中**不含任何密钥/密码**；root 密码只在运行时由你输入
- 只在你授权的服务器上操作（需要 IP + 密码才能动服务器）
- 重复部署会自动**复用已有密钥**，不破坏现有节点

## 工作原理（简要）

```
IP + root密码
  → SSH 登录服务器
  → 安装 Xray（未装才装）
  → 生成/复用 SS2022 32字节密钥，写配置（端口/method/password）
  → 启动 + 开机自启 + 防火墙放行 + iptables 计数规则
  → 服务器出海自测（curl google）
  → 生成 ss:// 链接（method:password@host:port）
  → 国内可达性预检（本机 TCP 测端口）
```

## 已知注意点

- **SS2022 密码必须是合法 32 字节 base64**（工具自动生成；手填非法值会导致 Xray 启动失败）
- **IP 被墙**（国内连不上、境外可连）无法靠部署解决，需换 IP/机房；工具的"国内可达性预检"会提前提示
- 服务器需为 Ubuntu / Debian（Debian 系）系统

## License

MIT © 陈奥奥
