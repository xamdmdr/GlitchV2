import re
import json
import random
import logging
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from data_manager import save_player_data, load_player_data, add_user

# Глобальный словарь для отслеживания сессий перевода
transfer_sessions = {}

def parse_recipient(text, event):
    """
    Определяет ID получателя по тексту сообщения или по пересланному/ответному сообщению.
    Сначала проверяются пересланные (fwd_messages) и ответные (reply_message) сообщения.
    Если их нет, производится поиск по шаблонам: vk.com/id12345, /id12345 или standalone id12345.
    Возвращает ID получателя в виде строки, если найден; иначе None.
    """
    message = event.obj.message or {}
    # Проверка пересланного сообщения
    fwd_msgs = message.get('fwd_messages', [])
    if fwd_msgs:
        recipient_id = fwd_msgs[0].get('from_id')
        if recipient_id:
            return str(recipient_id)
    # Проверка ответного сообщения
    reply = message.get('reply_message')
    if reply:
        recipient_id = reply.get('from_id')
        if recipient_id:
            return str(recipient_id)
    # Поиск по шаблонам
    match = re.search(r'vk\.com/id(\d+)', text)
    if match:
        return match.group(1)
    match = re.search(r'/id(\d+)', text)
    if match:
        return match.group(1)
    match = re.search(r'\bid(\d+)\b', text)
    if match:
        return match.group(1)
    return None

def initiate_transfer(sender_id, event, vk):
    """
    Инициирует сессию перевода.
    Если в event.obj.message присутствует reply_message, получатель определяется сразу и сессия переходит на этап ввода суммы.
    Если в тексте уже присутствует число (например, "Перевод 10"), то сумма берется из текста,
    и этап запроса суммы пропускается.
    В противном случае запрашивается указание получателя.
    """
    # Если event.obj.message является None, заменяем на {}
    message = event.obj.message or {}
    transfer_sessions[str(sender_id)] = {"stage": "recipient", "sender_id": str(sender_id)}
    # Если есть reply_message, сразу определяем получателя
    reply = message.get('reply_message')
    # Попытка извлечь сумму из текста
    text = message.get('text', '')
    sum_in_text = None
    parts = text.split()
    for part in parts:
        try:
            sum_in_text = int(part)
            break
        except:
            continue
    # Извлекаем peer_id из message; если отсутствует, устанавливаем равным sender_id
    peer_id = message.get('peer_id')
    if not peer_id:
        peer_id = sender_id
    if reply and reply.get('from_id'):
        transfer_sessions[str(sender_id)]["recipient"] = str(reply.get('from_id'))
        if sum_in_text is not None:
            transfer_sessions[str(sender_id)]["amount"] = sum_in_text
            transfer_sessions[str(sender_id)]["stage"] = "confirm"
            send_transfer_confirmation(sender_id, vk, peer_id)
        else:
            transfer_sessions[str(sender_id)]["stage"] = "amount"
            vk.messages.send(
                peer_id=peer_id,
                message="Введите сумму Glitch для перевода:",
                random_id=random.randint(1, 1000)
            )
    else:
        recipient = parse_recipient(text, event)
        if recipient:
            transfer_sessions[str(sender_id)]["recipient"] = recipient
            if sum_in_text is not None:
                transfer_sessions[str(sender_id)]["amount"] = sum_in_text
                transfer_sessions[str(sender_id)]["stage"] = "confirm"
                send_transfer_confirmation(sender_id, vk, peer_id)
            else:
                transfer_sessions[str(sender_id)]["stage"] = "amount"
                vk.messages.send(
                    peer_id=peer_id,
                    message="Введите сумму Glitch для перевода:",
                    random_id=random.randint(1, 1000)
                )
        else:
            vk.messages.send(
                peer_id=peer_id,
                message="Введите ссылку или тег игрока, которому нужно перевести Glitch. Либо ответьте на сообщение этого игрока.",
                random_id=random.randint(1, 1000)
            )

def send_transfer_confirmation(sender_id, vk, peer_id):
    """
    Отправляет сообщение с подтверждением перевода.
    Отправляется inline-клавиатура с кнопками подтверждения/отмены.
    Теперь уведомление получателю отправляется только после успешного подтверждения перевода.
    """
    session = transfer_sessions.get(str(sender_id))
    if not session:
        return
    amount = session.get("amount")
    recipient = session.get("recipient")
    sender_tag = f"vk.com/id{sender_id}"
    recipient_tag = f"vk.com/id{recipient}"
    keyboard = VkKeyboard(inline=True)
    keyboard.add_callback_button("Подтвердить", color=VkKeyboardColor.POSITIVE,
                                 payload={"command": "transfer_confirm", "action": "confirm"})
    keyboard.add_callback_button("Отменить", color=VkKeyboardColor.NEGATIVE,
                                 payload={"command": "transfer_confirm", "action": "cancel"})
    confirmation_msg = (f"Подтвердите перевод: вы ({sender_tag}) хотите отправить {amount} Glitch игроку ({recipient_tag}).")
    vk.messages.send(
        peer_id=peer_id,
        message=confirmation_msg,
        keyboard=keyboard.get_keyboard(),
        random_id=random.randint(1, 1000)
    )

def process_transfer(bot_event, sender_id, text, player_data, vk):
    """
    Обрабатывает входящее сообщение для перевода:
      1. На этапе "recipient" – пытается определить получателя из текста (если reply отсутствует).
      2. На этапе "amount" – проверяет корректность введенной суммы и переходит к подтверждению.
    Возвращает True, если сообщение обработано сессией перевода.
    """
    session = transfer_sessions.get(str(sender_id))
    if not session:
        return False

    stage = session.get("stage")
    peer_id = None
    if hasattr(bot_event.obj, "message") and bot_event.obj.message:
        peer_id = bot_event.obj.message.get('peer_id')
    else:
        peer_id = getattr(bot_event.obj, "peer_id", None)
    if not peer_id:
        peer_id = sender_id
    
    if stage == "recipient":
        recipient = parse_recipient(text, bot_event)
        if not recipient:
            vk.messages.send(
                peer_id=peer_id,
                message="Не удалось определить получателя. Укажите ссылку/тег или ответьте на сообщение игрока.",
                random_id=random.randint(1, 1000)
            )
            return True
        session["recipient"] = recipient
        session["stage"] = "amount"
        vk.messages.send(
            peer_id=peer_id,
            message="Введите сумму Glitch для перевода:",
            random_id=random.randint(1, 1000)
        )
        return True

    elif stage == "amount":
        try:
            amount = int(text)
            if amount <= 0:
                raise ValueError()
        except ValueError:
            vk.messages.send(
                peer_id=peer_id,
                message="Введите корректное число для суммы перевода.",
                random_id=random.randint(1, 1000)
            )
            return True
        sender_balance = int(player_data.get(str(sender_id), {}).get("balance", 0))
        if sender_balance < amount:
            vk.messages.send(
                peer_id=peer_id,
                message="Недостаточно средств для перевода.",
                random_id=random.randint(1, 1000)
            )
            del transfer_sessions[str(sender_id)]
            return True
        session["amount"] = amount
        session["stage"] = "confirm"
        send_transfer_confirmation(sender_id, vk, peer_id)
        return True

    return False

def process_transfer_confirmation(sender_id, action, player_data, vk, peer_id):
    """
    Обрабатывает callback подтверждения перевода.
    Если подтверждено, списывает средства у отправителя, добавляет их получателю и отправляет уведомление получателю.
    При отмене – завершает сессию перевода.
    """
    session = transfer_sessions.get(str(sender_id))
    if not session or session.get("stage") != "confirm":
        vk.messages.send(
            peer_id=peer_id,
            message="Сессия перевода не найдена или уже завершена.",
            random_id=random.randint(1, 1000)
        )
        return

    if action == "cancel":
        vk.messages.send(
            peer_id=peer_id,
            message="Перевод отменён.",
            random_id=random.randint(1, 1000)
        )
        del transfer_sessions[str(sender_id)]
        return

    if action == "confirm":
        amount = session.get("amount")
        recipient = session.get("recipient")
        sender_balance = int(player_data.get(str(sender_id), {}).get("balance", 0))
        if sender_balance < amount:
            vk.messages.send(
                peer_id=peer_id,
                message="Недостаточно средств для перевода.",
                random_id=random.randint(1, 1000)
            )
            del transfer_sessions[str(sender_id)]
            return
        # Списание средств у отправителя и зачисление получателю
        player_data[str(sender_id)]["balance"] -= amount
        if str(recipient) not in player_data:
            add_user(recipient, player_data, vk_name=f"Пользователь {recipient}")
        player_data[str(recipient)]["balance"] += amount
        save_player_data(player_data)
        vk.messages.send(
            peer_id=peer_id,
            message=(f"Перевод выполнен успешно! С вашего счета списано {amount} Glitch. Новый баланс: {player_data[str(sender_id)]['balance']} Glitch."),
            random_id=random.randint(1, 1000)
        )
        # Теперь уведомляем получателя только если перевод выполнен успешно
        vk.messages.send(
            peer_id=int(recipient),
            message=f"Вам переведен {amount} Glitch от vk.com/id{sender_id}.",
            random_id=random.randint(1, 1000)
        )
        del transfer_sessions[str(sender_id)]
        return