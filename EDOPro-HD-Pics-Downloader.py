#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EDOPro HD Pics Downloader - Web UI Version
Author: Armytille
Version: 3.0.0 - Web UI Edition
"""

import os
import sys
import json
import time
import threading
import webbrowser
import urllib.request
import urllib.error
import platform
import subprocess
import locale
from http.server import HTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor, as_completed, CancelledError, TimeoutError as FuturesTimeoutError
from datetime import datetime
import socket

API_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
DEFAULT_PORT = 8765
MAX_PORT_ATTEMPTS = 10
CONFIG_FILE = os.path.expanduser("~/.edopro_downloader_config.json")

class DownloadState:
    """Shared state for UI and worker"""
    def __init__(self):
        self.running = False
        self.total = 0
        self.processed = 0
        self.skipped = 0
        self.errors = 0
        self.logs = []
        self.cancel_flag = False
        self.pause_flag = False
        self.pause_cond = threading.Condition()
        self.start_time = None
        self.error_details = []
        self.api_error = None
        self.report = None
        self.lock = threading.Lock()
    
    def add_log(self, message, log_type='info'):
        with self.lock:
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.logs.append({
                'type': log_type,
                'message': f'[{timestamp}] {message}',
                'timestamp': time.time()
            })
            if len(self.logs) > 100:
                self.logs = self.logs[-100:]
    
    def increment(self, field):
        with self.lock:
            setattr(self, field, getattr(self, field) + 1)
    
    def reset(self):
        with self.lock:
            self.running = False
            self.total = 0
            self.processed = 0
            self.skipped = 0
            self.errors = 0
            self.logs = []
            self.cancel_flag = False
            self.pause_flag = False
            self.start_time = None
            self.error_details = []
            self.api_error = None
            self.report = None

state = DownloadState()

def detect_system():
    """Detect operating system"""
    return platform.system()

def detect_language():
    def macos_language():
        try:
            result = subprocess.run(
                ['defaults', 'read', '-g', 'AppleLanguages'],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode == 0:
                data = result.stdout.lower()
                tokens = data.replace('"', ' ').replace(',', ' ').replace('(', ' ').replace(')', ' ').split()
                for tok in tokens:
                    if tok.startswith('es'):
                        return 'es'
                    if tok.startswith('en'):
                        return 'en'
        except Exception:
            return None
        return None

    if detect_system() == 'Darwin':
        mac = macos_language()
        if mac:
            return mac
    try:
        lang, _ = locale.getdefaultlocale()
    except Exception:
        lang = None
    env = os.environ.get('LANG', '')
    lang = (lang or env or '').lower()
    return 'es' if lang.startswith('es') else 'en'

def find_pics_in_parents(start_dir, max_levels=None):
    """Search for a 'pics' folder in parent directories (direct child only)"""
    current = os.path.abspath(start_dir)
    levels = 0
    while True:
        candidate = os.path.join(current, 'pics')
        if os.path.isdir(candidate):
            return os.path.abspath(candidate)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
        levels += 1
        if max_levels is not None and levels >= max_levels:
            break
    return None

def find_edopro_macos():
    """Find ProjectIgnis/EDOPro pics on macOS using common paths only"""
    direct_pics_paths = [
        "~/Applications/ProjectIgnis/pics",
        "~/Aplicaciones/ProjectIgnis/pics",
        "~/Applications/EDOPro/pics",
        "~/Aplicaciones/EDOPro/pics"
    ]

    for path in direct_pics_paths:
        expanded_path = os.path.expanduser(path)
        if os.path.isdir(expanded_path):
            return os.path.abspath(expanded_path)

    common_apps = [
        "/Applications/EDOPro.app",
        "~/Applications/EDOPro.app",
        "/Applications/ProjectIgnis.app",
        "~/Applications/ProjectIgnis.app",
        "/Applications/ProjectIgnis/ProjectIgnis.app",
        "~/Applications/ProjectIgnis/ProjectIgnis.app"
    ]

    for app_path in common_apps:
        expanded_path = os.path.expanduser(app_path)
        if os.path.exists(expanded_path):
            pics_path = validate_macos_app_path(expanded_path)
            if pics_path:
                return pics_path

    return None

def validate_macos_app_path(app_path):
    """Validate .app structure and find pics folder"""
    pics_paths = [
        os.path.join(app_path, "Contents", "Resources", "pics"),
        os.path.join(app_path, "pics")
    ]
    
    for pics_path in pics_paths:
        if os.path.exists(pics_path):
            return os.path.abspath(pics_path)
    return None

def find_projectignis_windows():
    """Find ProjectIgnis on Windows using multiple methods"""
    paths_to_check = [
        "C:\\ProjectIgnis\\pics",
        "C:\\Program Files\\ProjectIgnis\\pics", 
        "C:\\Program Files (x86)\\ProjectIgnis\\pics"
    ]
    
    for path in paths_to_check:
        if os.path.exists(path):
            return os.path.abspath(path)
    
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall") as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    if "ProjectIgnis" in subkey_name or "EDOPro" in subkey_name:
                        subkey = winreg.OpenKey(key, subkey_name)
                        install_path = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                        winreg.CloseKey(subkey)
                        
                        pics_path = os.path.join(install_path, "pics")
                        if os.path.exists(pics_path):
                            return os.path.abspath(pics_path)
                except:
                    continue
    except:
        pass
    
    return None

def find_projectignis_linux():
    """Find ProjectIgnis on Linux"""
    paths_to_check = [
        os.path.expanduser("~/.local/share/ProjectIgnis/pics"),
        "/usr/share/ProjectIgnis/pics",
        "/opt/ProjectIgnis/pics",
        os.path.expanduser("~/ProjectIgnis/pics")
    ]
    
    for path in paths_to_check:
        if os.path.exists(path):
            return os.path.abspath(path)
    
    return None

def smart_detect_projectignis():
    """Intelligent detection with persistence"""
    config = load_config()

    if 'last_valid_path' in config:
        info = analyze_pics_path(config['last_valid_path'])
        if info['exists'] and info['is_pics_folder']:
            state.add_log(f"Using saved path: {info['path']}", 'info')
            return info['path']

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        found = find_pics_in_parents(script_dir)
        if found:
            save_config({'last_valid_path': found})
            state.add_log(f"ProjectIgnis pics found near script: {found}", 'success')
            return found
    except Exception:
        pass

    system = detect_system()
    detected = None

    try:
        if system == 'Darwin':
            detected = find_edopro_macos()
        elif system == 'Windows':
            detected = find_projectignis_windows()
        elif system == 'Linux':
            detected = find_projectignis_linux()

        if detected:
            save_config({'last_valid_path': detected})
            state.add_log(f"ProjectIgnis detected at: {detected}", 'success')
    except Exception as e:
        state.add_log(f"Detection error: {e}", 'error')

    return detected


def save_config(config):
    try:
        current = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                current = json.load(f)
        current.update(config or {})
        with open(CONFIG_FILE, 'w') as f:
            json.dump(current, f, indent=2)
        return True
    except Exception as e:
        state.add_log(f"Failed to save config: {e}", 'error')
        return False

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def run_applescript_folder_dialog():
    """Open folder selection dialog on macOS"""
    script = '''
    tell application "Finder"
        activate
        set folderPath to choose folder with prompt "Select ProjectIgnis folder"
        return POSIX path of folderPath
    end tell
    '''
    try:
        result = subprocess.run(['osascript', '-e', script], 
                            capture_output=True, text=True)
        if result.returncode == 0:
            folder_path = result.stdout.strip()
            if folder_path and os.path.exists(folder_path):
                return os.path.abspath(folder_path)
        return None
    except Exception as e:
        state.add_log(f"Folder dialog error: {e}", 'error')
        return None

def run_windows_folder_dialog():
    """Open folder selection dialog on Windows"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        folder_path = filedialog.askdirectory(
            title="Select ProjectIgnis folder",
            initialdir="C:\\"
        )
        root.destroy()
        
        if folder_path:
            return os.path.abspath(folder_path)
        return None
    except Exception as e:
        state.add_log(f"Folder dialog error: {e}", 'error')
        return None

def run_linux_folder_dialog():
    """Open folder selection dialog on Linux"""
    try:
        result = subprocess.run(['zenity', '--file-selection', '--directory'],
                              capture_output=True, text=True)
        if result.returncode == 0:
            folder_path = result.stdout.strip()
            if folder_path and os.path.exists(folder_path):
                return os.path.abspath(folder_path)
    except:
        pass
    
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()
        
        folder_path = filedialog.askdirectory(
            title="Select ProjectIgnis folder",
            initialdir=os.path.expanduser("~")
        )
        root.destroy()
        
        if folder_path:
            return os.path.abspath(folder_path)
        return None
    except Exception as e:
        state.add_log(f"Folder dialog error: {e}", 'error')
        return None

def analyze_pics_path(path):
    """Analyze a path and ensure it is an existing pics folder"""
    if not path:
        return {
            'exists': False,
            'is_pics_folder': False,
            'path': None,
            'suggested_path': None
        }
    
    candidate = os.path.abspath(os.path.expanduser(path.strip()))
    if not os.path.exists(candidate):
        return {
            'exists': False,
            'is_pics_folder': False,
            'path': candidate,
            'suggested_path': None
        }
    
    if os.path.isdir(candidate) and os.path.basename(candidate).lower() == 'pics':
        return {
            'exists': True,
            'is_pics_folder': True,
            'path': candidate,
            'suggested_path': None
        }
    
    pics_sub = os.path.join(candidate, 'pics')
    if os.path.isdir(pics_sub):
        return {
            'exists': True,
            'is_pics_folder': False,
            'path': candidate,
            'suggested_path': os.path.abspath(pics_sub)
        }
    
    return {
        'exists': True,
        'is_pics_folder': False,
        'path': candidate,
        'suggested_path': None
    }

def verify_jpeg(path):
    """Verify file is a valid JPEG"""
    try:
        with open(path, 'rb') as f:
            if f.read(2) != b'\xff\xd8':
                return False
            f.seek(-2, 2)
            if f.read(2) != b'\xff\xd9':
                return False
            f.seek(0, 2)
            if f.tell() < 1024:
                return False
        return True
    except Exception:
        return False

def list_existing_images(directory):
    try:
        return {
            name.lower()
            for name in os.listdir(directory)
            if name.lower().endswith('.jpg')
        }
    except FileNotFoundError:
        return set()
    except Exception:
        return set()

def write_report(stats, errors):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_dir = os.path.dirname(os.path.abspath(__file__))
    report_dir = os.path.join(base_dir, "reports-reportes")
    try:
        os.makedirs(report_dir, exist_ok=True)
    except Exception as e:
        state.add_log(f"Report folder error: {e}", 'error')
        return None
    json_path = os.path.join(report_dir, f"edopro_download_report_{ts}.json")
    md_path = os.path.join(report_dir, f"edopro_download_report_{ts}.md")
    try:
        payload = {
            'timestamp': ts,
            'stats': stats,
            'errors': errors
        }
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write("# EDOPro HD Pics Downloader Report\n\n")
            f.write(f"- Timestamp: {ts}\n")
            for k, v in stats.items():
                f.write(f"- {k}: {v}\n")
            if errors:
                f.write("\n## Errors\n\n")
                for e in errors:
                    f.write(f"- ID: {e.get('id')} | {e.get('name')} | {e.get('error')}\n")
        return {'json': json_path, 'md': md_path}
    except Exception as e:
        state.add_log(f"Report error: {e}", 'error')
        return None

def format_time(seconds):
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"

def http_get_json(url, timeout=30):
    """Download and parse JSON from URL"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "EDOPro-HD-Downloader/3.0",
        "Accept": "application/json",
        "Accept-Charset": "utf-8"
    })
    
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        encoding = r.headers.get_content_charset('utf-8')
        return json.loads(data.decode(encoding))

def download_file(url, outpath, timeout=30, max_retries=3, rate_limit_kbps=0):
    temp = outpath + ".part"
    limit_bps = max(0, int(rate_limit_kbps)) * 1024
    
    for attempt in range(1, max_retries + 1):
        if state.cancel_flag:
            if os.path.exists(temp):
                try:
                    os.remove(temp)
                except Exception:
                    pass
            return False, "Cancelled by user"
        
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "EDOPro-HD-Downloader/3.0",
                "Accept": "image/jpeg"
            })
            
            with urllib.request.urlopen(req, timeout=timeout) as r:
                ctype = r.headers.get('Content-Type', '').lower()
                if not ctype.startswith('image/jpeg'):
                    raise ValueError(f"Unsupported content type: {ctype}")
                
                with open(temp, "wb") as f:
                    window_start = time.time()
                    window_bytes = 0
                    while True:
                        if state.cancel_flag:
                            raise InterruptedError("Cancelled during download")
                        with state.pause_cond:
                            while state.pause_flag:
                                state.pause_cond.wait(0.5)
                                if state.cancel_flag:
                                    raise InterruptedError("Cancelled during pause")
                        
                        chunk = r.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        if limit_bps > 0:
                            window_bytes += len(chunk)
                            elapsed = time.time() - window_start
                            expected = window_bytes / limit_bps
                            if expected > elapsed:
                                time.sleep(expected - elapsed)
                            if elapsed >= 1:
                                window_start = time.time()
                                window_bytes = 0
            
            if not verify_jpeg(temp):
                raise ValueError("Downloaded file is not a valid JPEG")
            
            os.replace(temp, outpath)
            return True, None
            
        except InterruptedError as e:
            if os.path.exists(temp):
                try:
                    os.remove(temp)
                except Exception:
                    pass
            return False, str(e)
            
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as e:
            if attempt == max_retries:
                if os.path.exists(temp):
                    try:
                        os.remove(temp)
                    except Exception:
                        pass
                return False, f"After {max_retries} attempts: {str(e)}"
            
            time.sleep(2 ** (attempt - 1))
    
    return False, "Max retries exceeded"

def build_download_tasks(cards):
    """Build download task list from API data"""
    tasks = []
    
    for card in cards:
        card_id = card.get("id")
        name = card.get("name", "Unknown")
        images = card.get("card_images") or []
        card_type = card.get("type", "")
        
        for img in images:
            img_id = img.get("id")
            img_url = img.get("image_url")
            
            if img_id and img_url:
                tasks.append({
                    "card_id": card_id,
                    "name": name,
                    "image_id": img_id,
                    "url": img_url,
                    "subfolder": ""
                })
        
        if "Field" in card_type and "Spell" in card_type:
            first_img = images[0] if images else None
            if first_img:
                cropped_url = first_img.get("image_url_cropped")
                if cropped_url:
                    tasks.append({
                        "card_id": card_id,
                        "name": name,
                        "image_id": card_id,
                        "url": cropped_url,
                        "subfolder": "field"
                    })
    
    return tasks

def filter_cards(cards, type_filter=None, set_filter=None):
    if not type_filter and not set_filter:
        return cards
    type_filter = (type_filter or "").strip().lower()
    set_filter = (set_filter or "").strip().lower()
    filtered = []
    for card in cards:
        if type_filter:
            ctype = (card.get("type") or "").lower()
            if type_filter not in ctype:
                continue
        if set_filter:
            sets = card.get("card_sets") or []
            matched = False
            for s in sets:
                name = (s.get("set_name") or "").lower()
                code = (s.get("set_code") or "").lower()
                if set_filter in name or set_filter in code:
                    matched = True
                    break
            if not matched:
                continue
        filtered.append(card)
    return filtered

def filter_tasks(tasks, picsdir, only_missing, validate_existing):
    if not only_missing and not validate_existing:
        return tasks
    existing_base = list_existing_images(picsdir)
    existing_field = list_existing_images(os.path.join(picsdir, "field"))
    new_tasks = []
    for t in tasks:
        sub = t.get("subfolder") or ""
        fname = f"{t['image_id']}.jpg".lower()
        exists = fname in (existing_field if sub == "field" else existing_base)
        if not exists:
            new_tasks.append(t)
            continue
        if validate_existing:
            target_dir = os.path.join(picsdir, sub) if sub else picsdir
            outpath = os.path.join(target_dir, f"{t['image_id']}.jpg")
            if not verify_jpeg(outpath):
                new_tasks.append(t)
        elif not only_missing:
            new_tasks.append(t)
    return new_tasks

def download_worker_task(task, picsdir, force, timeout, retry_count, validate_existing, rate_limit_kbps):
    """Worker to download individual image"""
    if state.cancel_flag:
        return {"status": "Cancelled", "task": task}
    
    sub = task.get("subfolder") or ""
    target_dir = os.path.join(picsdir, sub) if sub else picsdir
    if not os.path.isdir(target_dir):
        return {
            "status": "Error",
            "task": task,
            "error": f"Target directory not found: {target_dir}"
        }
    
    fname = f"{task['image_id']}.jpg"
    outpath = os.path.join(target_dir, fname)
    
    if os.path.exists(outpath) and not force:
        if not validate_existing:
            return {"status": "Skipped", "task": task}
        if verify_jpeg(outpath):
            return {"status": "Skipped", "task": task}
    
    ok, err = download_file(
        task["url"],
        outpath,
        timeout=timeout,
        max_retries=retry_count,
        rate_limit_kbps=rate_limit_kbps
    )
    
    if ok:
        return {"status": "Success", "task": task}
    elif "Cancelled" in str(err):
        return {"status": "Cancelled", "task": task}
    else:
        return {
            "status": "Error",
            "task": task,
            "error": err
        }

def download_worker_main(params):
    """Main worker that coordinates all downloads"""
    try:
        state.running = True
        state.cancel_flag = False
        state.start_time = time.time()
        state.add_log("🚀 Starting downloader...", 'info')
        
        picsdir = params.get('picsdir', './pics')
        force = params.get('force', False)
        only_missing = params.get('onlyMissing', False)
        validate_existing = bool(params.get('validateExisting', False))
        concurrency = params.get('concurrency', 12)
        timeout = params.get('timeout', 30)
        retry = params.get('retry', 3)
        rate_limit_kbps = params.get('maxKbps', 0)
        type_filter = params.get('typeFilter', '')
        set_filter = params.get('setFilter', '')
        
        if force:
            only_missing = False
        
        try:
            concurrency = int(concurrency)
        except (ValueError, TypeError):
            concurrency = 12
        concurrency = max(1, min(50, concurrency))
        
        try:
            timeout = int(timeout)
        except (ValueError, TypeError):
            timeout = 30
        timeout = max(10, min(120, timeout))
        
        try:
            retry = int(retry)
        except (ValueError, TypeError):
            retry = 3
        retry = max(1, min(10, retry))

        try:
            rate_limit_kbps = int(rate_limit_kbps)
        except (ValueError, TypeError):
            rate_limit_kbps = 0
        if rate_limit_kbps < 0:
            rate_limit_kbps = 0
        
        path_info = analyze_pics_path(picsdir)
        if path_info['suggested_path']:
            state.add_log(f"ℹ️  Selected folder contains 'pics'. Using: {path_info['suggested_path']}", 'info')
            picsdir = path_info['suggested_path']
            path_info = analyze_pics_path(picsdir)
        else:
            picsdir = path_info['path'] or os.path.abspath(picsdir.strip())

        if not path_info['exists'] or not path_info['is_pics_folder']:
            state.add_log(f"❌ Invalid pics directory: {picsdir}", 'error')
            state.running = False
            return

        if not os.path.isdir(picsdir):
            state.add_log(f"❌ Pics directory not accessible: {picsdir}", 'error')
            state.running = False
            return


        save_config({'last_valid_path': picsdir})
        
        state.add_log(f"📁 Output directory: {picsdir}", 'info')
        if not os.path.isdir(os.path.join(picsdir, "field")):
            state.add_log("⚠️  Field folder not found (pics/field). It will be created by EDOPro if needed.", 'warning')
        
        state.add_log("📡 Connecting to YGOProDeck API...", 'info')
        try:
            data = http_get_json(API_URL, timeout=timeout)
            cards = data.get("data") or []
            
            if not cards:
                state.add_log("❌ No data received from API", 'error')
                state.running = False
                return
            
            state.add_log(f"✅ Received {len(cards):,} cards from API", 'success')
            
        except Exception as e:
            state.api_error = str(e)
            state.add_log(f"❌ API connection error: {e}", 'error')
            state.running = False
            return
        
        state.add_log("🔨 Preparing download list...", 'info')
        filtered_cards = filter_cards(cards, type_filter, set_filter)
        tasks = build_download_tasks(filtered_cards)
        
        original_count = len(tasks)
        tasks = filter_tasks(tasks, picsdir, only_missing, validate_existing)
        filtered_out = original_count - len(tasks)
        if filtered_out > 0:
            state.add_log(f"ℹ️  Filtered {filtered_out:,} existing images", 'info')
        
        state.total = len(tasks)
        
        if state.total == 0:
            state.add_log("✅ All images already downloaded", 'success')
            state.running = False
            return
        
        state.add_log(f"✅ Prepared {state.total:,} images for download", 'success')
        state.add_log(f"⚙️  Configuration: {concurrency} parallel downloads, {retry} retries, {timeout}s timeout", 'info')
        state.add_log(f"⚙️  Mode: {'Force replace' if force else 'Skip existing'}", 'info')
        if rate_limit_kbps:
            state.add_log(f"⚙️  Rate limit: {int(rate_limit_kbps)} KB/s per download", 'info')
        if validate_existing:
            state.add_log("⚙️  Validate existing: enabled", 'info')
        state.add_log("", 'info')
        state.add_log("🚀 Starting downloads...", 'info')
        
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(download_worker_task, t, picsdir, force, timeout, retry, validate_existing, rate_limit_kbps)
                for t in tasks
            ]
            
            cancel_requested = False
            for future in as_completed(futures):
                if state.cancel_flag and not cancel_requested:
                    state.add_log("⚠️  Cancellation requested, stopping new downloads...", 'warning')
                    cancel_requested = True
                    for f in futures:
                        f.cancel()
                
                try:
                    result = future.result()
                    status = result.get("status")
                    task = result.get("task")
                    
                    if status == "Success":
                        state.increment('processed')
                        if state.processed % 50 == 0 or state.processed < 10:
                            state.add_log(f"✓ Downloaded: {state.processed:,}/{state.total:,}", 'success')
                    
                    elif status == "Skipped":
                        state.increment('skipped')
                        if state.skipped % 100 == 0:
                            state.add_log(f"⊘ Skipped: {state.skipped:,}", 'info')
                    
                    elif status == "Error":
                        state.increment('errors')
                        error_msg = result.get("error", "Unknown error")
                        state.add_log(f"✗ Error in {task['name']} (ID: {task['image_id']}): {error_msg}", 'error')
                        state.error_details.append({
                            'id': task['image_id'],
                            'name': task['name'],
                            'url': task['url'],
                            'error': error_msg
                        })
                    
                    elif status == "Cancelled":
                        pass
                
                except CancelledError:
                    pass
                except Exception as e:
                    state.increment('errors')
                    state.add_log(f"✗ Unexpected error: {e}", 'error')
        
        elapsed = time.time() - state.start_time
        state.add_log("", 'info')
        state.add_log("═" * 60, 'info')
        
        if state.cancel_flag:
            state.add_log("⚠️  DOWNLOAD CANCELLED", 'warning')
        else:
            state.add_log("✅ DOWNLOAD COMPLETED", 'success')
        
        state.add_log("═" * 60, 'info')
        state.add_log(f"📊 Final Statistics:", 'info')
        state.add_log(f"   • Total images: {state.total:,}", 'info')
        state.add_log(f"   • ✓ Downloaded: {state.processed:,}", 'success')
        state.add_log(f"   • ⊘ Skipped: {state.skipped:,}", 'info')
        state.add_log(f"   • ✗ Errors: {state.errors:,}", 'error' if state.errors > 0 else 'info')
        state.add_log(f"   • ⏱  Total time: {format_time(elapsed)}", 'info')
        
        if state.processed > 0:
            rate = state.processed / elapsed if elapsed > 0 else 0
            state.add_log(f"   • 📈 Average speed: {rate:.1f} imgs/sec", 'info')
        
        state.add_log("", 'info')
        state.add_log(f"📁 Images saved to: {os.path.abspath(picsdir)}", 'info')
        
        if state.errors > 0:
            state.add_log(f"⚠️  {state.errors} errors occurred. Check details above.", 'warning')

        stats = {
            'total': state.total,
            'downloaded': state.processed,
            'skipped': state.skipped,
            'errors': state.errors,
            'elapsed': format_time(elapsed)
        }
        report = write_report(stats, state.error_details)
        if report:
            state.add_log(f"📝 Report (JSON): {report['json']}", 'info')
            state.add_log(f"📝 Report (MD): {report['md']}", 'info')
            state.report = report
        
    except Exception as e:
        state.add_log(f"❌ FATAL ERROR: {e}", 'error')
    
    finally:
        state.running = False

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EDOPro HD Pics Downloader</title>
    <style>
        :root {
            --bg-1: #f3f5f8;
            --bg-2: #e9eef5;
            --panel: #ffffff;
            --panel-muted: #f8fafc;
            --border: #e5e7eb;
            --text: #0f172a;
            --muted: #6b7280;
            --accent: #2563eb;
            --accent-weak: #e8f0ff;
            --ok: #16a34a;
            --warn: #f59e0b;
            --err: #ef4444;
            --log-bg: #0b1220;
        }

        body[data-theme="dark"] {
            --bg-1: #0b1120;
            --bg-2: #0f172a;
            --panel: #111827;
            --panel-muted: #0b1220;
            --border: #1f2937;
            --text: #e5e7eb;
            --muted: #94a3b8;
            --accent: #3b82f6;
            --accent-weak: #1e293b;
            --ok: #22c55e;
            --warn: #f59e0b;
            --err: #f87171;
            --log-bg: #0a0f1c;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
            background: radial-gradient(1200px 600px at 10% 10%, var(--bg-2), var(--bg-1));
            color: var(--text);
            height: 100vh;
            overflow: hidden;
        }

        .container {
            max-width: 1400px;
            height: calc(100vh - 24px);
            margin: 12px auto;
            display: grid;
            grid-template-rows: auto 1fr auto;
            gap: 10px;
            padding: 0 12px;
        }

        .header {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px 16px;
        }

        .header-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
        }

        .controls {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .title {
            font-size: 20px;
            font-weight: 700;
            letter-spacing: -0.2px;
        }

        .subtitle {
            margin-top: 4px;
            font-size: 13px;
            color: var(--muted);
        }

        .content {
            display: grid;
            grid-template-columns: 440px 1fr;
            gap: 10px;
            min-height: 0;
        }

        .panel {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            min-height: 0;
            overflow: hidden;
        }

        .config-panel {
            overflow: visible;
        }

        .panel-title {
            font-size: 14px;
            font-weight: 600;
            color: var(--text);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .status-row {
            display: flex;
            align-items: center;
            gap: 8px;
            justify-content: space-between;
        }

        .badge {
            padding: 4px 8px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
            background: var(--accent-weak);
            color: var(--accent);
        }

        .badge.ok { background: #e7f7ee; color: var(--ok); }
        .badge.warn { background: #fff3d6; color: var(--warn); }
        .badge.err { background: #fee2e2; color: var(--err); }

        .field {
            display: grid;
            gap: 6px;
        }

        label {
            font-size: 12px;
            color: var(--muted);
            font-weight: 600;
        }

        input[type="text"],
        input[type="number"] {
            width: 100%;
            padding: 8px 10px;
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 13px;
            outline: none;
            background: var(--panel);
            color: var(--text);
        }

        input[type="text"]:focus,
        input[type="number"]:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
        }

        .input-row {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 6px;
        }

        .help {
            font-size: 12px;
            color: var(--muted);
        }

        .label-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
        }

        .help-icon {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            border: 1px solid var(--border);
            background: var(--panel);
            color: var(--muted);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            cursor: help;
            position: relative;
        }

        .help-icon::after {
            content: attr(data-tooltip);
            position: absolute;
            bottom: 120%;
            left: 50%;
            transform: translate(-50%, 6px);
            opacity: 0;
            pointer-events: none;
            white-space: pre-line;
            width: 320px;
            max-width: 360px;
            background: var(--panel);
            color: var(--text);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px;
            font-size: 12px;
            box-shadow: 0 6px 18px rgba(0,0,0,0.12);
            transition: opacity 0.15s ease, transform 0.15s ease;
            z-index: 20;
        }

        .help-icon:hover::after,
        .help-icon:focus::after {
            opacity: 1;
            transform: translate(-50%, 0);
        }

        .row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }

        .grid-3 {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
        }

        .grid-2 {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
        }

        .check {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            color: var(--text);
            font-weight: 500;
        }

        .check-group {
            margin: 4px 0 8px;
            padding: 4px 0;
        }

        .btn {
            padding: 8px 12px;
            border-radius: 8px;
            border: 1px solid transparent;
            background: var(--accent);
            color: white;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }

        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .btn-ghost {
            background: transparent;
            color: var(--accent);
            border-color: var(--border);
        }

        .btn-secondary {
            background: var(--panel-muted);
            color: var(--text);
            border: 1px solid var(--border);
        }

        .btn-label {
            transition: opacity 0.15s ease;
        }

        .btn.loading .btn-label {
            visibility: hidden;
        }

        .spinner {
            width: 14px;
            height: 14px;
            border-radius: 50%;
            border: 2px solid rgba(0, 0, 0, 0.15);
            border-top-color: currentColor;
            animation: spin 0.8s linear infinite;
            display: none;
            position: absolute;
        }

        body[data-theme="dark"] .spinner {
            border-color: rgba(255, 255, 255, 0.2);
        }

        .btn.loading .spinner {
            display: inline-block;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        select {
            padding: 6px 8px;
            border-radius: 8px;
            border: 1px solid var(--border);
            font-size: 12px;
            background: var(--panel);
            color: var(--text);
        }

        .notice {
            min-height: 28px;
            padding: 6px 10px;
            border-radius: 8px;
            font-size: 12px;
            border: 1px solid var(--border);
            background: var(--panel-muted);
            color: var(--muted);
            display: flex;
            align-items: center;
            opacity: 0;
            transition: opacity 0.15s ease;
        }

        .notice.show { opacity: 1; }
        .notice.info { background: var(--accent-weak); color: var(--accent); border-color: var(--accent-weak); }
        .notice.success { background: #ecfdf3; color: #166534; border-color: #bbf7d0; }
        .notice.warning { background: #fff7ed; color: #9a3412; border-color: #fed7aa; }
        .notice.error { background: #fef2f2; color: #991b1b; border-color: #fecaca; }

        .progress-bar-container {
            background: var(--panel-muted);
            border-radius: 999px;
            height: 24px;
            overflow: hidden;
        }

        .progress-bar {
            height: 100%;
            background: var(--accent);
            width: 0%;
            color: white;
            font-size: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: width 0.3s ease;
        }

        .stats {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
        }

        .stat-card {
            background: var(--panel-muted);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 10px;
            display: grid;
            gap: 4px;
        }

        .stat-card .label {
            font-size: 11px;
            color: var(--muted);
            font-weight: 600;
        }

        .stat-card .value {
            font-size: 18px;
            font-weight: 700;
        }

        .stat-card .subvalue {
            font-size: 11px;
            color: var(--muted);
        }

        .stat-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            color: var(--muted);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 10px;
        }

        .log-wrap {
            display: grid;
            grid-template-rows: auto 1fr;
            gap: 6px;
            min-height: 0;
            flex: 1;
        }

        .log-title {
            font-size: 12px;
            color: var(--muted);
            font-weight: 600;
        }

        .log-container {
            background: var(--log-bg);
            color: #e2e8f0;
            border-radius: 8px;
            padding: 8px;
            font-family: "JetBrains Mono", "SFMono-Regular", Menlo, monospace;
            font-size: 11px;
            overflow-y: auto;
        }

        .advanced-card {
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 8px 10px;
            background: var(--panel-muted);
        }

        .advanced-card[open] {
            background: var(--panel);
        }

        .advanced-summary {
            list-style: none;
            cursor: pointer;
            font-size: 12px;
            font-weight: 600;
            color: var(--text);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .advanced-summary::-webkit-details-marker {
            display: none;
        }

        .advanced-summary::after {
            content: '+';
            color: var(--muted);
            font-weight: 700;
        }

        .advanced-card[open] .advanced-summary::after {
            content: '−';
        }

        .advanced-body {
            margin-top: 8px;
            display: grid;
            gap: 8px;
        }

        .log-line { margin-bottom: 4px; }
        .log-line.success { color: #22c55e; }
        .log-line.error { color: #f87171; }
        .log-line.info { color: #60a5fa; }
        .log-line.warning { color: #fbbf24; }

        .footer {
            text-align: center;
            font-size: 11px;
            color: var(--muted);
            padding-bottom: 4px;
        }

        .footer a { color: var(--accent); text-decoration: none; }

    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-top">
                <div>
                    <div class="title" id="titleText">EDOPro HD Pics Downloader</div>
                    <div class="subtitle" id="subtitleText">Descargador de imágenes Yu-Gi-Oh! para EDOPro</div>
                </div>
                <div class="controls">
                    <button type="button" class="btn btn-ghost" id="themeToggle">Theme</button>
                    <select id="langSelect">
                        <option value="es">ES</option>
                        <option value="en">EN</option>
                    </select>
                </div>
            </div>
        </div>

        <div class="content">
            <section class="panel config-panel">
                <div class="panel-title">
                    <span id="configTitle">Configuración</span>
                    <span id="detectStatus" class="badge">Detectando</span>
                </div>

                <div class="status-row">
                    <div class="help" id="detectHint">Detección automática en progreso</div>
                    <button type="button" class="btn btn-ghost" id="detectBtn" onclick="retryDetection()">Reintentar</button>
                </div>

                <div class="field">
                    <div class="label-row">
                        <label id="pathLabel" for="picsdir">Carpeta pics</label>
                        <button type="button" class="help-icon" id="pathHelp" aria-label="?">?</button>
                    </div>
                    <div class="input-row">
                        <input type="text" id="picsdir" value="./pics" placeholder="Ruta de la carpeta pics">
                        <button type="button" class="btn btn-secondary" id="browseBtn" onclick="browseFolder()">Examinar</button>
                    </div>
                </div>

                <div class="grid-3 check-group">
                    <label class="check"><input type="checkbox" id="force"><span id="forceLabel">Forzar reemplazo</span></label>
                    <label class="check"><input type="checkbox" id="onlyMissing" checked><span id="onlyMissingLabel">Solo faltantes</span></label>
                    <label class="check"><input type="checkbox" id="validateExisting"><span id="validateLabel">Validar existentes</span></label>
                </div>

                <details class="advanced-card" id="advancedCard">
                    <summary class="advanced-summary">
                        <span id="advancedTitle">Ajustes avanzados</span>
                    </summary>
                    <div class="advanced-body">
                        <div class="grid-2">
                            <div class="field">
                                <label id="concurrencyLabel">Concurrencia</label>
                                <input type="number" id="concurrency" value="12" min="1" max="50">
                            </div>
                            <div class="field">
                                <label id="retryLabel">Reintentos</label>
                                <input type="number" id="retry" value="3" min="1" max="10">
                            </div>
                            <div class="field">
                                <label id="timeoutLabel">Timeout (s)</label>
                                <input type="number" id="timeout" value="30" min="10" max="120">
                            </div>
                            <div class="field">
                                <label id="rateLabel">Máx KB/s</label>
                                <input type="number" id="maxKbps" value="0" min="0" max="99999">
                            </div>
                        </div>

                        <div class="grid-2">
                            <div class="field">
                                <label id="typeFilterLabel">Filtro tipo</label>
                                <input type="text" id="typeFilter" placeholder="Spell, Monster, Trap">
                            </div>
                            <div class="field">
                                <label id="setFilterLabel">Filtro set</label>
                                <input type="text" id="setFilter" placeholder="LOB, SDY, etc.">
                            </div>
                        </div>
                    </div>
                </details>

                <div class="actions">
                    <button type="button" class="btn btn-ghost" id="previewBtn">
                        <span class="btn-label" id="previewLabel">Vista previa</span>
                        <span class="spinner" id="previewSpinner" aria-hidden="true"></span>
                    </button>
                    <button type="button" class="btn" id="startBtn">Iniciar</button>
                    <button type="button" class="btn btn-ghost" id="pauseBtn" disabled>Pausar</button>
                    <button type="button" class="btn btn-secondary" id="cancelBtn" disabled>Cancelar</button>
                </div>

                <div class="notice" id="noticeBar"></div>
            </section>

            <section class="panel">
                <div class="panel-title" id="progressTitle">Progreso</div>

                <div class="progress-bar-container">
                    <div class="progress-bar" id="progressBar">0%</div>
                </div>

                <div class="stats">
                    <div class="stat-card">
                        <div class="label" id="totalLabel">Total</div>
                        <div class="value" id="statTotal">0</div>
                    </div>
                    <div class="stat-card">
                        <div class="label" id="processedLabel">Descargadas</div>
                        <div class="value" id="statProcessed">0</div>
                        <div class="subvalue" id="statSpeed">0 imgs/seg</div>
                    </div>
                    <div class="stat-card">
                        <div class="label" id="skippedLabel">Saltadas</div>
                        <div class="value" id="statSkipped">0</div>
                    </div>
                    <div class="stat-card">
                        <div class="label" id="errorsLabel">Errores</div>
                        <div class="value" id="statErrors">0</div>
                    </div>
                </div>

                <div class="stat-row">
                    <span id="timeLabel">Tiempo / ETA</span>
                    <span><span id="statElapsed">0s</span> / <span id="statEta">--</span></span>
                </div>

                <div class="log-wrap">
                    <div class="log-title" id="logTitle">Log en tiempo real</div>
                    <div class="log-container" id="logContainer">
                        <div class="log-line info">Esperando inicio de descarga...</div>
                    </div>
                </div>
            </section>
        </div>

        <div class="footer" id="footerText">
            EDOPro HD Pics Downloader v3.0 · Datos de <a href="https://db.ygoprodeck.com/" target="_blank">YGOProDeck API</a>
        </div>
    </div>

    <script>
        const DETECT_TIMEOUT_MS = 4000;
        const STRINGS = {
            es: {
                title: 'EDOPro HD Pics Downloader',
                subtitle: 'Descargador de imágenes Yu-Gi-Oh! para EDOPro',
                config: 'Configuración',
                advanced: 'Ajustes avanzados',
                detect_retry: 'Reintentar',
                detect_hint: 'Detección automática en progreso',
                detect_detecting: 'Detectando',
                detect_ok: 'Detectado',
                detect_fail: 'No detectado',
                detect_fail_hint: 'Usa la ruta manual',
                detect_timeout: 'No se pudo detectar automáticamente. Puedes seleccionar la carpeta manualmente.',
                theme_light: 'Tema claro',
                theme_dark: 'Tema oscuro',
                path_label: 'Carpeta pics',
                browse: 'Examinar',
                force: 'Forzar reemplazo',
                only_missing: 'Solo faltantes',
                validate_existing: 'Validar existentes',
                concurrency: 'Concurrencia',
                retry: 'Reintentos',
                timeout: 'Timeout (s)',
                rate: 'Máx KB/s',
                type_filter: 'Filtro tipo',
                set_filter: 'Filtro set',
                type_placeholder: 'Spell, Monster, Trap',
                set_placeholder: 'LOB, SDY, etc.',
                preview: 'Vista previa',
                preview_searching: 'Buscando cartas faltantes...',
                preview_found: 'Faltantes encontradas',
                start: 'Iniciar',
                pause: 'Pausar',
                resume: 'Reanudar',
                cancel: 'Cancelar',
                progress: 'Progreso',
                total: 'Total',
                processed: 'Descargadas',
                skipped: 'Saltadas',
                errors: 'Errores',
                time_eta: 'Tiempo / ETA',
                log_title: 'Log en tiempo real',
                waiting: 'Esperando inicio de descarga...',
                imgs_sec: 'imgs/seg',
                api_offline: 'API no disponible. Reintenta más tarde.',
                path_help_default: 'Selecciona la carpeta "pics" de tu instalación.',
                path_help_mac: 'Ruta típica:\\n/Users/<usuario>/Aplicaciones/ProjectIgnis/pics\\n/Users/<usuario>/Applications/ProjectIgnis/pics',
                path_help_win: 'Ruta típica:\\nC\\\\ProjectIgnis\\\\pics\\nC\\\\Program Files\\\\ProjectIgnis\\\\pics',
                path_help_linux: 'Ruta típica:\\n~/.local/share/ProjectIgnis/pics\\n/usr/share/ProjectIgnis/pics',
                alert_invalid_path: 'La carpeta no existe o no es "pics".',
                alert_valid_path: 'Carpeta válida seleccionada',
                alert_found_pics: 'Se encontró la carpeta "pics" dentro de la ruta',
                alert_picker_fail: 'No se pudo abrir el selector de carpetas',
                alert_picker_error: 'Error al abrir selector de carpetas',
                alert_validate_error: 'Error validando la carpeta',
                alert_need_path: 'Selecciona una carpeta de destino',
                alert_concurrency: 'La concurrencia debe estar entre 1 y 50',
                alert_started: 'Descarga iniciada',
                alert_done: 'Descarga completada',
                alert_done_errors: 'Descarga finalizada con errores',
                alert_cancelled: 'Cancelación solicitada',
                alert_api_error: 'Error de conexión',
                alert_preview: 'Vista previa',
                cards: 'cartas',
                footer: 'EDOPro HD Pics Downloader v3.0 · Datos de '
            },
            en: {
                title: 'EDOPro HD Pics Downloader',
                subtitle: 'Yu-Gi-Oh! image downloader for EDOPro',
                config: 'Settings',
                advanced: 'Advanced settings',
                detect_retry: 'Retry',
                detect_hint: 'Auto-detection in progress',
                detect_detecting: 'Detecting',
                detect_ok: 'Detected',
                detect_fail: 'Not detected',
                detect_fail_hint: 'Use manual path',
                detect_timeout: 'Auto-detection failed. Please select the folder manually.',
                theme_light: 'Light theme',
                theme_dark: 'Dark theme',
                path_label: 'Pics folder',
                browse: 'Browse',
                force: 'Force overwrite',
                only_missing: 'Only missing',
                validate_existing: 'Validate existing',
                concurrency: 'Concurrency',
                retry: 'Retries',
                timeout: 'Timeout (s)',
                rate: 'Max KB/s',
                type_filter: 'Type filter',
                set_filter: 'Set filter',
                type_placeholder: 'Spell, Monster, Trap',
                set_placeholder: 'LOB, SDY, etc.',
                preview: 'Preview',
                preview_searching: 'Checking missing cards...',
                preview_found: 'Missing found',
                start: 'Start',
                pause: 'Pause',
                resume: 'Resume',
                cancel: 'Cancel',
                progress: 'Progress',
                total: 'Total',
                processed: 'Downloaded',
                skipped: 'Skipped',
                errors: 'Errors',
                time_eta: 'Time / ETA',
                log_title: 'Live log',
                waiting: 'Waiting to start download...',
                imgs_sec: 'imgs/sec',
                api_offline: 'API unavailable. Try again later.',
                path_help_default: 'Select the "pics" folder from your installation.',
                path_help_mac: 'Typical path:\\n/Users/<user>/Applications/ProjectIgnis/pics',
                path_help_win: 'Typical path:\\nC\\\\ProjectIgnis\\\\pics\\nC\\\\Program Files\\\\ProjectIgnis\\\\pics',
                path_help_linux: 'Typical path:\\n~/.local/share/ProjectIgnis/pics\\n/usr/share/ProjectIgnis/pics',
                alert_invalid_path: 'Folder does not exist or is not "pics".',
                alert_valid_path: 'Valid folder selected',
                alert_found_pics: 'Found "pics" folder inside selected path',
                alert_picker_fail: 'Could not open folder picker',
                alert_picker_error: 'Error opening folder picker',
                alert_validate_error: 'Error validating folder',
                alert_need_path: 'Select an output folder',
                alert_concurrency: 'Concurrency must be between 1 and 50',
                alert_started: 'Download started',
                alert_done: 'Download completed',
                alert_done_errors: 'Download finished with errors',
                alert_cancelled: 'Cancel requested',
                alert_api_error: 'Connection error',
                alert_preview: 'Preview',
                cards: 'cards',
                footer: 'EDOPro HD Pics Downloader v3.0 · Data from '
            }
        };

        let lang = 'en';
        let theme = 'light';
        let themeLocked = false;
        let themeMedia = null;
        let polling = null;
        let startTime = null;
        let lastProcessed = 0;
        let detectionTimeoutId = null;
        let detectionInFlight = false;
        let lastSystem = null;
        let lastApiError = null;
        let lastReport = null;
        let noticeTimer = null;

        window.addEventListener('DOMContentLoaded', async () => {
            await loadConfig();
            applyLanguage();
            detectProjectIgnis();
        });

        document.getElementById('langSelect').addEventListener('change', async (e) => {
            lang = e.target.value;
            applyLanguage();
            await saveConfig({ lang });
        });

        document.getElementById('themeToggle').addEventListener('click', async () => {
            theme = theme === 'dark' ? 'light' : 'dark';
            themeLocked = true;
            applyTheme();
            await saveConfig({ theme });
        });

        function t(key) {
            return (STRINGS[lang] && STRINGS[lang][key]) || key;
        }

        function detectBrowserLang() {
            const nav = (navigator.language || 'en').toLowerCase();
            return nav.startsWith('es') ? 'es' : 'en';
        }

        function detectBrowserTheme() {
            if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
                return 'dark';
            }
            return 'light';
        }

        function applyTheme() {
            document.body.dataset.theme = theme;
            updateThemeToggle();
        }

        function updateThemeToggle() {
            const btn = document.getElementById('themeToggle');
            btn.textContent = theme === 'dark' ? t('theme_dark') : t('theme_light');
        }

        function applyLanguage() {
            document.documentElement.lang = lang;
            document.getElementById('titleText').textContent = t('title');
            document.getElementById('subtitleText').textContent = t('subtitle');
            document.getElementById('configTitle').textContent = t('config');
            document.getElementById('advancedTitle').textContent = t('advanced');
            document.getElementById('detectBtn').textContent = t('detect_retry');
            document.getElementById('pathLabel').textContent = t('path_label');
            document.getElementById('browseBtn').textContent = t('browse');
            document.getElementById('forceLabel').textContent = t('force');
            document.getElementById('onlyMissingLabel').textContent = t('only_missing');
            document.getElementById('validateLabel').textContent = t('validate_existing');
            document.getElementById('concurrencyLabel').textContent = t('concurrency');
            document.getElementById('retryLabel').textContent = t('retry');
            document.getElementById('timeoutLabel').textContent = t('timeout');
            document.getElementById('rateLabel').textContent = t('rate');
            document.getElementById('typeFilterLabel').textContent = t('type_filter');
            document.getElementById('setFilterLabel').textContent = t('set_filter');
            document.getElementById('typeFilter').placeholder = t('type_placeholder');
            document.getElementById('setFilter').placeholder = t('set_placeholder');
            document.getElementById('previewLabel').textContent = t('preview');
            document.getElementById('startBtn').textContent = t('start');
            document.getElementById('pauseBtn').textContent = t('pause');
            document.getElementById('cancelBtn').textContent = t('cancel');
            document.getElementById('progressTitle').textContent = t('progress');
            document.getElementById('totalLabel').textContent = t('total');
            document.getElementById('processedLabel').textContent = t('processed');
            document.getElementById('skippedLabel').textContent = t('skipped');
            document.getElementById('errorsLabel').textContent = t('errors');
            document.getElementById('timeLabel').textContent = t('time_eta');
            document.getElementById('logTitle').textContent = t('log_title');
            if (!polling) {
                document.getElementById('logContainer').innerHTML = '<div class="log-line info">' + t('waiting') + '</div>';
            }
            const footer = document.getElementById('footerText');
            footer.innerHTML = t('footer') + '<a href="https://db.ygoprodeck.com/" target="_blank">YGOProDeck API</a>';
            setHelpForSystem(lastSystem);
            updateThemeToggle();
        }

        async function loadConfig() {
            try {
                const response = await fetch('/api/config', { cache: 'no-store' });
                const cfg = await response.json();
                if (cfg && cfg.lang) {
                    lang = cfg.lang;
                } else {
                    lang = detectBrowserLang();
                    await saveConfig({ lang });
                }
                document.getElementById('langSelect').value = lang;
                if (cfg && cfg.theme) {
                    theme = cfg.theme;
                    themeLocked = true;
                } else {
                    theme = detectBrowserTheme();
                }
                if (cfg && cfg.last_settings) {
                    applySettings(cfg.last_settings);
                }
            } catch (e) {}

            if (window.matchMedia) {
                themeMedia = window.matchMedia('(prefers-color-scheme: dark)');
                const handler = (e) => {
                    if (themeLocked) return;
                    theme = e.matches ? 'dark' : 'light';
                    applyTheme();
                };
                if (themeMedia.addEventListener) {
                    themeMedia.addEventListener('change', handler);
                } else if (themeMedia.addListener) {
                    themeMedia.addListener(handler);
                }
            }
            applyTheme();
        }

        async function saveConfig(payload) {
            try {
                await fetch('/api/config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
            } catch (e) {}
        }

        function applySettings(s) {
            if (!s) return;
            if (s.picsdir) document.getElementById('picsdir').value = s.picsdir;
            if (typeof s.force === 'boolean') document.getElementById('force').checked = s.force;
            if (typeof s.onlyMissing === 'boolean') document.getElementById('onlyMissing').checked = s.onlyMissing;
            if (typeof s.validateExisting === 'boolean') document.getElementById('validateExisting').checked = s.validateExisting;
            if (s.concurrency) document.getElementById('concurrency').value = s.concurrency;
            if (s.retry) document.getElementById('retry').value = s.retry;
            if (s.timeout) document.getElementById('timeout').value = s.timeout;
            if (s.maxKbps !== undefined) document.getElementById('maxKbps').value = s.maxKbps;
            if (s.typeFilter) document.getElementById('typeFilter').value = s.typeFilter;
            if (s.setFilter) document.getElementById('setFilter').value = s.setFilter;
        }

        function setBadge(state, text) {
            const badge = document.getElementById('detectStatus');
            badge.className = 'badge' + (state ? ' ' + state : '');
            badge.textContent = text;
        }

        function setHint(text) {
            document.getElementById('detectHint').textContent = text;
        }

        function setHelpForSystem(system) {
            const help = document.getElementById('pathHelp');
            let text = t('path_help_default');
            if (system === 'macOS') {
                text = t('path_help_mac');
            } else if (system === 'Windows') {
                text = t('path_help_win');
            } else if (system === 'Linux') {
                text = t('path_help_linux');
            }
            help.dataset.tooltip = text;
            help.setAttribute('aria-label', text);
            help.setAttribute('title', text);
        }

        async function detectProjectIgnis() {
            detectionInFlight = true;
            setBadge('', t('detect_detecting'));
            setHint(t('detect_hint'));

            if (detectionTimeoutId) clearTimeout(detectionTimeoutId);
            detectionTimeoutId = setTimeout(() => {
                if (!detectionInFlight) return;
                detectionInFlight = false;
                setBadge('warn', t('detect_fail'));
                setHint(t('detect_fail_hint'));
                showAlert(t('detect_timeout'), 'warning');
            }, DETECT_TIMEOUT_MS);

            try {
                const controller = new AbortController();
                const abortTimeoutId = setTimeout(() => controller.abort(), DETECT_TIMEOUT_MS);

                const response = await fetch('/api/detect-projectignis', {
                    method: 'POST',
                    signal: controller.signal,
                    cache: 'no-store'
                });

                clearTimeout(abortTimeoutId);
                const result = await response.json();

                detectionInFlight = false;
                if (detectionTimeoutId) {
                    clearTimeout(detectionTimeoutId);
                    detectionTimeoutId = null;
                }

                lastSystem = result.system_name || result.system;
                setHelpForSystem(lastSystem);

                if (result.detected && result.path) {
                    setBadge('ok', t('detect_ok'));
                    setHint(t('detect_ok'));
                    document.getElementById('picsdir').value = result.path;
                    validateSelectedPath(result.path, false);
                } else {
                    setBadge('warn', t('detect_fail'));
                    setHint(t('detect_fail_hint'));
                }
            } catch (error) {
                detectionInFlight = false;
                if (detectionTimeoutId) {
                    clearTimeout(detectionTimeoutId);
                    detectionTimeoutId = null;
                }
                setBadge('warn', t('detect_fail'));
                setHint(t('detect_fail_hint'));
            }
        }

        function retryDetection() {
            detectProjectIgnis();
        }

        async function browseFolder() {
            try {
                const response = await fetch('/api/browse-folder', { method: 'POST' });
                const result = await response.json();

                if (result.success && result.path) {
                    document.getElementById('picsdir').value = result.path;
                    validateSelectedPath(result.path);
                } else {
                    showAlert(t('alert_picker_fail'), 'error');
                }
            } catch (error) {
                showAlert(t('alert_picker_error'), 'error');
            }
        }

        async function validateSelectedPath(path, applySuggestion = true) {
            try {
                const response = await fetch('/api/validate-path', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({path: path})
                });

                const result = await response.json();

                if (result.valid) {
                    if (result.is_pics_folder) {
                        showAlert(t('alert_valid_path'), 'success');
                    } else if (result.suggested_path) {
                        if (applySuggestion) {
                            document.getElementById('picsdir').value = result.suggested_path;
                        }
                        showAlert(t('alert_found_pics'), 'success');
                    } else {
                        showAlert(t('alert_invalid_path'), 'warning');
                    }
                    return true;
                } else {
                    showAlert(t('alert_invalid_path'), 'error');
                    return false;
                }
            } catch (error) {
                showAlert(t('alert_validate_error'), 'error');
                return false;
            }
        }

        document.getElementById('onlyMissing').addEventListener('change', (e) => {
            if (e.target.checked) {
                document.getElementById('force').checked = false;
            }
        });

        document.getElementById('force').addEventListener('change', (e) => {
            if (e.target.checked) {
                document.getElementById('onlyMissing').checked = false;
            }
        });

        document.getElementById('previewBtn').addEventListener('click', async (e) => {
            e.preventDefault();
            await previewDownload();
        });

        document.getElementById('startBtn').addEventListener('click', async (e) => {
            e.preventDefault();
            const picsdir = document.getElementById('picsdir').value.trim();
            if (!picsdir) {
                showAlert(t('alert_need_path'), 'error');
                return;
            }

            const ok = await validateSelectedPath(picsdir);
            if (!ok) return;

            await startDownload();
        });

        document.getElementById('pauseBtn').addEventListener('click', async () => {
            await togglePause();
        });

        document.getElementById('cancelBtn').addEventListener('click', async () => {
            await cancelDownload();
        });

        function collectFormData() {
            return {
                picsdir: document.getElementById('picsdir').value,
                force: document.getElementById('force').checked,
                onlyMissing: document.getElementById('onlyMissing').checked,
                validateExisting: document.getElementById('validateExisting').checked,
                concurrency: parseInt(document.getElementById('concurrency').value) || 12,
                timeout: parseInt(document.getElementById('timeout').value) || 30,
                retry: parseInt(document.getElementById('retry').value) || 3,
                maxKbps: parseInt(document.getElementById('maxKbps').value) || 0,
                typeFilter: document.getElementById('typeFilter').value.trim(),
                setFilter: document.getElementById('setFilter').value.trim()
            };
        }

        function setPreviewLoading(isLoading) {
            const btn = document.getElementById('previewBtn');
            btn.disabled = isLoading;
            btn.classList.toggle('loading', isLoading);
        }

        async function previewDownload() {
            const formData = collectFormData();
            setPreviewLoading(true);
            showAlert(t('preview_searching'), 'info');
            try {
                const response = await fetch('/api/preview', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(formData)
                });
                const result = await response.json();
                if (result.error) {
                    showAlert(result.error, 'error');
                    return;
                }
                showAlert(`${t('preview_found')}: ${result.to_download} / ${result.total_tasks} (${result.total_cards} ${t('cards')})`, 'info');
                document.getElementById('statTotal').textContent = result.total_tasks.toLocaleString();
            } catch (e) {
                showAlert(t('alert_api_error'), 'error');
            } finally {
                setPreviewLoading(false);
            }
        }

        async function startDownload() {
            const formData = collectFormData();

            if (formData.concurrency < 1 || formData.concurrency > 50) {
                showAlert(t('alert_concurrency'), 'error');
                return;
            }

            await saveConfig({ last_settings: formData });

            try {
                const response = await fetch('/api/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(formData)
                });

                const result = await response.json();

                if (response.ok) {
                    document.getElementById('startBtn').disabled = true;
                    document.getElementById('pauseBtn').disabled = false;
                    document.getElementById('cancelBtn').disabled = false;
                    document.querySelectorAll('input').forEach(input => {
                        input.disabled = true;
                    });

                    startTime = Date.now();
                    lastProcessed = 0;
                    startPolling();

                    showAlert(t('alert_started'), 'success');
                } else {
                    showAlert(result.error || t('alert_api_error'), 'error');
                }
            } catch (error) {
                showAlert(t('alert_api_error') + ': ' + error.message, 'error');
            }
        }

        async function togglePause() {
            try {
                const paused = document.getElementById('pauseBtn').dataset.paused === 'true';
                const endpoint = paused ? '/api/resume' : '/api/pause';
                await fetch(endpoint, { method: 'POST' });
            } catch (error) {}
        }

        async function cancelDownload() {
            if (!confirm(t('cancel') + '?')) return;

            try {
                await fetch('/api/cancel', {method: 'POST'});
                showAlert(t('alert_cancelled'), 'warning');
                document.getElementById('cancelBtn').disabled = true;
            } catch (error) {
                showAlert(t('alert_api_error') + ': ' + error.message, 'error');
            }
        }

        function startPolling() {
            document.getElementById('logContainer').innerHTML = '';

            polling = setInterval(async () => {
                try {
                    const response = await fetch('/api/status');
                    const data = await response.json();

                    updateUI(data);

                    if (data.finished) {
                        stopPolling();
                        document.getElementById('startBtn').disabled = false;
                        document.getElementById('pauseBtn').disabled = true;
                        document.getElementById('pauseBtn').dataset.paused = 'false';
                        document.getElementById('pauseBtn').textContent = t('pause');
                        document.getElementById('cancelBtn').disabled = true;
                        document.querySelectorAll('input').forEach(input => {
                            input.disabled = false;
                        });

                        if (data.errors > 0) {
                            showAlert(`${t('alert_done_errors')}: ${data.errors}`, 'warning');
                        } else if (data.processed > 0) {
                            showAlert(t('alert_done'), 'success');
                        }
                    }
                } catch (error) {
                    console.error('Error polling status:', error);
                }
            }, 500);
        }

        function stopPolling() {
            if (polling) {
                clearInterval(polling);
                polling = null;
            }
        }

        function updateUI(data) {
            const total = data.total || 1;
            const processed = data.processed || 0;
            const skipped = data.skipped || 0;
            const errors = data.errors || 0;
            const done = processed + skipped + errors;
            const pct = Math.min(100, Math.floor((done / total) * 100));

            const progressBar = document.getElementById('progressBar');
            progressBar.style.width = pct + '%';
            progressBar.textContent = pct + '%';

            document.getElementById('statTotal').textContent = total.toLocaleString();
            document.getElementById('statProcessed').textContent = processed.toLocaleString();
            document.getElementById('statSkipped').textContent = skipped.toLocaleString();
            document.getElementById('statErrors').textContent = errors.toLocaleString();

            const now = Date.now();
            const elapsedSeconds = (now - startTime) / 1000;
            const rate = processed / elapsedSeconds;
            document.getElementById('statSpeed').textContent = rate > 0 ? rate.toFixed(1) + ' ' + t('imgs_sec') : '-- ' + t('imgs_sec');

            document.getElementById('statElapsed').textContent = formatTime(elapsedSeconds);

            const remaining = total - done;
            const etaSeconds = rate > 0 ? remaining / rate : 0;
            document.getElementById('statEta').textContent = etaSeconds > 0 && isFinite(etaSeconds) ? formatTime(etaSeconds) : '--';

            if (data.logs && data.logs.length > 0) {
                const logContainer = document.getElementById('logContainer');
                const lastLogTimestamp = logContainer.dataset.lastTimestamp || 0;

                data.logs.forEach(log => {
                    if (log.timestamp > lastLogTimestamp) {
                        const line = document.createElement('div');
                        line.className = 'log-line ' + (log.type || 'info');
                        line.textContent = log.message;
                        logContainer.appendChild(line);
                    }
                });

                if (data.logs.length > 0) {
                    logContainer.dataset.lastTimestamp = data.logs[data.logs.length - 1].timestamp;
                }

                logContainer.scrollTop = logContainer.scrollHeight;
            }

            if (data.api_error && data.api_error !== lastApiError) {
                lastApiError = data.api_error;
                showAlert(t('api_offline'), 'warning');
            }

            if (data.report && data.report !== lastReport) {
                lastReport = data.report;
            }

            const pauseBtn = document.getElementById('pauseBtn');
            if (data.paused) {
                pauseBtn.dataset.paused = 'true';
                pauseBtn.textContent = t('resume');
            } else {
                pauseBtn.dataset.paused = 'false';
                pauseBtn.textContent = t('pause');
            }

            lastProcessed = processed;
        }

        function formatTime(seconds) {
            if (seconds < 60) {
                return Math.floor(seconds) + 's';
            } else if (seconds < 3600) {
                const mins = Math.floor(seconds / 60);
                const secs = Math.floor(seconds % 60);
                return mins + 'm ' + secs + 's';
            } else {
                const hours = (seconds / 3600).toFixed(1);
                return hours + 'h';
            }
        }

        function showAlert(message, type) {
            const notice = document.getElementById('noticeBar');
            if (noticeTimer) {
                clearTimeout(noticeTimer);
                noticeTimer = null;
            }
            if (!message) {
                notice.textContent = '';
                notice.className = 'notice';
                return;
            }
            notice.textContent = message;
            notice.className = 'notice show ' + (type || 'info');
            noticeTimer = setTimeout(() => {
                notice.textContent = '';
                notice.className = 'notice';
            }, 3000);
        }

        window.addEventListener('beforeunload', (e) => {
            if (polling) {
                e.preventDefault();
                e.returnValue = '';
            }
        });
    </script>
</body>
</html>
"""


class RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler"""
    
    def log_message(self, format, *args):
        """Silence HTTP server logs"""
        pass
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
        
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            
            with state.lock:
                response = {
                    'total': state.total,
                    'processed': state.processed,
                    'skipped': state.skipped,
                    'errors': state.errors,
                    'finished': not state.running,
                    'paused': state.pause_flag,
                    'api_error': state.api_error,
                    'report': state.report,
                    'logs': state.logs[-20:]
                }
            
            self.wfile.write(json.dumps(response).encode('utf-8'))

        elif self.path == '/api/config':
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            cfg = load_config()
            self.wfile.write(json.dumps(cfg).encode('utf-8'))
        
        else:
            self.send_error(404, 'Not Found')
    
    def do_POST(self):
        """Handle POST requests"""
        if self.path == '/api/config':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                params = json.loads(post_data.decode('utf-8'))
                save_config(params)
                response = {'status': 'saved'}
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode('utf-8'))
            except json.JSONDecodeError:
                self.send_error(400, 'Invalid JSON')
            return

        if self.path == '/api/detect-projectignis':
            """Auto-detect ProjectIgnis/EDOPro"""
            system = detect_system()
            detected_path = None
            
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(smart_detect_projectignis)
                    detected_path = future.result(timeout=4)
            except FuturesTimeoutError:
                state.add_log("Detection timed out, returning fallback response", 'warning')
            except Exception as e:
                state.add_log(f"Detection failed: {e}", 'error')
            
            response = {
                'detected': detected_path is not None,
                'path': detected_path,
                'system': system,
                'system_name': 'macOS' if system == 'Darwin' else system
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
        
        elif self.path == '/api/browse-folder':
            """Browse for folder using system dialog"""
            system = detect_system()
            folder_path = None
            
            try:
                if system == 'Darwin':
                    folder_path = run_applescript_folder_dialog()
                elif system == 'Windows':
                    folder_path = run_windows_folder_dialog()
                elif system == 'Linux':
                    folder_path = run_linux_folder_dialog()
            except Exception as e:
                state.add_log(f"Browse dialog error: {e}", 'error')
            
            response = {
                'path': folder_path,
                'success': folder_path is not None,
                'system': system
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
        
        elif self.path == '/api/validate-path':
            """Validate a given path exists and contains pics folder"""
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                params = json.loads(post_data.decode('utf-8'))
                path = params.get('path', '').strip()
                info = analyze_pics_path(path)
                
                response = {
                    'valid': info['exists'] and (info['is_pics_folder'] or bool(info['suggested_path'])),
                    'exists': info['exists'],
                    'is_pics_folder': info['is_pics_folder'],
                    'path': info['path'] if info['exists'] else None,
                    'suggested_path': info['suggested_path']
                }
                
            except json.JSONDecodeError:
                response = {'error': 'Invalid JSON'}
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))

        elif self.path == '/api/preview':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                params = json.loads(post_data.decode('utf-8'))
            except json.JSONDecodeError:
                self.send_error(400, 'Invalid JSON')
                return

            picsdir = params.get('picsdir', '').strip()
            force = params.get('force', False)
            only_missing = params.get('onlyMissing', False)
            validate_existing = params.get('validateExisting', False)
            if force:
                only_missing = False
                validate_existing = False
            type_filter = params.get('typeFilter', '')
            set_filter = params.get('setFilter', '')

            info = analyze_pics_path(picsdir)
            if info['suggested_path']:
                picsdir = info['suggested_path']
                info = analyze_pics_path(picsdir)
            if not info['exists'] or (not info['is_pics_folder'] and not info['suggested_path']):
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Invalid pics directory'}).encode('utf-8'))
                return

            try:
                data = http_get_json(API_URL, timeout=30)
                cards = data.get('data') or []
            except Exception as e:
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'error': f'API error: {e}'}).encode('utf-8'))
                return

            filtered_cards = filter_cards(cards, type_filter, set_filter)
            tasks = build_download_tasks(filtered_cards)
            filtered_tasks = filter_tasks(tasks, picsdir, only_missing, validate_existing)

            response = {
                'total_cards': len(filtered_cards),
                'total_tasks': len(tasks),
                'to_download': len(filtered_tasks)
            }
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
        
        elif self.path == '/api/pause':
            state.pause_flag = True
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'paused'}).encode('utf-8'))
        
        elif self.path == '/api/resume':
            with state.pause_cond:
                state.pause_flag = False
                state.pause_cond.notify_all()
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'resumed'}).encode('utf-8'))
        
        elif self.path == '/api/start':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                params = json.loads(post_data.decode('utf-8'))
            except json.JSONDecodeError:
                self.send_error(400, 'Invalid JSON')
                return
            
            if state.running:
                self.send_response(409)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'error': 'Download already in progress'
                }).encode('utf-8'))
                return
            
            state.reset()
            
            thread = threading.Thread(target=download_worker_main, args=(params,), daemon=True)
            thread.start()
            try:
                save_config({'last_settings': params})
            except Exception:
                pass
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'started'}).encode('utf-8'))
        
        elif self.path == '/api/cancel':
            state.cancel_flag = True
            with state.pause_cond:
                state.pause_flag = False
                state.pause_cond.notify_all()
            state.add_log("⚠️  Cancellation requested by user", 'warning')
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'cancelling'}).encode('utf-8'))
        
        else:
            self.send_error(404, 'Not Found')

def find_free_port(start_port=DEFAULT_PORT):
    """Find free port for server"""
    for port in range(start_port, start_port + MAX_PORT_ATTEMPTS):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('localhost', port))
            sock.close()
            return port
        except OSError:
            continue
    
    return None

def check_python_version():
    """Check Python version is adequate"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 7):
        msg = {
            'en': [
                "❌ ERROR: Python 3.7+ required",
                f"   Your version: Python {version.major}.{version.minor}.{version.micro}",
                "",
                "Please update Python from: https://www.python.org/downloads/"
            ],
            'es': [
                "❌ ERROR: Se requiere Python 3.7+",
                f"   Tu versión: Python {version.major}.{version.minor}.{version.micro}",
                "",
                "Actualiza Python desde: https://www.python.org/downloads/"
            ]
        }
        lang = detect_language()
        for line in msg.get(lang, msg['en']):
            print(line)
        sys.exit(1)

def main():
    """Main entry"""
    lang = detect_language()
    text = {
        'en': {
            'title1': "  🎴  EDOPro HD Pics Downloader - Web UI Edition v3.0",
            'title2': "      Yu-Gi-Oh! image downloader for EDOPro",
            'py': "✅ Python {ver} detected",
            'find_port': "🔍 Finding available port...",
            'port_fail': f"❌ ERROR: Could not find free port between {DEFAULT_PORT} and {DEFAULT_PORT + MAX_PORT_ATTEMPTS}",
            'port_fail_why': "This could be because:",
            'port_fail_1': "  • Another instance is already running",
            'port_fail_2': "  • Other services are using those ports",
            'port_solutions': "Solutions:",
            'port_sol_1': "  1. Close other program instances",
            'port_sol_2': "  2. Restart your Mac",
            'port_ok': "✅ Port {port} available",
            'server_start': "🚀 HTTP server started",
            'url': "📍 URL: {url}",
            'open_browser': "🌐 Opening browser...",
            'gui_open': "  ✅ WEB GUI OPENED IN YOUR BROWSER",
            'instructions': "📝 Instructions:",
            'inst_1': "  • Configure options in the web interface",
            'inst_2': "  • Click 'Start' to begin",
            'inst_3': "  • Progress updates in real time",
            'inst_4': "  • You can cancel anytime",
            'keep_open': "⚠️  DO NOT close this Terminal window while using the program",
            'stop_server': "⏹  To stop server: press Ctrl+C",
            'stopping': "  ⏹  Stopping server...",
            'stopped': "✅ Server stopped correctly",
            'thanks': "Thank you for using EDOPro HD Pics Downloader",
            'err_start': "❌ ERROR starting server: {err}",
            'err_start_why': "This could be because:",
            'err_start_1': "  • Insufficient permissions",
            'err_start_2': "  • Port already in use"
        },
        'es': {
            'title1': "  🎴  EDOPro HD Pics Downloader - Web UI Edition v3.0",
            'title2': "      Descargador de imágenes Yu-Gi-Oh! para EDOPro",
            'py': "✅ Python {ver} detectado",
            'find_port': "🔍 Buscando puerto disponible...",
            'port_fail': f"❌ ERROR: No se pudo encontrar un puerto libre entre {DEFAULT_PORT} y {DEFAULT_PORT + MAX_PORT_ATTEMPTS}",
            'port_fail_why': "Esto puede deberse a que:",
            'port_fail_1': "  • Otra instancia del programa ya está corriendo",
            'port_fail_2': "  • Otros servicios están usando esos puertos",
            'port_solutions': "Soluciones:",
            'port_sol_1': "  1. Cierra otras instancias del programa",
            'port_sol_2': "  2. Reinicia tu Mac",
            'port_ok': "✅ Puerto {port} disponible",
            'server_start': "🚀 Servidor HTTP iniciado",
            'url': "📍 URL: {url}",
            'open_browser': "🌐 Abriendo navegador...",
            'gui_open': "  ✅ GUI WEB ABIERTA EN TU NAVEGADOR",
            'instructions': "📝 Instrucciones:",
            'inst_1': "  • Configura las opciones en la interfaz web",
            'inst_2': "  • Haz clic en 'Iniciar' para comenzar",
            'inst_3': "  • El progreso se actualizará en tiempo real",
            'inst_4': "  • Puedes cancelar en cualquier momento",
            'keep_open': "⚠️  NO cierres esta ventana de Terminal mientras uses el programa",
            'stop_server': "⏹  Para detener el servidor: presiona Ctrl+C",
            'stopping': "  ⏹  Deteniendo servidor...",
            'stopped': "✅ Servidor detenido correctamente",
            'thanks': "Gracias por usar EDOPro HD Pics Downloader",
            'err_start': "❌ ERROR al iniciar el servidor: {err}",
            'err_start_why': "Esto puede deberse a:",
            'err_start_1': "  • Permisos insuficientes",
            'err_start_2': "  • El puerto ya está en uso"
        }
    }.get(lang, None)
    if text is None:
        text = {}

    def t(key):
        return text.get(key, "")

    print("═" * 70)
    print(t('title1'))
    print(t('title2'))
    print("═" * 70)
    print()
    
    check_python_version()
    print(t('py').format(ver=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"))
    print()
    
    print(t('find_port'))
    port = find_free_port()
    
    if port is None:
        print(t('port_fail'))
        print()
        print(t('port_fail_why'))
        print(t('port_fail_1'))
        print(t('port_fail_2'))
        print()
        print(t('port_solutions'))
        print(t('port_sol_1'))
        print(t('port_sol_2'))
        sys.exit(1)
    
    print(t('port_ok').format(port=port))
    print()
    
    try:
        server = HTTPServer(('localhost', port), RequestHandler)
        server_url = f'http://localhost:{port}'
        
        print(t('server_start'))
        print(t('url').format(url=server_url))
        print()
        print(t('open_browser'))
        
        webbrowser.open(server_url)
        
        print()
        print("═" * 70)
        print(t('gui_open'))
        print("═" * 70)
        print()
        print(t('instructions'))
        print(t('inst_1'))
        print(t('inst_2'))
        print(t('inst_3'))
        print(t('inst_4'))
        print()
        print(t('keep_open'))
        print(t('stop_server'))
        print()
        print("═" * 70)
        print()
        
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print()
            print()
            print("═" * 70)
            print(t('stopping'))
            print("═" * 70)
            server.shutdown()
            server.server_close()
            print()
            print(t('stopped'))
            print()
            print(t('thanks'))
            print()
    
    except OSError as e:
        print(t('err_start').format(err=e))
        print()
        print(t('err_start_why'))
        print(t('err_start_1'))
        print(t('err_start_2'))
        print()
        sys.exit(1)
    
    except Exception as e:
        print(f"❌ ERROR FATAL: {e}")
        print()
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
