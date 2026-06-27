import os
import json
import logging
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ["BOT_TOKEN"]

# ── хранилище (файл JSON) ──────────────────────────────────────────────────
DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data, uid):
    uid = str(uid)
    if uid not in data:
        data[uid] = {
            "tasks": [
                {"id": 1, "name": "Утренняя зарядка",   "points": 10, "emoji": "🏃"},
                {"id": 2, "name": "Чтение 30 минут",     "points": 15, "emoji": "📖"},
                {"id": 3, "name": "Питьевой режим (2л)", "points": 10, "emoji": "💧"},
                {"id": 4, "name": "Медитация",            "points": 20, "emoji": "🧘"},
                {"id": 5, "name": "Планирование дня",    "points": 10, "emoji": "📋"},
            ],
            "history": {},
            "today_checked": {},
            "today_date": "",
            "state": None,
        }
    u = data[uid]
    today = str(date.today())
    if u["today_date"] != today:
        # новый день — сохраняем вчера в историю
        if u["today_date"] and u["today_checked"]:
            earned = sum(t["points"] for t in u["tasks"] if str(t["id"]) in u["today_checked"])
            u["history"][u["today_date"]] = {"points": earned, "completed": len(u["today_checked"]), "total": len(u["tasks"])}
        u["today_checked"] = {}
        u["today_date"] = today
    return u

# ── клавиатура задач ───────────────────────────────────────────────────────
def tasks_keyboard(user):
    rows = []
    for t in user["tasks"]:
        done = str(t["id"]) in user["today_checked"]
        mark = "✅" if done else "⬜"
        rows.append([InlineKeyboardButton(
            f"{mark} {t['emoji']} {t['name']}  +{t['points']}б",
            callback_data=f"toggle_{t['id']}"
        )])
    earned = sum(t["points"] for t in user["tasks"] if str(t["id"]) in user["today_checked"])
    total  = sum(t["points"] for t in user["tasks"])
    pct    = int(earned / total * 100) if total else 0
    bar    = "█" * (pct // 10) + "░" * (10 - pct // 10)
    rows.append([
        InlineKeyboardButton("➕ Добавить задачу", callback_data="add_task"),
        InlineKeyboardButton("📊 История",          callback_data="history"),
    ])
    caption = f"📅 *{date.today().strftime('%d.%m.%Y')}*\n{bar} {pct}%\n💜 *{earned}* из *{total}* баллов"
    return caption, InlineKeyboardMarkup(rows)

# ── /start ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    save_data(data)
    text, kb = tasks_keyboard(user)
    await update.message.reply_text(
        f"Привет! 👋 Это твой ежедневный трекер.\n\n{text}",
        reply_markup=kb, parse_mode="Markdown"
    )

# ── callback-кнопки ────────────────────────────────────────────────────────
async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    uid  = str(query.from_user.id)
    user = get_user(data, uid)

    action = query.data

    if action.startswith("toggle_"):
        tid = action.split("_")[1]
        if tid in user["today_checked"]:
            del user["today_checked"][tid]
        else:
            user["today_checked"][tid] = True
        save_data(data)
        text, kb = tasks_keyboard(user)
        # проверяем 100%
        earned = sum(t["points"] for t in user["tasks"] if str(t["id"]) in user["today_checked"])
        total  = sum(t["points"] for t in user["tasks"])
        if earned == total and total > 0:
            text += "\n\n🎉 *Все задачи выполнены! Отличный день!*"
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

    elif action == "history":
        if not user["history"]:
            await query.edit_message_text("История пока пуста. Выполни задачи сегодня!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back")]]))
            save_data(data)
            return
        lines = ["📊 *История (последние 7 дней):*\n"]
        for d, h in sorted(user["history"].items(), reverse=True)[:7]:
            dd = date.fromisoformat(d).strftime("%d.%m")
            lines.append(f"`{dd}` — {h['points']} б  ({h['completed']}/{h['total']} задач)")
        total_week = sum(h["points"] for h in list(user["history"].values())[-7:])
        lines.append(f"\n💜 Итого за неделю: *{total_week} баллов*")
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back")]]), parse_mode="Markdown")
        save_data(data)

    elif action == "back":
        save_data(data)
        text, kb = tasks_keyboard(user)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

    elif action == "add_task":
        user["state"] = "awaiting_task"
        save_data(data)
        await query.edit_message_text(
            "Напиши задачу в формате:\n`эмодзи Название задачи : баллы`\n\nПример:\n`🏋️ Тренировка : 25`",
            parse_mode="Markdown"
        )

    elif action.startswith("del_"):
        tid = int(action.split("_")[1])
        user["tasks"] = [t for t in user["tasks"] if t["id"] != tid]
        user["today_checked"].pop(str(tid), None)
        save_data(data)
        text, kb = tasks_keyboard(user)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

# ── текстовые сообщения (добавление задачи) ───────────────────────────────
async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid  = str(update.effective_user.id)
    user = get_user(data, uid)

    if user.get("state") == "awaiting_task":
        user["state"] = None
        text = update.message.text.strip()
        try:
            left, right = text.rsplit(":", 1)
            points = int(right.strip())
            left   = left.strip()
            # первый символ — эмодзи (unicode > 127), остальное — название
            if ord(left[0]) > 127:
                emoji = left[0]
                name  = left[1:].strip()
            else:
                emoji = "⭐"
                name  = left
            new_id = max((t["id"] for t in user["tasks"]), default=0) + 1
            user["tasks"].append({"id": new_id, "name": name, "points": points, "emoji": emoji})
            save_data(data)
            task_text, kb = tasks_keyboard(user)
            await update.message.reply_text(f"✅ Задача добавлена!\n\n{task_text}", reply_markup=kb, parse_mode="Markdown")
        except Exception:
            save_data(data)
            await update.message.reply_text(
                "Не смог разобрать. Попробуй формат:\n`🏋️ Тренировка : 25`\n\nИли нажми /start чтобы вернуться.",
                parse_mode="Markdown"
            )
    else:
        save_data(data)
        text, kb = tasks_keyboard(user)
        await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")

# ── запуск ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.run_polling()
