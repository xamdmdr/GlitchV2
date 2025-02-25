import random
import hashlib
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from data_manager import save_player_data, add_game, remove_game, load_games
from utils import generate_result, generate_random_string

def show_games_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_callback_button("Орел-Решка", color=VkKeyboardColor.PRIMARY, payload={"command": "coinflip"})
    keyboard.add_callback_button("Мины", color=VkKeyboardColor.PRIMARY, payload={"command": "mines"})
    keyboard.add_callback_button("Бонус", color=VkKeyboardColor.POSITIVE, payload={"command": "get_glitch"})
    return keyboard.get_keyboard()

def start_coinflip(user_id, amount, player_data, vk, peer_id):
    if peer_id < 2000000000:
        vk.messages.send(
            peer_id=peer_id,
            message="Играть можно только в игровом чате.",
            random_id=random.randint(1, 1000)
        )
        return

    if amount <= 0:
        vk.messages.send(
            peer_id=peer_id,
            message="Ставка должна быть больше нуля.",
            random_id=random.randint(1, 1000)
        )
        return

    # Генерируем результат и вычисляем хэш игры единожды
    result, _ = generate_result()
    random_string = generate_random_string()
    # Вычисляем неизменяемый хэш игры
    game_hash = hashlib.md5(f"{result}|{random_string}".encode()).hexdigest()
    game_info = {
        "user_id": user_id,
        "amount": amount,
        "result": result,
        "game_hash": game_hash,
        "random_string": random_string,
        "timestamp": None
    }
    add_game(game_info)

    keyboard = VkKeyboard(inline=True)
    keyboard.add_callback_button("Орел", color=VkKeyboardColor.PRIMARY, payload={"command": "coinflip_choice", "choice": "heads"})
    keyboard.add_callback_button("Решка", color=VkKeyboardColor.PRIMARY, payload={"command": "coinflip_choice", "choice": "tails"})
    vk.messages.send(
        peer_id=peer_id,
        message=f"Вы выбрали ставку {amount}.\nХэш игры (для проверки честности): {game_hash}\nВыберите, на что ставите:",
        keyboard=keyboard.get_keyboard(),
        random_id=random.randint(1, 1000)
    )

def process_coinflip_choice(user_id, choice, player_data, vk, peer_id):
    games = load_games()
    game = games.get(str(user_id))
    if not game:
        vk.messages.send(
            peer_id=peer_id,
            message="Игра не найдена или уже завершена.",
            random_id=random.randint(1, 1000)
        )
        return

    amount = game["amount"]
    result = game["result"]
    game_hash = game["game_hash"]
    remove_game(user_id)

    if int(player_data.get(str(user_id), {}).get("balance", 0)) < amount:
        vk.messages.send(
            peer_id=peer_id,
            message="Недостаточно средств на балансе для этой ставки.",
            random_id=random.randint(1, 1000)
        )
        return

    player_data[str(user_id)]["balance"] -= amount

    if choice == result:
        winnings = amount * 2
        player_data[str(user_id)]["balance"] += winnings
        message = (
            f"Поздравляем! Вы выиграли {winnings}. Баланс: {player_data[str(user_id)]['balance']} Glitch⚡.\n"
            f"Хэш игры: {game_hash}\nПроверка честности: {result}|{game['random_string']}"
        )
    else:
        message = (
            f"Вы проиграли. Выпало: {result}. Баланс: {player_data[str(user_id)]['balance']} Glitch⚡.\n"
            f"Хэш игры: {game_hash}\nПроверка честности: {result}|{game['random_string']}"
        )
    vk.messages.send(
        peer_id=peer_id,
        message=message,
        random_id=random.randint(1, 1000)
    )
    save_player_data(player_data)