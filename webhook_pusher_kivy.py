# -*- coding: utf-8 -*-
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.uix.popup import Popup
from kivy.uix.togglebutton import ToggleButton
from kivy.clock import Clock
from kivy.properties import StringProperty, BooleanProperty, ListProperty
from kivy.core.image import Image as CoreImage

import requests
import json
import os
import socket
import threading
import time
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any
from email.utils import formatdate

try:
    from android.permissions import request_permissions, Permission
    from android.storage import primary_external_storage_path
    ANDROID = True
except ImportError:
    ANDROID = False

CONFIG_FILE = "webhook_config.json"

WPS_IMAGE_APP_ID = "AK20250402QYNRRO"
WPS_IMAGE_APP_KEY = "594bff6c82b608bc93ab0badcea472bd"


class WebhookCore:
    def __init__(self):
        self.session = requests.Session()
        self.config = self.load_config()
        self.schedule_running = False
        self.schedule_thread = None
        
    def load_config(self) -> Dict[str, Any]:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def save_config(self, config: Dict[str, Any]):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            return False
    
    def get_proxies(self, use_proxy: bool, http_proxy: str, https_proxy: str) -> Optional[Dict[str, str]]:
        if not use_proxy:
            return None
        proxies = {}
        if http_proxy:
            proxies["http"] = http_proxy
        if https_proxy:
            proxies["https"] = https_proxy
        return proxies if proxies else None
    
    def generate_wps_sign(self, timestamp: str) -> str:
        sign_str = f"{WPS_IMAGE_APP_ID}{timestamp}{WPS_IMAGE_APP_KEY}"
        return hashlib.md5(sign_str.encode()).hexdigest()
    
    def send_wps_text(self, url: str, content: str, msg_type: str = "text", proxies=None) -> Dict:
        if msg_type == "markdown":
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "text": content
                }
            }
        else:
            payload = {
                "msgtype": "text",
                "text": {
                    "content": content
                }
            }
        
        headers = {"Content-Type": "application/json"}
        response = self.session.post(url, json=payload, headers=headers, proxies=proxies, timeout=30)
        return {"status_code": response.status_code, "text": response.text}
    
    def send_wps_link(self, url: str, title: str, desc: str, link_url: str, proxies=None) -> Dict:
        payload = {
            "msgtype": "link",
            "link": {
                "title": title,
                "text": desc,
                "messageUrl": link_url,
                "btnTitle": "查看详情"
            }
        }
        headers = {"Content-Type": "application/json"}
        response = self.session.post(url, json=payload, headers=headers, proxies=proxies, timeout=30)
        return {"status_code": response.status_code, "text": response.text}
    
    def send_wps_card(self, url: str, title: str, content: str, proxies=None) -> Dict:
        payload = {
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
        headers = {"Content-Type": "application/json"}
        response = self.session.post(url, json=payload, headers=headers, proxies=proxies, timeout=30)
        return {"status_code": response.status_code, "text": response.text}
    
    def send_wps_image(self, url: str, image_path: str, proxies=None) -> Dict:
        if not os.path.exists(image_path):
            return {"error": f"图片文件不存在: {image_path}"}
        
        timestamp = formatdate(localtime=True)
        sign = self.generate_wps_sign(timestamp)
        
        headers = {
            "AppId": WPS_IMAGE_APP_ID,
            "Stamp": timestamp,
            "Sign": sign
        }
        
        with open(image_path, 'rb') as f:
            files = {'file': f}
            response = self.session.post(url, files=files, headers=headers, proxies=proxies, timeout=60)
        
        return {"status_code": response.status_code, "text": response.text}
    
    def send_generic_webhook(self, url: str, content: str, headers: dict, proxies=None) -> Dict:
        try:
            headers_dict = json.loads(headers) if isinstance(headers, str) else headers
        except:
            headers_dict = {"Content-Type": "application/json"}
        
        response = self.session.post(url, data=content, headers=headers_dict, proxies=proxies, timeout=30)
        return {"status_code": response.status_code, "text": response.text}
    
    def test_connection(self, url: str, proxies=None) -> Dict:
        try:
            response = self.session.get(url, proxies=proxies, timeout=10)
            return {"status_code": response.status_code, "text": response.text}
        except Exception as e:
            return {"error": str(e)}


class MainScreen(BoxLayout):
    log_text = StringProperty("")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.core = WebhookCore()
        self.orientation = 'vertical'
        self.padding = 10
        self.spacing = 10
        
        self.platform = 'wps'
        self.msg_type = 'text'
        
        self.build_ui()
        self.load_config()
        
        if ANDROID:
            request_permissions([
                Permission.INTERNET,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE
            ])
    
    def build_ui(self):
        self.add_widget(Label(text="Webhook 推送工具", font_size=24, size_hint_y=None, height=50))
        
        platform_row = BoxLayout(size_hint_y=None, height=40, spacing=10)
        platform_row.add_widget(Label(text="平台:", size_hint_x=0.2))
        self.platform_spinner = Spinner(
            text='WPS',
            values=['WPS', '通用 Webhook'],
            size_hint_x=0.8
        )
        self.platform_spinner.bind(text=self.on_platform_change)
        platform_row.add_widget(self.platform_spinner)
        self.add_widget(platform_row)
        
        msg_type_row = BoxLayout(size_hint_y=None, height=40, spacing=5)
        msg_type_row.add_widget(Label(text="类型:", size_hint_x=0.15))
        self.msg_type_spinner = Spinner(
            text='文本',
            values=['文本', 'Markdown', '链接', '卡片'],
            size_hint_x=0.85
        )
        self.msg_type_spinner.bind(text=self.on_msg_type_change)
        msg_type_row.add_widget(self.msg_type_spinner)
        self.add_widget(msg_type_row)
        
        url_row = BoxLayout(size_hint_y=None, height=40, spacing=10)
        url_row.add_widget(Label(text="URL:", size_hint_x=0.1))
        self.url_input = TextInput(hint_text='Webhook URL', multiline=False)
        url_row.add_widget(self.url_input)
        self.add_widget(url_row)
        
        self.content_label = Label(text="内容:", size_hint_y=None, height=30, halign='left')
        self.content_label.bind(size=self.content_label.setter('text_size'))
        self.add_widget(self.content_label)
        
        self.content_input = TextInput(hint_text='输入推送内容', multiline=True)
        self.add_widget(self.content_input)
        
        self.link_container = BoxLayout(orientation='vertical', spacing=5, size_hint_y=None, height=120)
        self.link_title_input = TextInput(hint_text='链接标题', multiline=False, size_hint_y=None, height=40)
        self.link_desc_input = TextInput(hint_text='链接描述', multiline=False, size_hint_y=None, height=40)
        self.link_url_input = TextInput(hint_text='链接URL', multiline=False, size_hint_y=None, height=40)
        self.link_container.add_widget(self.link_title_input)
        self.link_container.add_widget(self.link_desc_input)
        self.link_container.add_widget(self.link_url_input)
        
        self.card_container = BoxLayout(orientation='vertical', spacing=5, size_hint_y=None, height=80)
        self.card_title_input = TextInput(hint_text='卡片标题', multiline=False, size_hint_y=None, height=40)
        self.card_content_input = TextInput(hint_text='卡片内容 (支持Markdown)', multiline=True, size_hint_y=None, height=80)
        self.card_container.add_widget(self.card_title_input)
        self.card_container.add_widget(self.card_content_input)
        
        image_row = BoxLayout(size_hint_y=None, height=40, spacing=10)
        image_row.add_widget(Label(text="图片:", size_hint_x=0.1))
        self.image_input = TextInput(hint_text='图片路径', multiline=False)
        image_row.add_widget(self.image_input)
        self.select_image_btn = Button(text="选择", size_hint_x=0.2)
        self.select_image_btn.bind(on_press=self.select_image)
        image_row.add_widget(self.select_image_btn)
        self.add_widget(image_row)
        
        proxy_row = BoxLayout(size_hint_y=None, height=40, spacing=10)
        self.use_proxy_cb = CheckBox(active=False, size_hint_x=0.1)
        proxy_row.add_widget(self.use_proxy_cb)
        proxy_row.add_widget(Label(text="使用代理", size_hint_x=0.2))
        self.proxy_input = TextInput(hint_text='代理地址 (如 http://127.0.0.1:7890)', multiline=False, size_hint_x=0.7)
        proxy_row.add_widget(self.proxy_input)
        self.add_widget(proxy_row)
        
        schedule_row = BoxLayout(size_hint_y=None, height=40, spacing=10)
        self.schedule_cb = CheckBox(active=False, size_hint_x=0.1)
        schedule_row.add_widget(self.schedule_cb)
        schedule_row.add_widget(Label(text="定时推送", size_hint_x=0.2))
        self.schedule_time_input = TextInput(hint_text='时间 (如 09:00,18:00)', multiline=False, size_hint_x=0.7)
        schedule_row.add_widget(self.schedule_time_input)
        self.add_widget(schedule_row)
        
        btn_row = BoxLayout(size_hint_y=None, height=50, spacing=10)
        
        send_btn = Button(text="发送", background_color=(0.2, 0.6, 0.2, 1))
        send_btn.bind(on_press=self.send_webhook)
        btn_row.add_widget(send_btn)
        
        test_btn = Button(text="测试连接")
        test_btn.bind(on_press=self.test_connection)
        btn_row.add_widget(test_btn)
        
        save_btn = Button(text="保存配置")
        save_btn.bind(on_press=self.save_config)
        btn_row.add_widget(save_btn)
        
        clear_btn = Button(text="清空日志")
        clear_btn.bind(on_press=self.clear_log)
        btn_row.add_widget(clear_btn)
        
        self.add_widget(btn_row)
        
        log_label = Label(text="日志:", size_hint_y=None, height=30, halign='left')
        log_label.bind(size=log_label.setter('text_size'))
        self.add_widget(log_label)
        
        scroll = ScrollView()
        self.log_label = Label(
            text="",
            size_hint_y=None,
            valign='top',
            halign='left',
            text_size=(None, None)
        )
        self.log_label.bind(texture_size=self.log_label.setter('size'))
        scroll.add_widget(self.log_label)
        self.add_widget(scroll)
        
        self.toggle_content_view()
    
    def toggle_content_view(self):
        if hasattr(self, 'link_container') and self.link_container.parent:
            self.remove_widget(self.link_container)
        if hasattr(self, 'card_container') and self.card_container.parent:
            self.remove_widget(self.card_container)
        if hasattr(self, 'content_input') and self.content_input.parent:
            pass
        else:
            idx = 4
            self.add_widget(self.content_input, index=len(self.children) - idx)
        
        msg_type = self.msg_type
        if msg_type in ['text', 'markdown']:
            self.content_label.text = "内容:"
            self.content_input.hint_text = '输入推送内容'
            self.content_input.disabled = False
        elif msg_type == 'link':
            self.content_input.disabled = True
            self.content_label.text = "链接信息:"
            self.add_widget(self.link_container)
        elif msg_type == 'card':
            self.content_label.text = "卡片信息:"
            self.content_input.disabled = True
            self.add_widget(self.card_container)
    
    def on_platform_change(self, spinner, text):
        self.platform = 'wps' if text == 'WPS' else 'generic'
        if self.platform == 'generic':
            self.msg_type_spinner.disabled = True
        else:
            self.msg_type_spinner.disabled = False
    
    def on_msg_type_change(self, spinner, text):
        type_map = {'文本': 'text', 'Markdown': 'markdown', '链接': 'link', '卡片': 'card'}
        self.msg_type = type_map.get(text, 'text')
        self.toggle_content_view()
    
    def select_image(self, instance):
        if ANDROID:
            try:
                from android.storage import primary_external_storage_path
                storage = primary_external_storage_path()
                from plyer import filechooser
                filechooser.open_file(path=storage, filters=[['*.jpg', '*.png', '*.jpeg', '*.gif']])
            except:
                self.log("请在输入框中手动输入图片路径")
        else:
            self.log("请在输入框中输入图片路径")
    
    def log_msg(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_log = f"[{timestamp}] {message}\n"
        self.log_text = new_log + self.log_text
        self.log_label.text = self.log_text
    
    def clear_log(self, instance):
        self.log_text = ""
        self.log_label.text = ""
    
    def load_config(self):
        config = self.core.config
        if config.get('url'):
            self.url_input.text = config['url']
        if config.get('text_content'):
            self.content_input.text = config['text_content']
        if config.get('image_path'):
            self.image_input.text = config['image_path']
        if config.get('use_proxy'):
            self.use_proxy_cb.active = config['use_proxy']
        if config.get('http_proxy'):
            self.proxy_input.text = config['http_proxy']
        if config.get('schedule_times'):
            self.schedule_time_input.text = config['schedule_times']
        if config.get('link_title'):
            self.link_title_input.text = config['link_title']
        if config.get('link_desc'):
            self.link_desc_input.text = config['link_desc']
        if config.get('link_url'):
            self.link_url_input.text = config['link_url']
        if config.get('card_title'):
            self.card_title_input.text = config['card_title']
        if config.get('card_content'):
            self.card_content_input.text = config['card_content']
        
        platform_map = {'wps': 'WPS', 'generic': '通用 Webhook'}
        if config.get('platform'):
            self.platform_spinner.text = platform_map.get(config['platform'], 'WPS')
        
        type_map = {'text': '文本', 'markdown': 'Markdown', 'link': '链接', 'card': '卡片'}
        if config.get('msg_type'):
            self.msg_type_spinner.text = type_map.get(config['msg_type'], '文本')
        
        self.log_msg("配置已加载")
    
    def save_config(self, instance):
        config = {
            'url': self.url_input.text,
            'platform': self.platform,
            'msg_type': self.msg_type,
            'text_content': self.content_input.text,
            'image_path': self.image_input.text,
            'use_proxy': self.use_proxy_cb.active,
            'http_proxy': self.proxy_input.text,
            'https_proxy': self.proxy_input.text,
            'schedule_times': self.schedule_time_input.text,
            'link_title': self.link_title_input.text,
            'link_desc': self.link_desc_input.text,
            'link_url': self.link_url_input.text,
            'card_title': self.card_title_input.text,
            'card_content': self.card_content_input.text,
        }
        if self.core.save_config(config):
            self.log_msg("配置已保存")
            self.show_popup("成功", "配置已保存")
        else:
            self.log_msg("保存配置失败")
            self.show_popup("错误", "保存配置失败")
    
    def show_popup(self, title: str, message: str):
        popup = Popup(
            title=title,
            content=Label(text=message),
            size_hint=(0.8, 0.3)
        )
        popup.open()
    
    def get_proxies(self):
        if not self.use_proxy_cb.active:
            return None
        proxy = self.proxy_input.text.strip()
        if not proxy:
            return None
        return {"http": proxy, "https": proxy}
    
    def send_webhook(self, instance):
        url = self.url_input.text.strip()
        if not url:
            self.show_popup("错误", "请输入 Webhook URL")
            return
        
        self.log_msg("正在发送...")
        
        def do_send():
            try:
                proxies = self.get_proxies()
                
                if self.platform == 'generic':
                    result = self.core.send_generic_webhook(
                        url, 
                        self.content_input.text,
                        '{"Content-Type": "application/json"}',
                        proxies
                    )
                else:
                    if self.msg_type == 'text':
                        result = self.core.send_wps_text(url, self.content_input.text, 'text', proxies)
                    elif self.msg_type == 'markdown':
                        result = self.core.send_wps_text(url, self.content_input.text, 'markdown', proxies)
                    elif self.msg_type == 'link':
                        result = self.core.send_wps_link(
                            url,
                            self.link_title_input.text,
                            self.link_desc_input.text,
                            self.link_url_input.text,
                            proxies
                        )
                    elif self.msg_type == 'card':
                        result = self.core.send_wps_card(
                            url,
                            self.card_title_input.text,
                            self.card_content_input.text,
                            proxies
                        )
                    else:
                        result = {"error": "未知消息类型"}
                
                Clock.schedule_once(lambda dt: self.on_send_complete(result), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.on_send_complete({"error": str(e)}), 0)
        
        threading.Thread(target=do_send, daemon=True).start()
    
    def on_send_complete(self, result):
        if 'error' in result:
            self.log_msg(f"发送失败: {result['error']}")
            self.show_popup("失败", f"发送失败: {result['error']}")
        else:
            self.log_msg(f"发送成功: {result.get('status_code', 'N/A')} - {result.get('text', '')[:100]}")
            self.show_popup("成功", f"发送成功\n状态码: {result.get('status_code', 'N/A')}")
    
    def test_connection(self, instance):
        url = self.url_input.text.strip()
        if not url:
            self.show_popup("错误", "请输入 Webhook URL")
            return
        
        self.log_msg("正在测试连接...")
        
        def do_test():
            try:
                proxies = self.get_proxies()
                result = self.core.test_connection(url, proxies)
                Clock.schedule_once(lambda dt: self.on_test_complete(result), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.on_test_complete({"error": str(e)}), 0)
        
        threading.Thread(target=do_test, daemon=True).start()
    
    def on_test_complete(self, result):
        if 'error' in result:
            self.log_msg(f"连接失败: {result['error']}")
            self.show_popup("失败", f"连接失败: {result['error']}")
        else:
            self.log_msg(f"连接成功: {result.get('status_code', 'N/A')}")
            self.show_popup("成功", f"连接成功\n状态码: {result.get('status_code', 'N/A')}")


class WebhookPusherApp(App):
    def build(self):
        self.title = "Webhook 推送工具"
        return MainScreen()


if __name__ == '__main__':
    WebhookPusherApp().run()
