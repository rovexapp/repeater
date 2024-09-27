import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, CallbackContext
from telegram.error import BadRequest
import os

TOKEN = os.getenv("BOT_TOKEN")  # استخدم المتغير البيئي BOT_TOKEN

group_settings = {}

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("مرحباً! استخدم الأمر /setup لتهيئة الإعدادات (فقط للمالك أو المشرفين).")

async def is_admin(update: Update, context: CallbackContext) -> bool:
    try:
        chat_member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return chat_member.status in ['administrator', 'creator']
    except BadRequest:
        return False

async def setup(update: Update, context: CallbackContext):
    if not await is_admin(update, context):
        return

    keyboard = [
        [InlineKeyboardButton("إعداد الرسالة في القروب", callback_data='setup_in_group')],
        [InlineKeyboardButton("إعداد الرسالة بشكل خاص", callback_data='setup_in_private')]
    ]
    await update.message.reply_text("أين ترغب في إعداد الرسالة؟", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_click(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == 'setup_in_group':
        await query.edit_message_text("يرجى إدخال الرسالة المراد تكرارها في القروب.")
        await ask_for_message(query, context, group_mode=True)
    elif query.data == 'setup_in_private':
        await query.edit_message_text("سيتم تحويلك إلى البوت لإعداد الرسالة بشكل خاص.")
        # إرسال رسالة للمستخدم في الخاص لبدء إعداد الرسالة
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text="يرجى إدخال الرسالة المراد تكرارها في القروب عبر المحادثة الخاصة."
        )
        # تخزين معرف القروب لكي يتم تطبيق الإعدادات عليه بعد اكتمال الإعداد في الخاص
        context.user_data['group_id'] = query.message.chat.id
        context.user_data['step'] = 'waiting_for_message_in_private'

async def ask_for_message(update: Update, context: CallbackContext, group_mode=False, keep_old=False):
    group_id = update.message.chat.id if update.message else update.callback_query.message.chat.id

    if not keep_old:
        group_settings[group_id] = {}

    await context.bot.send_message(chat_id=group_id, text="الرجاء إدخال الرسالة.")
    context.user_data['group_id'] = group_id
    context.user_data['step'] = 'waiting_for_message'

async def handle_message(update: Update, context: CallbackContext):
    step = context.user_data.get('step')

    # عند إعداد الرسالة في المحادثة الخاصة
    if step == 'waiting_for_message_in_private':
        group_id = context.user_data['group_id']
        group_settings[group_id] = {'message': update.message.text}
        await update.message.reply_text("الرجاء إدخال مدة التكرار بالثواني.")
        context.user_data['step'] = 'waiting_for_interval_in_private'
    elif step == 'waiting_for_interval_in_private':
        try:
            interval = int(update.message.text)
            group_id = context.user_data['group_id']
            group_settings[group_id]['interval'] = interval
            await update.message.reply_text("الرجاء إدخال مدة الحذف بالثواني (أو اكتب 'no' لتعطيل الحذف).")
            context.user_data['step'] = 'waiting_for_delete_time_in_private'
        except ValueError:
            await update.message.reply_text("يرجى إدخال رقم صالح للمدة بالثواني.")
    elif step == 'waiting_for_delete_time_in_private':
        group_id = context.user_data['group_id']
        if update.message.text.lower() == 'no':
            group_settings[group_id]['delete_time'] = None
        else:
            try:
                delete_time = int(update.message.text)
                group_settings[group_id]['delete_time'] = delete_time
            except ValueError:
                await update.message.reply_text("يرجى إدخال رقم صالح لمدة الحذف بالثواني.")
                return
        await update.message.reply_text("هل تريد إضافة أزرار؟ (yes أو no)")
        context.user_data['step'] = 'waiting_for_buttons_in_private'
    elif step == 'waiting_for_buttons_in_private':
        group_id = context.user_data['group_id']
        if update.message.text.lower() == 'yes':
            await update.message.reply_text("كم عدد الأزرار التي تريد إضافتها؟")
            context.user_data['step'] = 'waiting_for_button_count_in_private'
        else:
            await update.message.reply_text("تم حفظ الإعدادات بنجاح. سيتم تكرار الرسالة في القروب.")
            await schedule_message(group_id, context)
    elif step == 'waiting_for_button_count_in_private':
        try:
            button_count = int(update.message.text)
            group_id = context.user_data['group_id']
            group_settings[group_id]['buttons'] = True
            group_settings[group_id]['button_count'] = button_count
            group_settings[group_id]['buttons_info'] = []
            await update.message.reply_text("يرجى إدخال اسم الزر والرابط بالشكل التالي: \nاسم الزر, الرابط")
            context.user_data['step'] = 'waiting_for_button_info_in_private'
        except ValueError:
            await update.message.reply_text("يرجى إدخال رقم صالح لعدد الأزرار.")
    elif step == 'waiting_for_button_info_in_private':
        try:
            button_text, button_url = update.message.text.split(',')
            group_id = context.user_data['group_id']
            group_settings[group_id]['buttons_info'].append({
                'text': button_text.strip(),
                'url': button_url.strip()
            })
            if len(group_settings[group_id]['buttons_info']) < group_settings[group_id]['button_count']:
                await update.message.reply_text("يرجى إدخال الزر التالي بالشكل: \nاسم الزر, الرابط")
            else:
                await update.message.reply_text("هل تريد عرض الأزرار بجانب بعضها؟ (اكتب 'جنب' أو 'تحت')")
                context.user_data['step'] = 'waiting_for_button_layout_in_private'
        except ValueError:
            await update.message.reply_text("يرجى إدخال البيانات بالشكل المطلوب: \nاسم الزر, الرابط")
    elif step == 'waiting_for_button_layout_in_private':
        layout = update.message.text.lower()
        group_id = context.user_data['group_id']
        if layout in ['جنب', 'تحت']:
            group_settings[group_id]['layout'] = layout
            await update.message.reply_text("تم حفظ الإعدادات بنجاح. سيتم تكرار الرسالة في القروب.")
            await schedule_message(group_id, context)
        else:
            await update.message.reply_text("يرجى اختيار إما 'جنب' أو 'تحت'.")

async def send_message(context: CallbackContext, group_id, message_text, buttons):
    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
    message = await context.bot.send_message(chat_id=group_id, text=message_text, reply_markup=reply_markup)
    return message

async def delete_message(context: CallbackContext, group_id, message_id):
    await asyncio.sleep(group_settings[group_id]['delete_time'])
    await context.bot.delete_message(chat_id=group_id, message_id=message_id)

async def schedule_message(group_id, context: CallbackContext):
    settings = group_settings[group_id]
    message_text = settings['message']
    interval = settings['interval']
    delete_time = settings['delete_time'] if isinstance(settings['delete_time'], int) else 0

    async def repeat():
        while True:
            buttons = []
            if settings.get('buttons'):
                if settings['layout'] == 'جنب':
                    buttons = [[InlineKeyboardButton(btn['text'], url=btn['url']) for btn in settings['buttons_info']]]
                else:
                    buttons = [[InlineKeyboardButton(btn['text'], url=btn['url'])] for btn in settings['buttons_info']]

            sent_message = await send_message(context, group_id, message_text, buttons)
            if delete_time > 0:
                asyncio.create_task(delete_message(context, group_id, sent_message.message_id))
            await asyncio.sleep(interval)

    asyncio.create_task(repeat())

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()

    start_handler = CommandHandler('start', start)
    setup_handler = CommandHandler('setup', setup)
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    button_handler = CallbackQueryHandler(button_click)

    application.add_handler(start_handler)
    application.add_handler(setup_handler)
    application.add_handler(message_handler)
    application.add_handler(button_handler)

    application.run_polling()

