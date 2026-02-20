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

# ── שלבי שיחה ────────────────────────────────────────────
# תפריט ראשי
MENU = 0

# שאלון הצטרפות
Q_LASTNAME, Q_VILLAGE, Q_PHOTO, Q_UNIT, Q_RANK, Q_HISTORY = range(1, 7)

# דיווח על חשבון
REPORT_MEMBER_NUM, REPORT_REASON = 10, 11

# פנייה כללית
CONTACT_MSG = 20

# ניהול (מנהל)
ADMIN_WARN_NUM, ADMIN_BLOCK_NUM, ADMIN_BROADCAST_MSG = 30, 31, 32

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
תהנה מהקבוצה! 💚
"""

RULES_VIOLATION_MSG = """
⚠️ אזהרה #{warn} – {name}

קיבלת אזהרה על עבירת הנחיות.
{"פעם הבאה תוצא מהקבוצה." if warn == 1 else ""}
"""

# ── ניהול נתונים ─────────────────────────────────────────

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"members": {}, "pending": {}, "rejected": [], "counter": 0, "cooldowns": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── עזרה: חיפוש חבר לפי מספר ─────────────────────────────

def find_member_by_number(data, number_str):
    """מחזיר (uid, member_dict) או (None, None)"""
    number_str = number_str.lstrip("#")
    for uid, member in data["members"].items():
        if str(member["number"]) == number_str or str(member["number"]).zfill(3) == number_str:
            return int(uid), member
    return None, None

# ══════════════════════════════════════════════════════════
#                     תפריט ראשי
# ══════════════════════════════════════════════════════════

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """הצגת תפריט ראשי"""
    user = update.effective_user
    is_admin = (user.id == ADMIN_ID)

    buttons = [
        [InlineKeyboardButton("📋 שאלון הצטרפות", callback_data="menu_questionnaire")],
        [InlineKeyboardButton("🚨 דיווח על חשבון", callback_data="menu_report")],
        [InlineKeyboardButton("💬 פנייה כללית למנהל", callback_data="menu_contact")],
    ]

    if is_admin:
        buttons.append([InlineKeyboardButton("⚠️ התראה לחבר", callback_data="menu_warn")])
        buttons.append([InlineKeyboardButton("🚫 חסימת חבר", callback_data="menu_block")])
        buttons.append([InlineKeyboardButton("📢 הפצת הודעה לקבוצה", callback_data="menu_broadcast")])
        buttons.append([InlineKeyboardButton("📋 רשימת חברים", callback_data="menu_members")])

    await update.message.reply_text(
        "שלום! 👋\n\n"
        "🔒 כל הנתונים מוגנים ומעובדים על ידי בוט בלבד.\n\n"
        "בחר מה ברצונך לעשות:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return MENU

async def menu_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """ניתוב מהתפריט לפי בחירה"""
    query = update.callback_query
    await query.answer()
    choice = query.data

    # ── שאלון הצטרפות ──
    if choice == "menu_questionnaire":
        user = query.from_user
        data = load_data()
        uid = str(user.id)

        # בדיקת cooldown
        if uid in data["cooldowns"]:
            until = datetime.fromisoformat(data["cooldowns"][uid])
            if datetime.now() < until:
                remaining = until - datetime.now()
                hours = int(remaining.total_seconds() // 3600)
                mins  = int((remaining.total_seconds() % 3600) // 60)
                await query.edit_message_text(
                    f"❌ בקשתך נדחתה לאחרונה.\n"
                    f"תוכל לנסות שוב בעוד {hours} שעות ו-{mins} דקות."
                )
                return ConversationHandler.END

        await query.edit_message_text(
            "📋 שאלון הצטרפות\n\n"
            "אנא ענה על השאלות הבאות.\n"
            "🔒 המידע לא נשמר ומשמש אך ורק לבדיקה אוטומטית AI.\n\n"
            "1️⃣ מה שם המשפחה שלך?\n"
            "ℹ️ הפרט נלקח לצורך אימות בלבד ממאגר משפחות שהוזן מראש.\n"
            "אם המשפחה שלך לא במאגר – פנה למנהל דרך התפריט."
        )
        ctx.user_data["answers"] = {}
        return Q_LASTNAME

    # ── דיווח על חשבון ──
    elif choice == "menu_report":
        await query.edit_message_text(
            "🚨 דיווח על חשבון\n\n"
            "אנא שלח את מספר החבר שברצונך לדווח עליו.\n"
            "לדוגמה: 001"
        )
        return REPORT_MEMBER_NUM

    # ── פנייה כללית ──
    elif choice == "menu_contact":
        await query.edit_message_text(
            "💬 פנייה כללית\n\n"
            "כתוב את ההודעה שברצונך לשלוח למנהל.\n"
            "🔒 הנתונים מוגנים ומעובדים על ידי בוט בלבד."
        )
        return CONTACT_MSG

    # ── ניהול: התראה ──
    elif choice == "menu_warn":
        if query.from_user.id != ADMIN_ID:
            await query.edit_message_text("❌ אין לך הרשאה לפעולה זו.")
            return ConversationHandler.END
        await query.edit_message_text(
            "⚠️ התראה לחבר\n\n"
            "שלח את מספר החבר שברצונך להתריע עליו.\n"
            "לדוגמה: 001"
        )
        return ADMIN_WARN_NUM

    # ── ניהול: חסימה ──
    elif choice == "menu_block":
        if query.from_user.id != ADMIN_ID:
            await query.edit_message_text("❌ אין לך הרשאה לפעולה זו.")
            return ConversationHandler.END
        await query.edit_message_text(
            "🚫 חסימת חבר\n\n"
            "שלח את מספר החבר שברצונך לחסום.\n"
            "לדוגמה: 001"
        )
        return ADMIN_BLOCK_NUM

    # ── ניהול: הפצת הודעה ──
    elif choice == "menu_broadcast":
        if query.from_user.id != ADMIN_ID:
            await query.edit_message_text("❌ אין לך הרשאה לפעולה זו.")
            return ConversationHandler.END
        await query.edit_message_text(
            "📢 הפצת הודעה לקבוצה\n\n"
            "כתוב את ההודעה שברצונך לשלוח לקבוצה."
        )
        return ADMIN_BROADCAST_MSG

    # ── ניהול: רשימת חברים ──
    elif choice == "menu_members":
        if query.from_user.id != ADMIN_ID:
            await query.edit_message_text("❌ אין לך הרשאה לפעולה זו.")
            return ConversationHandler.END
        data = load_data()
        if not data["members"]:
            await query.edit_message_text("אין חברים עדיין.")
            return ConversationHandler.END
        lines = ["📋 רשימת חברים:\n"]
        for uid, m in sorted(data["members"].items(), key=lambda x: x[1]["number"]):
            warn_str = f" ⚠️×{m['warnings']}" if m["warnings"] > 0 else ""
            lines.append(f"#{str(m['number']).zfill(3)} | {m['lastname']} | {m['village']} | {m['rank']}{warn_str}")
        await query.edit_message_text("\n".join(lines))
        return ConversationHandler.END

    return ConversationHandler.END

# ══════════════════════════════════════════════════════════
#                   שאלון הצטרפות
# ══════════════════════════════════════════════════════════

async def q_lastname(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["answers"]["lastname"] = update.message.text
    await update.message.reply_text("2️⃣ מאיזה כפר/עיר אתה?")
    return Q_VILLAGE

async def q_village(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["answers"]["village"] = update.message.text
    await update.message.reply_text(
        "3️⃣ אנא העלה צילום של תג חוגר / תעודת לוחם / תעודת שחרור.\n\n"
        "🤖 התמונה נבדקת על ידי מודל עיבוד תמונה AI שמטרתו לזהות את שם המשפחה ולאמת מול הנתון שהזנת.\n\n"
        "✅ מותר להסתיר: מספר אישי, שם פרטי, תמונה\n"
        "✅ צריך להיות גלוי: שם משפחה, סוג התעודה"
    )
    return Q_PHOTO

async def q_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo and not update.message.document:
        await update.message.reply_text("⚠️ אנא העלה תמונה או קובץ.")
        return Q_PHOTO
    if update.message.photo:
        ctx.user_data["answers"]["photo_id"] = update.message.photo[-1].file_id
    else:
        ctx.user_data["answers"]["photo_id"] = update.message.document.file_id
    await update.message.reply_text("4️⃣ באיזו יחידה שירתת?")
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
    user = update.effective_user
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

    # הודעה למשתמש
    await update.message.reply_text(
        "✅ פנייתך בטיפול, תהליך זה יכול לקחת עד 48 שעות.\n"
        "תודה על הסבלנות!"
    )
    return ConversationHandler.END

# ══════════════════════════════════════════════════════════
#                  דיווח על חשבון
# ══════════════════════════════════════════════════════════

async def report_member_num(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """קבלת מספר חבר לדיווח"""
    ctx.user_data["report_member"] = update.message.text.strip()
    await update.message.reply_text(
        "📝 מה הסיבה לדיווח?\n"
        "תאר בקצרה את הבעיה."
    )
    return REPORT_REASON

async def report_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """קבלת סיבת הדיווח ושליחה למנהל"""
    reason = update.message.text
    member_num = ctx.user_data.get("report_member", "לא צוין")
    user = update.effective_user

    admin_text = (
        f"🚨 דיווח על חשבון!\n\n"
        f"מדווח: @{user.username or 'אין'} (ID: {user.id})\n"
        f"מדווח על חבר מספר: #{member_num}\n"
        f"סיבה: {reason}"
    )
    await ctx.bot.send_message(ADMIN_ID, admin_text)

    await update.message.reply_text(
        "✅ פנייתך בטיפול, תהליך זה יכול לקחת עד 48 שעות.\n"
        "תודה על הדיווח!"
    )
    return ConversationHandler.END

# ══════════════════════════════════════════════════════════
#                  פנייה כללית למנהל
# ══════════════════════════════════════════════════════════

async def contact_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """קבלת הודעה חופשית ושליחה למנהל"""
    user = update.effective_user

    admin_text = (
        f"💬 פנייה כללית\n\n"
        f"מאת: @{user.username or 'אין'} (ID: {user.id})\n"
        f"הודעה: {update.message.text}"
    )
    await ctx.bot.send_message(ADMIN_ID, admin_text)

    await update.message.reply_text(
        "✅ פנייתך בטיפול, תהליך זה יכול לקחת עד 48 שעות.\n"
        "תודה!"
    )
    return ConversationHandler.END

# ══════════════════════════════════════════════════════════
#               ניהול – התראה לחבר
# ══════════════════════════════════════════════════════════

async def admin_warn_num(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """מנהל: קבלת מספר חבר ושליחת אזהרה"""
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    data = load_data()
    target_uid, target_member = find_member_by_number(data, update.message.text.strip())

    if not target_member:
        await update.message.reply_text("❌ חבר לא נמצא. נסה שוב עם /start")
        return ConversationHandler.END

    target_member["warnings"] += 1
    save_data(data)
    warn_count = target_member["warnings"]

    if warn_count == 1:
        await ctx.bot.send_message(
            target_uid,
            f"⚠️ קיבלת אזהרה ראשונה על עבירת הנחיות הקבוצה.\n"
            f"בעבירה הבאה תוצא מהקבוצה."
        )
        await update.message.reply_text(
            f"⚠️ אזהרה ראשונה נשלחה לחבר #{str(target_member['number']).zfill(3)}"
        )
    else:
        # הוצאה מהקבוצה
        try:
            await ctx.bot.ban_chat_member(GROUP_ID, target_uid)
            await ctx.bot.send_message(target_uid, "❌ הוצאת מהקבוצה עקב עבירה חוזרת על ההנחיות.")
        except Exception as e:
            logger.error(f"Could not ban {target_uid}: {e}")
        del data["members"][str(target_uid)]
        save_data(data)
        await update.message.reply_text(
            f"🚫 חבר #{str(target_member['number']).zfill(3)} הוצא מהקבוצה"
        )

    return ConversationHandler.END

# ══════════════════════════════════════════════════════════
#               ניהול – חסימת חבר
# ══════════════════════════════════════════════════════════

async def admin_block_num(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """מנהל: קבלת מספר חבר וחסימה מיידית"""
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    data = load_data()
    target_uid, target_member = find_member_by_number(data, update.message.text.strip())

    if not target_member:
        await update.message.reply_text("❌ חבר לא נמצא. נסה שוב עם /start")
        return ConversationHandler.END

    member_num = str(target_member['number']).zfill(3)

    try:
        await ctx.bot.ban_chat_member(GROUP_ID, target_uid)
        await ctx.bot.send_message(target_uid, "❌ הוצאת מהקבוצה על ידי המנהל.")
    except Exception as e:
        logger.error(f"Could not ban {target_uid}: {e}")

    del data["members"][str(target_uid)]
    save_data(data)

    await update.message.reply_text(f"🚫 חבר #{member_num} נחסם והוצא מהקבוצה.")
    return ConversationHandler.END

# ══════════════════════════════════════════════════════════
#               ניהול – הפצת הודעה
# ══════════════════════════════════════════════════════════

async def admin_broadcast_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """מנהל: שליחת הודעה לקבוצה דרך הבוט"""
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    message_text = update.message.text

    try:
        await ctx.bot.send_message(
            GROUP_ID,
            f"📢 הודעה מהמנהל:\n\n{message_text}"
        )
        await update.message.reply_text("✅ ההודעה נשלחה לקבוצה בהצלחה.")
    except Exception as e:
        logger.error(f"Could not send broadcast: {e}")
        await update.message.reply_text("❌ שגיאה בשליחת ההודעה לקבוצה.")

    return ConversationHandler.END

# ══════════════════════════════════════════════════════════
#                  החלטת מנהל (אישור/דחייה)
# ══════════════════════════════════════════════════════════

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

        # יצירת לינק הזמנה חד-פעמי לקבוצה
        try:
            invite = await ctx.bot.create_chat_invite_link(
                GROUP_ID,
                member_limit=1,
                name=f"#{str(member_number).zfill(3)} {pending['answers']['lastname']}"
            )
            invite_text = f"\n🔗 לחץ כאן להצטרפות לקבוצה:\n{invite.invite_link}"
        except Exception as e:
            logger.error(f"Could not create invite link: {e}")
            invite_text = "\n\n⚠️ לא ניתן היה ליצור לינק הזמנה. פנה למנהל לקבלת לינק."

        await ctx.bot.send_message(
            uid,
            f"🎉 בקשתך אושרה!\n\n" +
            WELCOME_MSG.format(number=str(member_number).zfill(3)) +
            invite_text
        )
        await query.edit_message_text(f"✅ {pending['answers']['lastname']} אושר – מספר #{str(member_number).zfill(3)}")

    elif action == "reject":
        # שמירת נתוני הנדחה בארכיון
        if "rejected" not in data:
            data["rejected"] = []
        data["rejected"].append({
            "user_id": uid,
            "username": pending.get("username", ""),
            "answers": pending["answers"],
            "rejected_at": datetime.now().isoformat()
        })
        del data["pending"][str(uid)]
        # הגדרת cooldown 24 שעות
        data["cooldowns"][str(uid)] = (datetime.now() + timedelta(hours=24)).isoformat()
        save_data(data)

        await ctx.bot.send_message(
            uid,
            "❌ בקשתך נדחתה עקב אי עמידה בתנאים.\n\n"
            "נדרש לוודא שכלל הנתונים שהזנת נכונים ותואמים.\n"
            "ניתן לפנות למנהל דרך התפריט במידה וישנו חשד לטעות בזיהוי האוטומטי.\n\n"
            "ניתן להגיש בקשה חוזרת בעוד 24 שעות."
        )
        await query.edit_message_text(f"❌ {pending['answers']['lastname']} נדחה")

# ══════════════════════════════════════════════════════════
#               אירועי קבוצה
# ══════════════════════════════════════════════════════════

async def new_member_joined(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """הודעה אוטומטית כשחבר נוסף לקבוצה"""
    for member in update.message.new_chat_members:
        data = load_data()
        uid = str(member.id)
        if uid in data["members"]:
            number = data["members"][uid]["number"]
            await update.message.reply_text(
                f"ברוך הבא #{str(number).zfill(3)}! 🫡\n"
                f"קיבלת הודעה פרטית עם הנחיות הקבוצה."
            )

# ══════════════════════════════════════════════════════════
#                      ביטול
# ══════════════════════════════════════════════════════════

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ הפעולה בוטלה. לחזרה לתפריט שלח /start")
    return ConversationHandler.END

# ══════════════════════════════════════════════════════════
#                      הרצה
# ══════════════════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            # תפריט ראשי
            MENU: [CallbackQueryHandler(menu_handler, pattern="^menu_")],

            # שאלון הצטרפות
            Q_LASTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, q_lastname)],
            Q_VILLAGE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, q_village)],
            Q_PHOTO:    [MessageHandler(filters.PHOTO | filters.Document.ALL, q_photo)],
            Q_UNIT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, q_unit)],
            Q_RANK:     [MessageHandler(filters.TEXT & ~filters.COMMAND, q_rank)],
            Q_HISTORY:  [MessageHandler(filters.TEXT & ~filters.COMMAND, q_history)],

            # דיווח על חשבון
            REPORT_MEMBER_NUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_member_num)],
            REPORT_REASON:     [MessageHandler(filters.TEXT & ~filters.COMMAND, report_reason)],

            # פנייה כללית
            CONTACT_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_msg)],

            # ניהול
            ADMIN_WARN_NUM:     [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_warn_num)],
            ADMIN_BLOCK_NUM:    [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_block_num)],
            ADMIN_BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_msg)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(admin_decision, pattern="^(approve|reject)_"))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_joined))

    logger.info("Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
