#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deploy_vpn_tool.py — 一键把「IP + root 密码」变成可用的 Shadowsocks 2022 节点

用法：
    python deploy_vpn_tool.py --host 1.2.3.4 --password '你的root密码'
    python deploy_vpn_tool.py --host 1.2.3.4 --password 'xxx' --port 10086 --name my-node

流程：
    1. 预检：TCP 连通性测试（22 端口）——连不上直接警告，不浪费时间
    2. SSH 登录（paramiko）
    3. 安装 Xray（未装才装）
    4. 生成/复用 32 字节 SS2022 密钥，写入配置
    5. 校验配置 + 启动 + 开机自启 + 防火墙放行
    6. 服务器出海自测（curl google）
    7. 生成 ss:// 分享链接，保存到文件 + 打印
    （可选）8. 在线生成二维码（失败则提示用 v2rayN 导入）

依赖：pip install paramiko  （本机已装）
"""
import argparse
import base64
import json
import os
import secrets
import socket
import ssl
import sys
import time
import urllib.request

try:
    import paramiko
except ImportError:
    print("缺少 paramiko，请先: pip install paramiko")
    sys.exit(1)


def precheck(host, port=22, timeout=5):
    """TCP 连通性预检：IP 完全不可达时提前警告。"""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True, "可达"
    except Exception as e:
        return False, f"不可达: {type(e).__name__} {e}"


def connect(host, user, pwd, port=22, timeout=25):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    conn = {"hostname": host, "port": port, "username": user, "password": pwd,
            "timeout": timeout, "look_for_keys": False, "allow_agent": False}
    c.connect(**conn)
    return c


def run(c, cmd, timeout=120):
    print(f"\n$ {cmd}")
    print("-" * 60)
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    if out:
        print(out.rstrip())
    if err:
        print("[stderr]", err.rstrip())
    return out + err


def existing_ss_key(c, method):
    """若服务器已有相同方法的 SS 配置，复用其密码（重跑不破坏节点）。"""
    cmd = "cat /usr/local/etc/xray/config.json 2>/dev/null"
    _, stdout, _ = c.exec_command(cmd, timeout=15)
    raw = stdout.read().decode(errors="replace").strip()
    if not raw:
        return None
    try:
        cfg = json.loads(raw)
        for ib in cfg.get("inbounds", []):
            st = ib.get("settings", {})
            if ib.get("protocol") == "shadowsocks" and st.get("method") == method:
                return st.get("password")
    except Exception:
        pass
    return None


def try_qr(link, save_path):
    """在线生成二维码；失败返回 False（网络受限时用 v2rayN 导入即可）。"""
    try:
        import urllib.parse
        ctx = ssl._create_unverified_context()
        q = urllib.parse.quote(link, safe="")
        url = "https://api.qrserver.com/v1/create-qr-code/?size=400x400&data=" + q
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, context=ctx, timeout=20).read()
        if len(data) > 500:
            with open(save_path, "wb") as f:
                f.write(data)
            return True
    except Exception:
        pass
    return False


def china_reach_check(host, port, timeout=6):
    """部署后从本机（国内网络）测 SS 端口 TCP 连通性。
    通=大概率可用；不通=IP 很可能被墙（RackNerd 同况），提示换机。"""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True, "本机可达（大概率国内可用）"
    except Exception as e:
        return False, f"本机连不上: {type(e).__name__} {e}"


def deploy(host, user, pwd, port, method, name, qr=True):
    print("=" * 60)
    print(f"[0/7] 预检连通性 {host}:22")
    ok, msg = precheck(host)
    print("      " + msg)
    if not ok:
        print("[!] 服务器 IP 不可达。若国内无法连接，可能是 IP 被墙（与 RackNerd 同况），")
        print("    换 IP 或换机房后再试；无法通过部署解决。")
        return 1

    print(f"\n[1/7] SSH 登录 {host}")
    c = connect(host, user, pwd)
    print("      登录成功")

    print("\n[2/7] 安装 Xray（已装则跳过）")
    run(c, 'command -v xray >/dev/null 2>&1 || bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install', timeout=400)
    run(c, "command -v xray && xray version 2>&1 | head -1")

    print("\n[3/7] 生成/复用 SS2022 密钥并写配置")
    key = existing_ss_key(c, method)
    if key:
        print(f"      复用已有密钥（重跑不破坏节点）")
    else:
        key = base64.b64encode(secrets.token_bytes(32)).decode()
        print(f"      新生成 32 字节密钥")
    config = json.dumps({
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "listen": "0.0.0.0", "port": port, "protocol": "shadowsocks",
            "settings": {"method": method, "password": key, "network": "tcp,udp"},
        }],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}],
    })
    b64 = base64.b64encode(config.encode()).decode()
    run(c, f"echo '{b64}' | base64 -d > /usr/local/etc/xray/config.json")
    run(c, "xray run -test -config /usr/local/etc/xray/config.json && echo CONFIG_OK")

    print("\n[4/7] 启动 + 开机自启 + 防火墙")
    run(c, "systemctl enable xray 2>&1; systemctl restart xray; sleep 2; systemctl is-active xray")
    run(c, f"ufw allow {port}/tcp 2>&1; ufw allow {port}/udp 2>&1; ufw status 2>&1 | grep {port}")
    ensure_count_rules(c, port)

    print("\n[5/7] 监听 + 出海自测")
    run(c, f"ss -tln | grep {port} || echo NO_LISTEN")
    run(c, "curl -sI --max-time 10 https://www.google.com | head -1 || echo OUTBOUND_FAIL")

    print("\n[6/7] 生成 ss:// 链接")
    uri = f"{method}:{key}"
    ss_link = "ss://" + base64.urlsafe_b64encode(uri.encode()).decode().rstrip("=") + f"@{host}:{port}#{name}"
    info = (f"IP={host}\nPORT={port}\nMETHOD={method}\nKEY={key}\n"
            f"LINK={ss_link}\n")
    save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"ss_node_{host}.txt")
    with open(save_path, "w") as f:
        f.write(info)
    print("\n" + "=" * 60)
    print("[OK] 部署完成！节点信息（已保存到 %s）" % save_path)
    print(f"  地址   : {host}")
    print(f"  端口   : {port}")
    print(f"  方法   : {method}")
    print(f"  密码   : {key}")
    print(f"\n  SS链接 : {ss_link}")
    print("=" * 60)

    print("\n[7/7] 二维码 + 国内可达性预检")
    qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"qr_{host}.png")
    if qr and try_qr(ss_link, qr_path):
        print(f"  二维码已生成: {qr_path}")
    else:
        print("  在线二维码服务不可用 → 用 v2rayN 导入链接后右键节点生成二维码")

    reachable, msg = china_reach_check(host, port)
    print(f"  国内可达性: {msg}")
    if not reachable:
        print("[!] 警告：部署成功，但本机（国内）连不上该 SS 端口。")
        print("    若境外可连而国内不通，说明 IP 被墙（RackNerd 同况），")
        print("    需要换 IP / 换机房后重新部署，工具无法解决 IP 被墙。")
    else:
        print("  [OK] 国内网络可达，节点大概率可直接使用。")
    c.close()
    return 0


def fetch_config(c):
    _, out, _ = c.exec_command("cat /usr/local/etc/xray/config.json", timeout=15)
    raw = out.read().decode(errors="replace").strip()
    return json.loads(raw) if raw else None


def push_config(c, cfg):
    b64 = base64.b64encode(json.dumps(cfg).encode()).decode()
    run(c, f"echo '{b64}' | base64 -d > /usr/local/etc/xray/config.json")
    run(c, "xray run -test -config /usr/local/etc/xray/config.json && echo CONFIG_OK")
    run(c, "systemctl restart xray; sleep 2; systemctl is-active xray")


def rotate_ss(host, user, pwd, port, method="2022-blake3-aes-256-gcm", name="vpn-node", qr=True):
    """旋转密钥：同一端口换新密码，旧链接立即作废（服务器/端口保留）。"""
    print("=" * 60)
    print(f"[旋转密钥] {host}:{port}")
    c = connect(host, user, pwd)
    cfg = fetch_config(c)
    target = None
    for ib in cfg.get("inbounds", []):
        if ib.get("protocol") == "shadowsocks" and ib.get("port") == port:
            target = ib
            break
    if target is None:
        print(f"[!] 端口 {port} 没有 Shadowsocks 节点，无需旋转。")
        c.close()
        return 1
    key = base64.b64encode(secrets.token_bytes(32)).decode()
    target["settings"]["password"] = key
    push_config(c, cfg)
    uri = f"{method}:{key}"
    ss_link = "ss://" + base64.urlsafe_b64encode(uri.encode()).decode().rstrip("=") + f"@{host}:{port}#{name}"
    info = f"IP={host}\nPORT={port}\nMETHOD={method}\nKEY={key}\nLINK={ss_link}\n"
    save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"ss_node_{host}.txt")
    with open(save_path, "w") as f:
        f.write(info)
    print("[OK] 密钥已旋转，旧链接作废。新节点：")
    print(f"  地址: {host}:{port}  方法: {method}")
    print(f"  新密码: {key}")
    print(f"  新SS链接: {ss_link}")
    print(f"  已保存: {save_path}")
    qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"qr_{host}.png")
    if qr and try_qr(ss_link, qr_path):
        print(f"  新二维码: {qr_path}")
    else:
        print("  二维码服务不可用，用 v2rayN 导入链接生成。")
    c.close()
    return 0


def remove_ss(host, user, pwd, port):
    """删除节点：移除该端口的 Shadowsocks inbound + 关闭防火墙端口。"""
    print("=" * 60)
    print(f"[删除节点] {host}:{port}")
    c = connect(host, user, pwd)
    cfg = fetch_config(c)
    before = len(cfg.get("inbounds", []))
    kept = [ib for ib in cfg.get("inbounds", [])
            if not (ib.get("protocol") == "shadowsocks" and ib.get("port") == port)]
    if len(kept) == before:
        print(f"[!] 端口 {port} 没有 Shadowsocks 节点，无需删除。")
        c.close()
        return 1
    cfg["inbounds"] = kept
    push_config(c, cfg)
    run(c, f"ufw delete allow {port}/tcp 2>&1; ufw delete allow {port}/udp 2>&1; echo FIREWALL_CLOSED")
    remain = [ib.get("port") for ib in kept]
    print(f"[OK] 已删除端口 {port} 的节点。")
    print(f"  剩余节点端口: {remain if remain else '（无）'}")
    c.close()
    return 0


def list_ss(host, user, pwd):
    """列出该服务器上所有 Shadowsocks 节点（端口/方法/密码）。只读，不改任何配置。"""
    print("=" * 60)
    print(f"[节点列表] {host}")
    c = connect(host, user, pwd)
    cfg = fetch_config(c)
    inbounds = cfg.get("inbounds", [])
    ss = [ib for ib in inbounds if ib.get("protocol") == "shadowsocks"]
    if not ss:
        print("  该服务器没有 Shadowsocks 节点。")
        c.close()
        return 0
    for i, ib in enumerate(ss, 1):
        st = ib.get("settings", {})
        print(f"  {i}. 端口 {ib.get('port')} | 方法 {st.get('method')} | 密码 {st.get('password')} | 网络 {st.get('network')}")
    print("=" * 60)
    c.close()
    return 0


def deploy_append(host, user, pwd, port, method="2022-blake3-aes-256-gcm", name="vpn-node", qr=True):
    """追加模式：在现有配置上新增一个端口节点，保留原有所有节点（给家人/多用途各开一个端口）。"""
    print("=" * 60)
    print(f"[追加节点] {host}:{port}（保留现有节点）")
    c = connect(host, user, pwd)
    cfg = fetch_config(c)
    if cfg is None:
        cfg = {"log": {"loglevel": "warning"}, "inbounds": [],
               "outbounds": [{"protocol": "freedom", "tag": "direct"}]}
    existing = [ib.get("port") for ib in cfg.get("inbounds", [])]
    if port in existing:
        print(f"[!] 端口 {port} 已存在，未追加。现有端口: {existing}")
        c.close()
        return 1
    key = base64.b64encode(secrets.token_bytes(32)).decode()
    cfg["inbounds"].append({"listen": "0.0.0.0", "port": port, "protocol": "shadowsocks",
                            "settings": {"method": method, "password": key, "network": "tcp,udp"}})
    push_config(c, cfg)
    run(c, f"ufw allow {port}/tcp 2>&1; ufw allow {port}/udp 2>&1; echo FW_OK")
    ensure_count_rules(c, port)
    uri = f"{method}:{key}"
    ss_link = "ss://" + base64.urlsafe_b64encode(uri.encode()).decode().rstrip("=") + f"@{host}:{port}#{name}"
    save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"ss_node_{host}_{port}.txt")
    with open(save_path, "w") as f:
        f.write(f"IP={host}\nPORT={port}\nMETHOD={method}\nKEY={key}\nLINK={ss_link}\n")
    print(f"[OK] 已追加端口 {port}（现有节点全部保留）")
    print(f"  新节点: {host}:{port}  方法: {method}")
    print(f"  新密码: {key}")
    print(f"  新SS链接: {ss_link}")
    print(f"  已保存: {save_path}")
    qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"qr_{host}_{port}.png")
    if qr and try_qr(ss_link, qr_path):
        print(f"  新二维码: {qr_path}")
    else:
        print("  二维码服务不可用，用 v2rayN 导入链接生成。")
    reachable, msg = china_reach_check(host, port)
    print(f"  国内可达性: {msg}")
    c.close()
    return 0


def _fmt_bytes(n):
    n = int(n or 0)
    if n >= 2 ** 30:
        return "%.2f GB" % (n / 2 ** 30)
    if n >= 2 ** 20:
        return "%.1f MB" % (n / 2 ** 20)
    if n >= 2 ** 10:
        return "%.1f KB" % (n / 2 ** 10)
    return "%d B" % n


def ensure_count_rules(c, port):
    """为 SS 端口安装 iptables 计数规则（入站+出站），不存在才插入。"""
    c.exec_command(
        f"iptables -C INPUT -p tcp --dport {port} -j ACCEPT 2>/dev/null || iptables -I INPUT 1 -p tcp --dport {port} -j ACCEPT; "
        f"iptables -C OUTPUT -p tcp --sport {port} -j ACCEPT 2>/dev/null || iptables -I OUTPUT 1 -p tcp --sport {port} -j ACCEPT",
        timeout=20)


def traffic(host, user, pwd):
    """按节点（端口）统计流量：为每个 SS 端口加 iptables 计数规则并读取字节数。
    注意：计数从规则建立时刻起算（重启/删规则会清零）；整机总流量见 Vultr 面板/监控。"""
    print("=" * 60)
    print(f"[各节点流量] {host}")
    c = connect(host, user, pwd)
    cfg = fetch_config(c)
    ss_ports = [ib.get("port") for ib in cfg.get("inbounds", [])
                if ib.get("protocol") == "shadowsocks"]
    if not ss_ports:
        print("  该服务器没有 Shadowsocks 节点。")
        c.close()
        return 0
    # 确保每个端口有计数规则（不存在则插入，-j ACCEPT 兼具放行）
    for p in ss_ports:
        ensure_count_rules(c, p)
    _, out, _ = c.exec_command("iptables -L INPUT -n -v -x 2>/dev/null; echo '==OUT=='; iptables -L OUTPUT -n -v -x 2>/dev/null", timeout=30)
    raw = out.read().decode(errors="replace")
    in_lines, out_lines = raw.split("==OUT==") if "==OUT==" in raw else (raw, "")

    def count_for(lines, pat):
        for ln in lines.splitlines():
            if pat in ln:
                parts = ln.split()
                if len(parts) >= 2 and parts[0].isdigit():
                    return int(parts[0]), int(parts[1])
        return 0, 0

    print(f"  {'端口':<8}{'入站':<14}{'出站':<14}{'合计':<14}")
    for p in ss_ports:
        pk1, b1 = count_for(in_lines, f"dpt:{p}")
        pk2, b2 = count_for(out_lines, f"spt:{p}")
        print(f"  {p:<8}{_fmt_bytes(b1):<14}{_fmt_bytes(b2):<14}{_fmt_bytes(b1 + b2):<14}")
    print("  说明：计数自规则建立起算；重启后需重新查看才会重建规则并重新计数。")
    print("=" * 60)
    c.close()
    return 0
    c.close()
    return 0


def main():
    ap = argparse.ArgumentParser(description="一键把 IP+root密码 变成 Shadowsocks 2022 节点")
    ap.add_argument("--host", help="服务器 IP")
    ap.add_argument("--password", help="root 密码")
    ap.add_argument("--user", default="root", help="SSH 用户名（默认 root）")
    ap.add_argument("--port", type=int, default=10086, help="SS 端口（默认 10086）")
    ap.add_argument("--method", default="2022-blake3-aes-256-gcm", help="加密方法")
    ap.add_argument("--name", default="vpn-node", help="节点名称")
    ap.add_argument("--no-qr", action="store_true", help="跳过二维码")
    ap.add_argument("--batch", metavar="servers.json", help="批量部署：JSON 文件，内容为数组 [{host,password,port?,name?}, ...]")
    ap.add_argument("--rotate-ss", action="store_true", help="旋转密钥（换密码，旧链接作废），需 --host/--password/--port")
    ap.add_argument("--remove-ss", action="store_true", help="删除该端口节点 + 关防火墙，需 --host/--password/--port")
    ap.add_argument("--list-ss", action="store_true", help="列出该服务器所有 SS 节点（只读），需 --host/--password")
    ap.add_argument("--append-ss", action="store_true", help="追加模式：保留现有节点，新增一个端口节点，需 --host/--password/--port")
    ap.add_argument("--traffic", action="store_true", help="按节点（端口）统计流量，需 --host/--password")
    args = ap.parse_args()

    if args.traffic:
        host = args.host or input("服务器 IP: ").strip()
        pwd = args.password or input("root 密码: ").strip()
        sys.exit(traffic(host, args.user, pwd))
    if args.append_ss:
        host = args.host or input("服务器 IP: ").strip()
        pwd = args.password or input("root 密码: ").strip()
        sys.exit(deploy_append(host, args.user, pwd, args.port, args.method, args.name, qr=not args.no_qr))
    if args.list_ss:
        host = args.host or input("服务器 IP: ").strip()
        pwd = args.password or input("root 密码: ").strip()
        sys.exit(list_ss(host, args.user, pwd))

    if args.rotate_ss:
        host = args.host or input("服务器 IP: ").strip()
        pwd = args.password or input("root 密码: ").strip()
        sys.exit(rotate_ss(host, args.user, pwd, args.port, args.method, args.name, qr=not args.no_qr))
    if args.remove_ss:
        host = args.host or input("服务器 IP: ").strip()
        pwd = args.password or input("root 密码: ").strip()
        sys.exit(remove_ss(host, args.user, pwd, args.port))

    if args.batch:
        with open(args.batch, "r", encoding="utf-8") as f:
            servers = json.load(f)
        results = []
        for i, s in enumerate(servers, 1):
            host = s.get("host")
            pwd = s.get("password")
            if not host or not pwd:
                print(f"[{i}/{len(servers)}] 跳过（缺 host/password）: {s}")
                continue
            print(f"\n########## [{i}/{len(servers)}] 部署 {host} ##########")
            try:
                rc = deploy(host, s.get("user", "root"), pwd,
                            int(s.get("port", args.port)), s.get("method", args.method),
                            s.get("name", host), qr=not args.no_qr)
                results.append((host, "OK" if rc == 0 else f"rc={rc}"))
            except Exception as e:
                print(f"[ERROR] {host}: {e}")
                results.append((host, "ERROR"))
        print("\n" + "=" * 60)
        print("批量部署结果汇总：")
        for host, r in results:
            print(f"  {host}: {r}")
        print("=" * 60)
        return 0

    host = args.host or input("服务器 IP: ").strip()
    pwd = args.password or input("root 密码: ").strip()
    if not host or not pwd:
        print("IP 和密码必填")
        sys.exit(1)
    sys.exit(deploy(host, args.user, pwd, args.port, args.method, args.name, qr=not args.no_qr))


if __name__ == "__main__":
    main()
