import logging
import json
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── הגדרות ──────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID   = int(os.environ.get("ADMIN_ID", "0"))   # מזהה טלגרם של המנהל
GROUP_ID   = int(os.environ.get("GROUP_ID",  "0"))   # מזהה הקבוצה

DATA_FILE = "data.json"

# שלבי השאלון
(
    Q_LASTNAME, Q_VILLAGE, Q_PHOTO, Q_UNIT, Q_RANK,
    Q_HISTORY, Q_CONFIRM
) = range(7)

WELCOME_MSG = """
ברוך הבא לקבוצת החיילים הדרוזים 🫡

הנחיות התנהלות:
• כבוד הדדי בכל עת
• שפה מכבדת בלבד – ללא גסויות, ללא עלבונות
• איסור פרסום פרטים מזהים של חברים אחרים
• איסור צילומסך ושיתוף תוכן מחוץ לקבוצה
• נושאים פוליטיים – בנימוס ובאחריות
• במקרה של עבירה: אזהרה ראשונה, בשנייה – הוצאה

המספר שלך בקבוצה: #{number}
תהנה/י מהקבוצה! 💚
"""

RULES_VIOLATION_MSG = """
⚠️ אזהרה #{warn} – {name}

קיבלת אזהרה על עבירת הנחיות.
{"פעם הבאה תוצא/י מהקבוצה." if warn == 1 else ""}
"""

# ── ניהול נתונים ─────────────────────────────────────────

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"members": {}, "pending": {}, "counter": 0, "cooldowns": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── תהליך הצטרפות ────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()

    # בדיקת cooldown
    uid = str(user.id)
    if uid in data["cooldowns"]:
        until = datetime.fromisoformat(data["cooldowns"][uid])
        if datetime.now() < until:
            remaining = until - datetime.now()
            hours = int(remaining.total_seconds() // 3600)
            mins  = int((remaining.total_seconds() % 3600) // 60)
            await update.message.reply_text(
                f"❌ בקשתך נדחתה לאחרונה.\n"
                f"תוכל/י לנסות שוב בעוד {hours} שעות ו-{mins} דקות."
            )
            return ConversationHandler.END

    await update.message.reply_text(
        "שלום! 👋\n\n"
        "זהו תהליך הצטרפות לקבוצת החיילים הדרוזים.\n"
        "אנא ענה/י על השאלות הבאות. כל המידע נשמר בסודיות.\n\n"
        "1️⃣ מה שם המשפחה שלך?"
    )
    ctx.user_data["answers"] = {}
    return Q_LASTNAME

async def q_lastname(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["answers"]["lastname"] = update.message.text
    await update.message.reply_text("2️⃣ מאיזה כפר/עיר את/ה?")
    return Q_VILLAGE

async def q_village(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["answers"]["village"] = update.message.text
    await update.message.reply_text(
        "3️⃣ אנא העלה/י צילום של תג חוגר / תעודת לוחם / תעודת שחרור.\n\n"
        "✅ מותר להסתיר: מספר אישי, שם פרטי, תמונה\n"
        "✅ צריך להיות גלוי: שם משפחה, סוג התעודה"
    )
    return Q_PHOTO

async def q_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo and not update.message.document:
        await update.message.reply_text("⚠️ אנא העלה/י תמונה או קובץ.")
        return Q_PHOTO
    if update.message.photo:
        ctx.user_data["answers"]["photo_id"] = update.message.photo[-1].file_id
    else:
        ctx.user_data["answers"]["photo_id"] = update.message.document.file_id
    await update.message.reply_text("4️⃣ באיזו יחידה שירת/שירתת?")
    return Q_UNIT

async def q_unit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["answers"]["unit"] = update.message.text
    await update.message.reply_text("5️⃣ מה הדרגה הנוכחית / האחרונה שלך?")
    return Q_RANK

async def q_rank(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["answers"]["rank"] = update.message.text
    await update.message.reply_text(
        "6️⃣ מי חתם על הסכם גיוס הדרוזים לצה\"ל, ולמה הוא הסכים לכך?"
    )
    return Q_HISTORY

async def q_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["answers"]["history"] = update.message.text
    a = ctx.user_data["answers"]
    summary = (
        f"📋 סיכום בקשתך:\n\n"
        f"שם משפחה: {a['lastname']}\n"
        f"כפר/עיר: {a['village']}\n"
        f"יחידה: {a['unit']}\n"
        f"דרגה: {a['rank']}\n"
        f"תעודה: הועלתה ✅\n\n"
        f"האם לשלוח את הבקשה?"
    )
    keyboard = [[
        InlineKeyboardButton("✅ כן, שלח", callback_data="confirm_yes"),
        InlineKeyboardButton("❌ ביטול", callback_data="confirm_no")
    ]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
    return Q_CONFIRM

async def q_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if query.data == "confirm_no":
        await query.edit_message_text("❌ הבקשה בוטלה. תוכל/י להתחיל מחדש עם /start")
        return ConversationHandler.END

    a = ctx.user_data["answers"]
    data = load_data()

    # שמירה כממתין
    data["pending"][str(user.id)] = {
        "user_id": user.id,
        "username": user.username or "",
        "answers": a,
        "timestamp": datetime.now().isoformat()
    }
    save_data(data)

    # שליחה למנהל
    admin_text = (
        f"🔔 בקשת הצטרפות חדשה!\n\n"
        f"👤 טלגרם: @{user.username or 'אין'} (ID: {user.id})\n"
        f"שם משפחה: {a['lastname']}\n"
        f"כפר/עיר: {a['village']}\n"
        f"יחידה: {a['unit']}\n"
        f"דרגה: {a['rank']}\n"
        f"תשובה היסטורית: {a['history']}"
    )
    keyboard = [[
        InlineKeyboardButton("✅ אשר", callback_data=f"approve_{user.id}"),
        InlineKeyboardButton("❌ דחה",  callback_data=f"reject_{user.id}")
    ]]
    await ctx.bot.send_message(ADMIN_ID, admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
    await ctx.bot.send_photo(ADMIN_ID, a["photo_id"], caption="תעודת המבקש")

    await query.edit_message_text(
        "✅ בקשתך נשלחה למנהל לאישור.\n"
        "תקבל/י הודעה בקרוב. תודה על הסבלנות!"
    )
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ הבקשה בוטלה.")
    return ConversationHandler.END

# ── החלטת מנהל ──────────────────────────────────────────

async def admin_decision(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    action, uid = query.data.split("_", 1)
    uid = int(uid)
    data = load_data()
    pending = data["pending"].get(str(uid))

    if not pending:
        await query.edit_message_text("⚠️ לא נמצאה בקשה (אולי כבר טופלה)")
        return

    if action == "approve":
        # הקצאת מספר
        data["counter"] += 1
        member_number = data["counter"]
        data["members"][str(uid)] = {
            "number": member_number,
            "lastname": pending["answers"]["lastname"],
            "village": pending["answers"]["village"],
            "unit": pending["answers"]["unit"],
            "rank": pending["answers"]["rank"],
            "warnings": 0,
            "joined": datetime.now().isoformat()
        }
        del data["pending"][str(uid)]
        # הסרת cooldown אם יש
        data["cooldowns"].pop(str(uid), None)
        save_data(data)

        await ctx.bot.send_message(
            uid,
            f"🎉 בקשתך אושרה!\n\n" +
            WELCOME_MSG.format(number=str(member_number).zfill(3))
        )
        await query.edit_message_text(f"✅ {pending['answers']['lastname']} אושר/ה – מספר #{str(member_number).zfill(3)}")

    elif action == "reject":
        del data["pending"][str(uid)]
        # הגדרת cooldown 24 שעות
        data["cooldowns"][str(uid)] = (datetime.now() + timedelta(hours=24)).isoformat()
        save_data(data)

        await ctx.bot.send_message(
            uid,
            "❌ בקשתך לא אושרה הפעם.\n"
            "תוכל/י להגיש בקשה מחדש בעוד 24 שעות."
        )
        await query.edit_message_text(f"❌ {pending['answers']['lastname']} נדחה/תה")

# ── ניהול הקבוצה ────────────────────────────────────────

async def warn_member(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """פקודה למנהל: /warn [user_id]"""
    if update.effective_user.id != ADMIN_ID:
        return
    if not ctx.args:
        await update.message.reply_text("שימוש: /warn [מספר חבר]")
        return

    target_number = ctx.args[0].lstrip("#")
    data = load_data()

    # מציאת חבר לפי מספר
    target_uid = None
    target_member = None
    for uid, member in data["members"].items():
        if str(member["number"]) == target_number or str(member["number"]).zfill(3) == target_number:
            target_uid = int(uid)
            target_member = member
            break

    if not target_member:
        await update.message.reply_text("❌ חבר לא נמצא")
        return

    target_member["warnings"] += 1
    save_data(data)
    warn_count = target_member["warnings"]

    if warn_count == 1:
        await ctx.bot.send_message(
            target_uid,
            f"⚠️ קיבלת אזהרה ראשונה על עבירת הנחיות הקבוצה.\n"
            f"בעבירה הבאה תוצא/י מהקבוצה."
        )
        await update.message.reply_text(f"⚠️ אזהרה ראשונה נשלחה לחבר #{str(target_member['number']).zfill(3)}")
    else:
        # הוצאה מהקבוצה
        try:
            await ctx.bot.ban_chat_member(GROUP_ID, target_uid)
            await ctx.bot.send_message(target_uid, "❌ הוצאת מהקבוצה עקב עבירה חוזרת על ההנחיות.")
        except Exception as e:
            logger.error(f"Could not ban {target_uid}: {e}")
        del data["members"][str(target_uid)]
        save_data(data)
        await update.message.reply_text(f"🚫 חבר #{str(target_member['number']).zfill(3)} הוצא מהקבוצה")

async def list_members(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """פקודה למנהל: /members"""
    if update.effective_user.id != ADMIN_ID:
        return
    data = load_data()
    if not data["members"]:
        await update.message.reply_text("אין חברים עדיין")
        return
    lines = ["📋 רשימת חברים:\n"]
    for uid, m in sorted(data["members"].items(), key=lambda x: x[1]["number"]):
        warn_str = f" ⚠️×{m['warnings']}" if m["warnings"] > 0 else ""
        lines.append(f"#{str(m['number']).zfill(3)} | {m['lastname']} | {m['village']} | {m['rank']}{warn_str}")
    await update.message.reply_text("\n".join(lines))

async def new_member_joined(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """הודעה אוטומטית כשחבר נוסף לקבוצה"""
    for member in update.message.new_chat_members:
        data = load_data()
        uid = str(member.id)
        if uid in data["members"]:
            number = data["members"][uid]["number"]
            await update.message.reply_text(
                f"ברוכ/ה הבא/ה #{str(number).zfill(3)}! 🫡\n"
                f"קיבלת הודעה פרטית עם הנחיות הקבוצה."
            )

# ── הרצה ────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            Q_LASTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, q_lastname)],
            Q_VILLAGE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, q_village)],
            Q_PHOTO:    [MessageHandler(filters.PHOTO | filters.Document.ALL, q_photo)],
            Q_UNIT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, q_unit)],
            Q_RANK:     [MessageHandler(filters.TEXT & ~filters.COMMAND, q_rank)],
            Q_HISTORY:  [MessageHandler(filters.TEXT & ~filters.COMMAND, q_history)],
            Q_CONFIRM:  [CallbackQueryHandler(q_confirm, pattern="^confirm_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(admin_decision, pattern="^(approve|reject)_"))
    app.add_handler(CommandHandler("warn", warn_member))
    app.add_handler(CommandHandler("members", list_members))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_joined))

    logger.info("Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
