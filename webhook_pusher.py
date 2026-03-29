# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import requests
import json
import os
import socket
import subprocess
import threading
import time
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from email.utils import formatdate

CONFIG_FILE = "webhook_config.json"

WPS_IMAGE_APP_ID = "AK20250402QYNRRO"
WPS_IMAGE_APP_KEY = "594bff6c82b608bc93ab0badcea472bd"

WPS_TEXT_TEMPLATE = '''{
  "msgtype": "text",
  "text": {
    "content": "这里是文本消息内容\\n可以@人：<at user_id=\\"12345\\">姓名</at>\\n@所有人：<at user_id=\\"-1\\">所有人</at>"
  }
}'''

WPS_MARKDOWN_TEMPLATE = '''{
  "msgtype": "markdown",
  "markdown": {
    "text": "## 标题\\n\\n**粗体文本** *斜体* ~~删除线~~\\n\\n> 引用内容\\n\\n- 列表项1\\n- 列表项2\\n\\n<font color='red'>红色文字</font>\\n\\n[链接名称](https://example.com)"
  }
}'''

WPS_LINK_TEMPLATE = '''{
  "msgtype": "link",
  "link": {
    "title": "链接标题",
    "text": "链接描述内容\\n支持多行",
    "messageUrl": "https://example.com",
    "btnTitle": "查看详情"
  }
}'''

WPS_CARD_TEMPLATE = '''{
  "msgtype": "card",
  "card": {
    "header": {
      "title": {
        "tag": "text",
        "content": {
          "type": "plainText",
          "text": "卡片标题"
        }
      },
      "subtitle": {
        "tag": "text",
        "content": {
          "type": "plainText",
          "text": "卡片副标题"
        }
      }
    },
    "elements": [
      {
        "tag": "text",
        "content": {
          "type": "markdown",
          "text": "卡片内容，支持**Markdown**格式"
        }
      }
    ]
  }
}'''

class WebhookPusher:
    def __init__(self, root):
        self.root = root
        self.root.title("Webhook 推送工具")
        self.root.geometry("800x800")
        self.root.resizable(True, True)
        
        self.config = self.load_config()
        self.session = requests.Session()
        
        self.schedule_thread = None
        self.schedule_running = False
        
        self.create_widgets()
        self.check_network_status()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def on_closing(self):
        if self.schedule_running:
            self.stop_schedule()
        self.save_current_config(show_message=False)
        self.root.destroy()
        
    def check_network_status(self):
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            self.log("网络状态: 已连接")
        except OSError:
            self.log("网络状态: 未连接或受限")
            
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        platform_frame = ttk.LabelFrame(main_frame, text="平台选择", padding="10")
        platform_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.platform_var = tk.StringVar(value=self.config.get("platform", "wps"))
        platforms = [("通用 Webhook", "generic"), ("WPS", "wps")]
        for i, (text, value) in enumerate(platforms):
            ttk.Radiobutton(platform_frame, text=text, value=value, 
                          variable=self.platform_var, 
                          command=self.on_platform_change).pack(side=tk.LEFT, padx=10)
        
        self.wps_type_frame = ttk.Frame(platform_frame)
        self.wps_type_frame.pack(side=tk.LEFT, padx=20)
        ttk.Label(self.wps_type_frame, text="WPS消息类型:").pack(side=tk.LEFT)
        self.wps_msg_type = tk.StringVar(value=self.config.get("msg_type", "text"))
        ttk.Radiobutton(self.wps_type_frame, text="文本", value="text", 
                       variable=self.wps_msg_type,
                       command=self.on_msg_type_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(self.wps_type_frame, text="Markdown", value="markdown", 
                       variable=self.wps_msg_type,
                       command=self.on_msg_type_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(self.wps_type_frame, text="链接", value="link", 
                       variable=self.wps_msg_type,
                       command=self.on_msg_type_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(self.wps_type_frame, text="卡片", value="card", 
                       variable=self.wps_msg_type,
                       command=self.on_msg_type_change).pack(side=tk.LEFT, padx=5)
        
        url_frame = ttk.LabelFrame(main_frame, text="Webhook URL", padding="10")
        url_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.pack(fill=tk.X)
        self.url_entry.insert(0, self.config.get("url", ""))
        
        content_frame = ttk.LabelFrame(main_frame, text="推送内容", padding="10")
        content_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.content_area = ttk.Frame(content_frame)
        self.content_area.pack(fill=tk.BOTH, expand=True)
        
        self.text_content_frame = ttk.Frame(self.content_area)
        self.text_content_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.text_content_frame, text="文本内容:").pack(anchor=tk.W)
        self.text_content = scrolledtext.ScrolledText(self.text_content_frame, height=6, wrap=tk.WORD)
        self.text_content.pack(fill=tk.BOTH, expand=True)
        self.text_content.insert("1.0", self.config.get("text_content", ""))
        
        self.link_content_frame = ttk.Frame(self.content_area)
        ttk.Label(self.link_content_frame, text="链接标题:").pack(anchor=tk.W)
        self.link_title = ttk.Entry(self.link_content_frame)
        self.link_title.pack(fill=tk.X, pady=(0, 5))
        self.link_title.insert(0, self.config.get("link_title", ""))
        
        ttk.Label(self.link_content_frame, text="链接描述:").pack(anchor=tk.W)
        self.link_desc = ttk.Entry(self.link_content_frame)
        self.link_desc.pack(fill=tk.X, pady=(0, 5))
        self.link_desc.insert(0, self.config.get("link_desc", ""))
        
        ttk.Label(self.link_content_frame, text="链接URL:").pack(anchor=tk.W)
        self.link_url = ttk.Entry(self.link_content_frame)
        self.link_url.pack(fill=tk.X)
        self.link_url.insert(0, self.config.get("link_url", ""))
        
        self.card_content_frame = ttk.Frame(self.content_area)
        ttk.Label(self.card_content_frame, text="卡片标题:").pack(anchor=tk.W)
        self.card_title = ttk.Entry(self.card_content_frame)
        self.card_title.pack(fill=tk.X, pady=(0, 5))
        self.card_title.insert(0, self.config.get("card_title", ""))
        
        ttk.Label(self.card_content_frame, text="卡片内容 (支持Markdown):").pack(anchor=tk.W)
        self.card_content = scrolledtext.ScrolledText(self.card_content_frame, height=4, wrap=tk.WORD)
        self.card_content.pack(fill=tk.BOTH, expand=True)
        self.card_content.insert("1.0", self.config.get("card_content", ""))
        
        self.on_msg_type_change()
        
        at_frame = ttk.LabelFrame(main_frame, text="@人功能 (WPS)", padding="10")
        at_frame.pack(fill=tk.X, pady=(0, 10))
        
        at_row1 = ttk.Frame(at_frame)
        at_row1.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(at_row1, text="用户ID:").pack(side=tk.LEFT)
        self.at_user_id = ttk.Entry(at_row1, width=20)
        self.at_user_id.pack(side=tk.LEFT, padx=(5, 10))
        
        ttk.Label(at_row1, text="姓名:").pack(side=tk.LEFT)
        self.at_user_name = ttk.Entry(at_row1, width=15)
        self.at_user_name.pack(side=tk.LEFT, padx=(5, 10))
        
        ttk.Button(at_row1, text="插入@人", command=self.insert_at_person).pack(side=tk.LEFT, padx=(5, 5))
        ttk.Button(at_row1, text="@所有人", command=self.insert_at_all).pack(side=tk.LEFT, padx=(5, 0))
        
        at_row2 = ttk.Frame(at_frame)
        at_row2.pack(fill=tk.X)
        
        ttk.Label(at_row2, text="常用联系人:").pack(side=tk.LEFT)
        self.at_favorite_combo = ttk.Combobox(at_row2, state="readonly", width=30)
        self.at_favorite_combo.pack(side=tk.LEFT, padx=(5, 10))
        ttk.Button(at_row2, text="插入", command=self.insert_favorite_person).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(at_row2, text="保存为常用", command=self.save_favorite_person).pack(side=tk.LEFT, padx=(5, 0))
        
        self.load_favorites()
        
        image_frame = ttk.LabelFrame(main_frame, text="图片推送 (WPS)", padding="10")
        image_frame.pack(fill=tk.X, pady=(0, 10))
        
        image_row = ttk.Frame(image_frame)
        image_row.pack(fill=tk.X)
        
        self.image_path_var = tk.StringVar(value=self.config.get("image_path", ""))
        ttk.Label(image_row, text="图片路径:").pack(side=tk.LEFT)
        image_entry = ttk.Entry(image_row, textvariable=self.image_path_var)
        image_entry.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        ttk.Button(image_row, text="选择图片", command=self.select_image).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(image_row, text="发送图片", command=self.send_image).pack(side=tk.LEFT, padx=(5, 0))
        
        proxy_frame = ttk.LabelFrame(main_frame, text="代理设置 (可选)", padding="10")
        proxy_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.use_proxy_var = tk.BooleanVar(value=self.config.get("use_proxy", False))
        ttk.Checkbutton(proxy_frame, text="使用代理", variable=self.use_proxy_var).pack(anchor=tk.W)
        
        proxy_input_frame = ttk.Frame(proxy_frame)
        proxy_input_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(proxy_input_frame, text="HTTP代理:").pack(side=tk.LEFT)
        self.http_proxy_entry = ttk.Entry(proxy_input_frame, width=25)
        self.http_proxy_entry.pack(side=tk.LEFT, padx=(5, 15))
        self.http_proxy_entry.insert(0, self.config.get("http_proxy", ""))
        
        ttk.Label(proxy_input_frame, text="HTTPS代理:").pack(side=tk.LEFT)
        self.https_proxy_entry = ttk.Entry(proxy_input_frame, width=25)
        self.https_proxy_entry.pack(side=tk.LEFT, padx=(5, 0))
        self.https_proxy_entry.insert(0, self.config.get("https_proxy", ""))
        
        ttk.Label(proxy_frame, text="示例: http://127.0.0.1:7890 或 socks5://127.0.0.1:1080").pack(anchor=tk.W)
        
        options_frame = ttk.LabelFrame(main_frame, text="高级选项", padding="10")
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(options_frame, text="自定义 Headers (JSON格式):").pack(anchor=tk.W)
        self.headers_entry = ttk.Entry(options_frame)
        self.headers_entry.pack(fill=tk.X, pady=(5, 0))
        self.headers_entry.insert(0, self.config.get("headers", '{"Content-Type": "application/json"}'))
        
        schedule_frame = ttk.LabelFrame(main_frame, text="定时推送设置", padding="10")
        schedule_frame.pack(fill=tk.X, pady=(0, 10))
        
        schedule_row1 = ttk.Frame(schedule_frame)
        schedule_row1.pack(fill=tk.X, pady=(0, 5))
        
        self.schedule_enabled = tk.BooleanVar(value=self.config.get("schedule_enabled", False))
        ttk.Checkbutton(schedule_row1, text="启用定时推送", variable=self.schedule_enabled).pack(side=tk.LEFT, padx=(0, 20))
        
        ttk.Label(schedule_row1, text="推送时间:").pack(side=tk.LEFT)
        
        self.schedule_times_entry = ttk.Entry(schedule_row1)
        self.schedule_times_entry.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        self.schedule_times_entry.insert(0, self.config.get("schedule_times", "09:00"))
        
        ttk.Label(schedule_row1, text="(如: 08:30,09:11)", foreground="gray").pack(side=tk.LEFT, padx=(5, 0))
        
        schedule_row2 = ttk.Frame(schedule_frame)
        schedule_row2.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(schedule_row2, text="推送类型:").pack(side=tk.LEFT)
        self.schedule_type = tk.StringVar(value=self.config.get("schedule_type", "text"))
        ttk.Radiobutton(schedule_row2, text="文本", value="text", variable=self.schedule_type).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(schedule_row2, text="图片", value="image", variable=self.schedule_type).pack(side=tk.LEFT, padx=5)
        
        schedule_row3 = ttk.Frame(schedule_frame)
        schedule_row3.pack(fill=tk.X)
        
        self.schedule_status = tk.StringVar(value="未启动")
        ttk.Label(schedule_row3, text="状态:").pack(side=tk.LEFT)
        ttk.Label(schedule_row3, textvariable=self.schedule_status, foreground="gray").pack(side=tk.LEFT, padx=(5, 0))
        
        self.schedule_btn = ttk.Button(schedule_row3, text="启动定时", command=self.toggle_schedule)
        self.schedule_btn.pack(side=tk.RIGHT)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.send_btn = ttk.Button(button_frame, text="发送推送", command=self.send_webhook)
        self.send_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(button_frame, text="测试连接", command=self.test_connection).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="网络诊断", command=self.diagnose_network).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="保存配置", command=self.save_current_config).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="清空日志", command=self.clear_log).pack(side=tk.LEFT, padx=(0, 10))
        
        log_frame = ttk.LabelFrame(main_frame, text="日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
    def diagnose_network(self):
        self.log("========== 网络诊断开始 ==========")
        
        self.log("\n[1] 检查基本网络连接...")
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            self.log("  ✓ 可以连接到8.8.8.8 (DNS服务器)")
        except Exception as e:
            self.log(f"  ✗ 无法连接到8.8.8.8: {e}")
        
        self.log("\n[2] 检查DNS解析...")
        test_domains = ["xz.wps.cn", "www.baidu.com", "www.qq.com"]
        for domain in test_domains:
            try:
                result = subprocess.run(["nslookup", domain], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    self.log(f"  ✓ {domain} DNS解析成功")
                else:
                    self.log(f"  ✗ {domain} DNS解析失败")
            except Exception as e:
                self.log(f"  ✗ {domain} DNS解析异常: {e}")
        
        self.log("\n[3] 检查Python DNS解析...")
        for domain in test_domains:
            try:
                ip = socket.gethostbyname(domain)
                self.log(f"  ✓ {domain} -> {ip}")
            except Exception as e:
                self.log(f"  ✗ {domain} Python解析失败: {e}")
        
        self.log("\n[4] 检查HTTPS连接...")
        test_urls = ["https://www.baidu.com", "https://xz.wps.cn"]
        for url in test_urls:
            try:
                proxies = self.get_proxies()
                r = requests.get(url, timeout=10, proxies=proxies)
                self.log(f"  ✓ {url} -> {r.status_code}")
            except Exception as e:
                self.log(f"  ✗ {url} 连接失败: {type(e).__name__}: {str(e)[:100]}")
        
        self.log("\n========== 网络诊断结束 ==========")
        
        messagebox.showinfo("诊断完成", "网络诊断已完成，请查看日志获取详细信息")
    
    def get_proxies(self) -> Optional[Dict[str, str]]:
        if not self.use_proxy_var.get():
            return None
        
        http_proxy = self.http_proxy_entry.get().strip()
        https_proxy = self.https_proxy_entry.get().strip()
        
        if not http_proxy and not https_proxy:
            return None
        
        proxies = {}
        if http_proxy:
            proxies["http"] = http_proxy
        if https_proxy:
            proxies["https"] = https_proxy
        
        return proxies
    
    def insert_template(self, msg_type: str):
        self.content_text.delete("1.0", tk.END)
        templates = {
            "text": WPS_TEXT_TEMPLATE,
            "markdown": WPS_MARKDOWN_TEMPLATE,
            "link": WPS_LINK_TEMPLATE,
            "card": WPS_CARD_TEMPLATE
        }
        template = templates.get(msg_type, WPS_TEXT_TEMPLATE)
        self.content_text.insert("1.0", template)
        self.wps_msg_type.set(msg_type)
    
    def on_msg_type_change(self):
        msg_type = self.wps_msg_type.get()
        
        self.text_content_frame.pack_forget()
        self.link_content_frame.pack_forget()
        self.card_content_frame.pack_forget()
        
        if msg_type in ["text", "markdown"]:
            self.text_content_frame.pack(fill=tk.BOTH, expand=True)
        elif msg_type == "link":
            self.link_content_frame.pack(fill=tk.X)
        elif msg_type == "card":
            self.card_content_frame.pack(fill=tk.BOTH, expand=True)
        
    def on_platform_change(self):
        platform = self.platform_var.get()
        if platform == "wps":
            self.wps_type_frame.pack(side=tk.LEFT, padx=20)
            self.headers_entry.delete(0, tk.END)
            self.headers_entry.insert(0, '{"Content-Type": "application/json"}')
        else:
            self.wps_type_frame.pack_forget()
            self.headers_entry.delete(0, tk.END)
            self.headers_entry.insert(0, self.config.get("headers", '{"Content-Type": "application/json"}'))
    
    def log(self, message: str):
        self.log_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def load_config(self) -> Dict[str, Any]:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def save_current_config(self, show_message=True):
        self.config["url"] = self.url_entry.get()
        self.config["platform"] = self.platform_var.get()
        self.config["msg_type"] = self.wps_msg_type.get()
        self.config["text_content"] = self.text_content.get("1.0", tk.END).strip()
        self.config["link_title"] = self.link_title.get()
        self.config["link_desc"] = self.link_desc.get()
        self.config["link_url"] = self.link_url.get()
        self.config["card_title"] = self.card_title.get()
        self.config["card_content"] = self.card_content.get("1.0", tk.END).strip()
        self.config["headers"] = self.headers_entry.get()
        self.config["use_proxy"] = self.use_proxy_var.get()
        self.config["http_proxy"] = self.http_proxy_entry.get()
        self.config["https_proxy"] = self.https_proxy_entry.get()
        self.config["schedule_enabled"] = self.schedule_enabled.get()
        self.config["schedule_times"] = self.schedule_times_entry.get()
        self.config["schedule_type"] = self.schedule_type.get()
        self.config["image_path"] = self.image_path_var.get()
        
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            self.log("配置已保存")
            if show_message:
                messagebox.showinfo("成功", "配置已保存")
        except Exception as e:
            self.log(f"保存配置失败: {str(e)}")
            if show_message:
                messagebox.showerror("错误", f"保存配置失败: {str(e)}")
    
    def test_connection(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("错误", "请输入 Webhook URL")
            return
        
        self.log(f"测试连接: {url}")
        proxies = self.get_proxies()
        if proxies:
            self.log(f"使用代理: {proxies}")
        
        try:
            response = requests.get(url, timeout=10, proxies=proxies)
            self.log(f"响应状态码: {response.status_code}")
            self.log(f"响应内容: {response.text[:500]}")
            
            if response.status_code == 404:
                messagebox.showwarning("警告", 
                    "返回404错误！\n\n可能原因：\n1. Webhook URL已失效\n2. 机器人已被删除\n3. URL格式不正确\n\n请在WPS群聊中重新获取Webhook地址")
            elif response.status_code == 200:
                messagebox.showinfo("成功", "连接测试成功！")
            else:
                messagebox.showinfo("信息", f"服务器返回状态码: {response.status_code}")
        except requests.exceptions.ConnectionError as e:
            self.log(f"连接失败: {str(e)[:200]}")
            messagebox.showerror("错误", 
                "无法连接到服务器\n\n可能原因：\n1. 网络未连接\n2. DNS解析失败\n3. 需要配置代理\n\n请点击\"网络诊断\"查看详情")
        except Exception as e:
            self.log(f"测试失败: {str(e)}")
            messagebox.showerror("错误", f"测试失败: {str(e)}")
    
    def build_payload(self) -> Dict[str, Any]:
        platform = self.platform_var.get()
        
        if platform == "wps":
            msg_type = self.wps_msg_type.get()
            
            if msg_type == "text":
                content = self.text_content.get("1.0", tk.END).strip()
                return {
                    "msgtype": "text",
                    "text": {
                        "content": content
                    }
                }
            elif msg_type == "markdown":
                content = self.text_content.get("1.0", tk.END).strip()
                return {
                    "msgtype": "markdown",
                    "markdown": {
                        "text": content
                    }
                }
            elif msg_type == "link":
                title = self.link_title.get().strip()
                desc = self.link_desc.get().strip()
                url = self.link_url.get().strip()
                return {
                    "msgtype": "link",
                    "link": {
                        "title": title,
                        "text": desc,
                        "messageUrl": url
                    }
                }
            elif msg_type == "card":
                title = self.card_title.get().strip()
                content = self.card_content.get("1.0", tk.END).strip()
                return {
                    "msgtype": "card",
                    "card": {
                        "header": {
                            "title": {
                                "tag": "text",
                                "content": {
                                    "type": "plainText",
                                    "text": title
                                }
                            }
                        },
                        "elements": [
                            {
                                "tag": "text",
                                "content": {
                                    "type": "markdown",
                                    "text": content
                                }
                            }
                        ]
                    }
                }
            else:
                content = self.text_content.get("1.0", tk.END).strip()
                return {
                    "msgtype": "text",
                    "text": {
                        "content": content
                    }
                }
        else:
            content = self.text_content.get("1.0", tk.END).strip()
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"content": content}
    
    def get_headers(self) -> Dict[str, str]:
        headers_str = self.headers_entry.get().strip()
        try:
            return json.loads(headers_str)
        except json.JSONDecodeError:
            return {"Content-Type": "application/json"}
    
    def send_webhook(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("错误", "请输入 Webhook URL")
            return
        
        msg_type = self.wps_msg_type.get()
        if msg_type in ["text", "markdown"]:
            content = self.text_content.get("1.0", tk.END).strip()
            if not content:
                messagebox.showerror("错误", "请输入推送内容")
                return
        elif msg_type == "link":
            if not self.link_title.get().strip():
                messagebox.showerror("错误", "请输入链接标题")
                return
            if not self.link_url.get().strip():
                messagebox.showerror("错误", "请输入链接URL")
                return
        elif msg_type == "card":
            if not self.card_title.get().strip():
                messagebox.showerror("错误", "请输入卡片标题")
                return
            if not self.card_content.get("1.0", tk.END).strip():
                messagebox.showerror("错误", "请输入卡片内容")
                return
        
        self.send_btn.config(state=tk.DISABLED)
        self.root.update()
        
        proxies = self.get_proxies()
        
        try:
            payload = self.build_payload()
            headers = self.get_headers()
            
            self.log(f"正在发送到: {url}")
            self.log(f"平台: {self.platform_var.get()}, 消息类型: {msg_type}")
            if proxies:
                self.log(f"使用代理: {proxies}")
            self.log(f"Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
            
            response = requests.post(
                url,
                headers=headers,
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                timeout=30,
                proxies=proxies
            )
            
            self.log(f"响应状态码: {response.status_code}")
            self.log(f"响应内容: {response.text}")
            
            if response.status_code == 200:
                try:
                    resp_json = response.json()
                    if resp_json.get("errcode", 0) == 0 or resp_json.get("code", 0) == 0:
                        self.log("发送成功!")
                        messagebox.showinfo("成功", "推送发送成功!")
                    else:
                        errmsg = resp_json.get("errmsg", "") or resp_json.get("msg", "未知错误")
                        self.log(f"发送失败: {errmsg}")
                        messagebox.showwarning("发送失败", f"错误信息: {errmsg}")
                except:
                    self.log("发送成功!")
                    messagebox.showinfo("成功", "推送发送成功!")
            elif response.status_code == 404:
                self.log("发送失败: 404 - Webhook地址无效")
                messagebox.showerror("发送失败", 
                    "404错误 - Webhook地址无效\n\n可能原因：\n1. 机器人已被删除\n2. URL已失效\n\n请在WPS群聊中重新获取Webhook地址")
            else:
                self.log(f"发送失败! 状态码: {response.status_code}")
                messagebox.showwarning("警告", f"推送发送完成，但返回状态码: {response.status_code}\n\n响应: {response.text[:200]}")
                
        except requests.exceptions.Timeout:
            self.log("发送失败: 请求超时")
            messagebox.showerror("错误", "请求超时，请检查网络连接")
        except requests.exceptions.ConnectionError as e:
            self.log(f"发送失败: 连接错误 - {str(e)[:100]}")
            messagebox.showerror("错误", 
                "连接错误\n\n可能原因：\n1. 网络未连接\n2. DNS解析失败\n3. 需要配置代理\n\n请点击\"网络诊断\"查看详情")
        except Exception as e:
            self.log(f"发送失败: {str(e)}")
            messagebox.showerror("错误", f"发送失败: {str(e)}")
        finally:
            self.send_btn.config(state=tk.NORMAL)
    
    def toggle_schedule(self):
        if self.schedule_running:
            self.stop_schedule()
        else:
            self.start_schedule()
    
    def get_valid_times(self):
        """获取有效时间列表"""
        time_text = self.schedule_times_entry.get().replace("，", ",").replace("：", ":")
        valid_times = []

        for t in time_text.split(','):
            t = t.strip()
            if not t:
                continue
            try:
                hour, minute = map(int, t.split(':'))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    valid_times.append(f"{hour:02}:{minute:02}")
            except ValueError:
                continue
        return valid_times
    
    def start_schedule(self):
        if not self.schedule_enabled.get():
            messagebox.showwarning("警告", "请先勾选\"启用定时推送\"")
            return
        
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("错误", "请先填写 Webhook URL")
            return
        
        schedule_type = self.schedule_type.get()
        if schedule_type == "text":
            content = self.content_text.get("1.0", tk.END).strip()
            if not content:
                messagebox.showerror("错误", "请先填写推送内容")
                return
        else:
            image_path = self.image_path_var.get().strip()
            if not image_path:
                messagebox.showerror("错误", "请先选择图片")
                return
            if not os.path.exists(image_path):
                messagebox.showerror("错误", "图片文件不存在")
                return
        
        valid_times = self.get_valid_times()
        if not valid_times:
            messagebox.showerror("错误", "请输入有效的推送时间格式\n示例: 09:00 或 08:30,09:11")
            return
        
        self.schedule_running = True
        self.schedule_btn.config(text="停止定时")
        self.schedule_status.set("运行中")
        self.schedule_times_entry.config(state=tk.DISABLED)
        type_name = "文本" if schedule_type == "text" else "图片"
        self.log(f"定时推送已启动，推送时间: {', '.join(valid_times)}，类型: {type_name}")
        
        self.schedule_thread = threading.Thread(target=self.schedule_loop, daemon=True)
        self.schedule_thread.start()
        
        self.save_current_config(show_message=False)
    
    def stop_schedule(self):
        self.schedule_running = False
        self.schedule_btn.config(text="启动定时")
        self.schedule_status.set("已停止")
        self.schedule_times_entry.config(state=tk.NORMAL)
        self.log("定时推送已停止")
    
    def schedule_loop(self):
        triggered_times = set()
        last_minute = -1
        
        while self.schedule_running:
            try:
                now = datetime.now()
                current_minute = now.minute
                
                if current_minute != last_minute:
                    triggered_times.clear()
                    last_minute = current_minute
                
                current_time_str = now.strftime("%H:%M")
                valid_times = self.get_valid_times()
                
                if current_time_str in valid_times and current_time_str not in triggered_times:
                    schedule_type = self.schedule_type.get()
                    self.log(f"定时推送触发，时间: {now.strftime('%Y-%m-%d %H:%M:%S')}，类型: {'图片' if schedule_type == 'image' else '文本'}")
                    
                    if schedule_type == "image":
                        self.root.after(0, self.send_image_silent)
                    else:
                        self.root.after(0, self.send_webhook_silent)
                    
                    triggered_times.add(current_time_str)
                
                time.sleep(1)
                
            except Exception as e:
                self.log(f"定时任务异常: {str(e)}")
                time.sleep(1)
    
    def send_webhook_silent(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        
        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            return
        
        proxies = self.get_proxies()
        
        try:
            payload = self.build_payload()
            headers = self.get_headers()
            
            response = requests.post(
                url,
                headers=headers,
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                timeout=30,
                proxies=proxies
            )
            
            if response.status_code == 200:
                self.log("定时推送发送成功!")
            else:
                self.log(f"定时推送失败: 状态码 {response.status_code}")
                
        except Exception as e:
            self.log(f"定时推送异常: {str(e)}")
    
    def send_image_silent(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        
        image_path = self.image_path_var.get().strip()
        if not image_path:
            return
        
        if not os.path.exists(image_path):
            return
        
        try:
            store_key = self.upload_image_to_wps(image_path)
            if not store_key:
                self.log("定时图片推送失败: 图片上传失败")
                return
            
            payload = {
                "msgtype": "card",
                "card": {
                    "elements": [
                        {
                            "tag": "img",
                            "content": {
                                "store_key": store_key
                            }
                        }
                    ]
                }
            }
            
            headers = {"Content-Type": "application/json"}
            proxies = self.get_proxies()
            
            response = requests.post(
                url,
                headers=headers,
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                timeout=30,
                proxies=proxies
            )
            
            if response.status_code == 200:
                self.log("定时图片推送发送成功!")
            else:
                self.log(f"定时图片推送失败: 状态码 {response.status_code}")
                
        except Exception as e:
            self.log(f"定时图片推送异常: {str(e)}")
    
    def load_favorites(self):
        """加载常用联系人"""
        favorites = self.config.get("at_favorites", [])
        self.at_favorite_combo['values'] = [f"{item['name']} ({item['user_id']})" for item in favorites]
        self.at_favorite_combo.user_ids = favorites
        if favorites:
            self.at_favorite_combo.current(0)
    
    def save_favorite_person(self):
        """保存当前用户为常用联系人"""
        user_id = self.at_user_id.get().strip()
        user_name = self.at_user_name.get().strip()
        
        if not user_id:
            messagebox.showwarning("警告", "请输入用户ID")
            return
        
        if not user_name:
            messagebox.showwarning("警告", "请输入姓名")
            return
        
        favorites = self.config.get("at_favorites", [])
        
        for i, item in enumerate(favorites):
            if item['user_id'] == user_id:
                favorites[i]['name'] = user_name
                break
        else:
            favorites.append({"user_id": user_id, "name": user_name})
        
        self.config["at_favorites"] = favorites
        self.load_favorites()
        self.save_current_config(show_message=False)
        self.log(f"已保存常用联系人: {user_name} ({user_id})")
        messagebox.showinfo("成功", f"已保存常用联系人: {user_name}")
    
    def insert_at_person(self):
        """插入@人标签"""
        user_id = self.at_user_id.get().strip()
        user_name = self.at_user_name.get().strip()
        
        if not user_id:
            messagebox.showwarning("警告", "请输入用户ID")
            return
        
        if not user_name:
            messagebox.showwarning("警告", "请输入姓名")
            return
        
        at_tag = f'<at user_id="{user_id}">{user_name}</at> '
        self.text_content.insert(tk.INSERT, at_tag)
        self.log(f"已插入@人标签: {user_name}")
    
    def insert_at_all(self):
        """插入@所有人标签"""
        at_tag = '<at user_id="-1">所有人</at> '
        self.text_content.insert(tk.INSERT, at_tag)
        self.log("已插入@所有人标签")
    
    def insert_favorite_person(self):
        """插入常用联系人"""
        current_index = self.at_favorite_combo.current()
        if current_index == -1:
            messagebox.showwarning("警告", "请先选择常用联系人")
            return
        
        favorites = self.at_favorite_combo.user_ids
        if current_index < len(favorites):
            item = favorites[current_index]
            at_tag = f'<at user_id="{item["user_id"]}">{item["name"]}</at> '
            self.text_content.insert(tk.INSERT, at_tag)
            self.log(f"已插入常用联系人: {item['name']}")
    
    def select_image(self):
        file_path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            self.image_path_var.set(file_path)
            self.log(f"已选择图片: {file_path}")
    
    def upload_image_to_wps(self, file_path: str) -> Optional[str]:
        """上传图片到WPS开放平台，返回store_key"""
        openapi_host = "https://openapi.wps.cn"
        app_id = WPS_IMAGE_APP_ID
        app_key = WPS_IMAGE_APP_KEY
        
        def generate_signature(content_md5: str, uri: str, date: str) -> str:
            sha1 = hashlib.sha1(app_key.lower().encode())
            sha1.update(content_md5.encode())
            sha1.update(uri.encode())
            sha1.update(b"application/json")
            sha1.update(date.encode())
            return f"WPS-3:{app_id}:{sha1.hexdigest()}"
        
        def make_request(method: str, uri: str, body: Optional[dict] = None) -> dict:
            content_md5 = hashlib.md5().hexdigest()
            if method in ["PUT", "POST", "DELETE"] and body:
                body_str = json.dumps(body) if isinstance(body, dict) else body
                content_md5 = hashlib.md5(body_str.encode()).hexdigest()
            
            date = formatdate(usegmt=True)
            signature = generate_signature(content_md5, uri, date)
            
            headers = {
                "Content-Type": "application/json",
                "X-Auth": signature,
                "Date": date,
                "Content-Md5": content_md5
            }
            
            url = f"{openapi_host}{uri}"
            response = requests.request(
                method, url,
                data=json.dumps(body) if body else None,
                headers=headers,
                verify=False
            )
            
            if response.status_code != 200:
                raise Exception(f"请求失败: {response.status_code} - {response.text}")
            return response.json()
        
        try:
            if not os.path.exists(file_path):
                raise Exception(f"文件不存在: {file_path}")
            
            # 获取企业令牌
            token_uri = f"/oauthapi/v3/inner/company/token?app_id={app_id}"
            token_data = make_request("GET", token_uri)
            company_token = token_data["company_token"]
            
            # 获取上传授权
            file_size = os.path.getsize(file_path)
            auth_uri = f"/kopen/woa/api/v2/developer/mime/upload?company_token={company_token}&service_key={app_id}&type=image&size={file_size}"
            auth_data = make_request("GET", auth_uri)
            
            if auth_data.get("result") != 0:
                raise Exception(f"获取授权失败: {auth_data.get('msg', '未知错误')}")
            
            # 执行文件上传
            with open(file_path, "rb") as f:
                response = requests.put(
                    url=auth_data["url"],
                    headers=auth_data["headers"],
                    data=f.read(),
                    verify=False
                )
            
            if not response.ok:
                raise Exception(f"上传失败: {response.status_code} - {response.text}")
            
            return auth_data["store_key"]
            
        except Exception as e:
            self.log(f"图片上传失败: {str(e)}")
            return None
    
    def send_image(self):
        """发送图片消息"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("错误", "请输入 Webhook URL")
            return
        
        image_path = self.image_path_var.get().strip()
        if not image_path:
            messagebox.showerror("错误", "请先选择图片")
            return
        
        if not os.path.exists(image_path):
            messagebox.showerror("错误", "图片文件不存在")
            return
        
        self.log("正在上传图片...")
        self.root.update()
        
        store_key = self.upload_image_to_wps(image_path)
        if not store_key:
            messagebox.showerror("错误", "图片上传失败，请查看日志")
            return
        
        self.log(f"图片上传成功，store_key: {store_key}")
        
        # 构造卡片消息
        payload = {
            "msgtype": "card",
            "card": {
                "elements": [
                    {
                        "tag": "img",
                        "content": {
                            "store_key": store_key
                        }
                    }
                ]
            }
        }
        
        self.log("正在发送图片消息...")
        
        try:
            headers = {"Content-Type": "application/json"}
            proxies = self.get_proxies()
            
            response = requests.post(
                url,
                headers=headers,
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                timeout=30,
                proxies=proxies
            )
            
            self.log(f"响应状态码: {response.status_code}")
            self.log(f"响应内容: {response.text}")
            
            if response.status_code == 200:
                self.log("图片发送成功!")
                messagebox.showinfo("成功", "图片发送成功!")
            else:
                self.log(f"图片发送失败: 状态码 {response.status_code}")
                messagebox.showwarning("发送失败", f"状态码: {response.status_code}\n响应: {response.text[:200]}")
                
        except Exception as e:
            self.log(f"图片发送失败: {str(e)}")
            messagebox.showerror("错误", f"发送失败: {str(e)}")

def main():
    root = tk.Tk()
    app = WebhookPusher(root)
    root.mainloop()

if __name__ == "__main__":
    main()
