# -*- coding: utf-8 -*-
"""VPN 一键部署工具（GUI 版）— 把 IP+root 密码变成 Shadowsocks 2022 节点"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deploy_vpn_tool as dvt


class LogWriter:
    def __init__(self, widget):
        self.widget = widget

    def write(self, s):
        self.widget.configure(state="normal")
        self.widget.insert("end", s)
        self.widget.see("end")
        self.widget.configure(state="disabled")
        return len(s)

    def flush(self):
        pass


def build_gui():
    root = tk.Tk()
    root.title("VPN 一键部署工具（IP -> Shadowsocks 2022）")
    root.geometry("720x560")
    root.minsize(640, 480)

    pad = {"padx": 8, "pady": 4}
    frm = ttk.Frame(root, padding=10)
    frm.pack(fill="x")

    def add_row(label, var, show=None, default=""):
        ttk.Label(frm, text=label, width=12).grid(row=len(rows), column=0, sticky="e", **pad)
        e = ttk.Entry(frm, textvariable=var, show=show, width=40)
        e.grid(row=len(rows), column=1, sticky="we", **pad)
        var.set(default)
        rows.append(e)
        return e

    rows = []
    v_host = tk.StringVar()
    v_pwd = tk.StringVar()
    v_port = tk.StringVar()
    v_name = tk.StringVar()
    v_action = tk.StringVar(value="部署（覆盖）")
    ttk.Label(frm, text="操作", width=12).grid(row=len(rows), column=0, sticky="e", **pad)
    act = ttk.Combobox(frm, textvariable=v_action, width=37, state="readonly",
                       values=["部署（覆盖）", "追加节点（保留现有）", "旋转密钥（旧链接作废）", "删除节点", "查看节点列表", "查看各节点流量"])
    act.grid(row=len(rows), column=1, sticky="we", **pad)
    rows.append("action")
    add_row("服务器 IP", v_host, default="")

    desc = tk.StringVar()
    desc_label = ttk.Label(root, textvariable=desc, foreground="#555", wraplength=680, justify="left")
    desc_label.pack(fill="x", padx=12, pady=(0, 4))

    def on_action(_e=None):
        desc.set({
            "部署（覆盖）": "部署（覆盖）：把服务器重设为【单个】新节点，覆盖原有配置、原节点失效。适合新服务器首次部署。",
            "追加节点（保留现有）": "追加节点：在服务器上【保留现有所有节点】的基础上，新增一个端口节点（独立新密码）。适合给家人/多用途各开一个端口。",
            "旋转密钥（旧链接作废）": "旋转密钥：同一端口换新密码，旧链接立即作废（服务器与节点保留）。适合节点泄露后快速换密码。",
            "删除节点": "删除节点：移除指定端口的节点并关闭该端口防火墙（同服务器其他节点不受影响）。",
            "查看节点列表": "查看节点列表：只读列出该服务器上所有 SS 节点（端口/方法/密码），不改动任何配置。",
            "查看各节点流量": "查看各节点流量：列出每个 SS 端口的入站/出站/合计字节数（自动安装 iptables 计数规则，从部署时起算）。",
        }.get(v_action.get(), ""))
    act.bind("<<ComboboxSelected>>", on_action)
    on_action()
    add_row("root 密码", v_pwd, show="*")
    add_row("SS 端口", v_port, default="10086")
    add_row("节点名称", v_name, default="vpn-node")

    log = scrolledtext.ScrolledText(root, state="disabled", height=20, wrap="word")
    log.pack(fill="both", expand=True, padx=10, pady=(0, 6))

    def start():
        host = v_host.get().strip()
        pwd = v_pwd.get().strip()
        port = v_port.get().strip()
        name = v_name.get().strip() or "vpn-node"
        action = v_action.get()
        if not host or not pwd:
            messagebox.showwarning("提示", "请填写服务器 IP 和 root 密码")
            return
        old = sys.stdout
        sys.stdout = LogWriter(log)

        def work():
            try:
                if action == "旋转密钥（旧链接作废）":
                    dvt.rotate_ss(host, "root", pwd, int(port), "2022-blake3-aes-256-gcm", name, qr=True)
                elif action == "删除节点":
                    dvt.remove_ss(host, "root", pwd, int(port))
                elif action == "查看节点列表":
                    dvt.list_ss(host, "root", pwd)
                elif action == "查看各节点流量":
                    dvt.traffic(host, "root", pwd)
                elif action == "追加节点（保留现有）":
                    dvt.deploy_append(host, "root", pwd, int(port), "2022-blake3-aes-256-gcm", name, qr=True)
                else:
                    dvt.deploy(host, "root", pwd, int(port), "2022-blake3-aes-256-gcm", name, qr=True)
            except Exception as e:
                print("[ERROR]", repr(e))
            finally:
                sys.stdout = old
                btn.config(state="normal")

        btn.config(state="disabled")
        log.configure(state="normal")
        log.delete("1.0", "end")
        log.configure(state="disabled")
        threading.Thread(target=work, daemon=True).start()

    btn = ttk.Button(root, text="开始执行", command=start)
    btn.pack(padx=10, pady=(0, 10))

    root.mainloop()


if __name__ == "__main__":
    build_gui()
