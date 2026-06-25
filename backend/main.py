from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
import threading
import time
import sqlite3

app = FastAPI(title="CSGO Market Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# локальная база данных чтобы не проебать свой апи
DB_NAME = "bot_data.db"


def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                item_id TEXT PRIMARY KEY,
                api_key TEXT,
                hash_name TEXT,
                min_price REAL
            )
        ''')
        conn.commit()


init_db()

# bot_state
bot_state = {
    "running": False,
    "thread": None,
    "logs": []
}


def add_log(msg: str):
    time_str = time.strftime('%H:%M:%S')
    bot_state["logs"].append(f"[{time_str}] {msg}")
    if len(bot_state["logs"]) > 30:
        bot_state["logs"].pop(0)


class InventoryRequest(BaseModel):
    api_key: str


class AddTaskRequest(BaseModel):
    api_key: str
    item_id: str
    hash_name: str
    min_price: float


class RemoveTaskRequest(BaseModel):
    item_id: str


def bot_worker():
    add_log("Главный воркер запущен. Чтение БД...")
    step_kopecks = 1

    while bot_state["running"]:
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks")
            tasks = cursor.fetchall()

        if not tasks:
            time.sleep(5)
            continue

        for task in tasks:
            if not bot_state["running"]:
                break

            item_id = task["item_id"]
            api_key = task["api_key"]
            hash_name = task["hash_name"]
            min_price_kopecks = int(round(task["min_price"] * 100))

            try:
                # 1. чтение цен наших шмоток
                our_item_url = f"https://market.csgo.com/api/v2/items?key={api_key}&cur=RUB"
                our_items_res = requests.get(our_item_url, timeout=10).json()

                current_our_price_kopecks = None
                if our_items_res.get('success'):
                    for item in our_items_res.get('items', []):
                        if str(item.get('item_id')) == str(item_id):
                            current_our_price_kopecks = int(item.get('price'))
                            break

                # 2. чтение цен чужих шмоток
                search_url = f"https://market.csgo.com/api/v2/search-item-by-hash-name?key={api_key}&hash_name={hash_name}&cur=RUB"
                search_res = requests.get(search_url, timeout=10).json()

                if search_res.get('success') and search_res.get('data'):
                    market_min_price_kopecks = int(
                        search_res['data'][0]['price'])
                    target_price_kopecks = max(
                        market_min_price_kopecks - step_kopecks, min_price_kopecks)

                    if current_our_price_kopecks is not None and current_our_price_kopecks == target_price_kopecks:
                        add_log(
                            f"[{hash_name}] Мы первые ({current_our_price_kopecks / 100:.2f} руб).")

                    elif market_min_price_kopecks > min_price_kopecks:
                        set_price_url = f"https://market.csgo.com/api/v2/set-price?key={api_key}&item_id={item_id}&price={target_price_kopecks}&cur=RUB"
                        set_response = requests.get(
                            set_price_url, timeout=10).json()

                        if set_response.get('success'):
                            add_log(
                                f"[{hash_name}] Законтрили хуесоса, новая цена: {target_price_kopecks / 100:.2f} руб.")
                        else:
                            error_msg = set_response.get('error', 'ошибка')
                            add_log(
                                f"[{hash_name}] Маркет отклонил запрос ({error_msg}).")
                    else:
                        add_log(f"[{hash_name}] Цена рынка ниже дна. Ждем.")
                else:
                    add_log(f"[{hash_name}] Предмет не найден в поиске.")

            except Exception as e:
                add_log(f"[{hash_name}] Ошибка сети: {e}")

            time.sleep(3)

        if bot_state["running"]:
            time.sleep(120)

    add_log("Главный воркер остановлен.")


@app.post("/api/get_inventory")
def get_inventory(req: InventoryRequest):
    url = f"https://market.csgo.com/api/v2/items?key={req.api_key}&cur=RUB"
    try:
        response = requests.get(url).json()
        if response.get('success'):
            items = response.get('items', [])
            for item in items:
                item['price'] = float(item['price'])
            return {"success": True, "items": items}
        raise HTTPException(status_code=400, detail="Ошибка API маркета")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/add_task")
def add_task(req: AddTaskRequest):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO tasks (item_id, api_key, hash_name, min_price)
            VALUES (?, ?, ?, ?)
        ''', (req.item_id, req.api_key, req.hash_name, req.min_price))
        conn.commit()

    add_log(f"В БД добавлен лот: {req.hash_name}")
    return {"success": True}


@app.post("/api/remove_task")
def remove_task(req: RemoveTaskRequest):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE item_id = ?", (req.item_id,))
        conn.commit()

    add_log(f"Лот удален из БД.")
    return {"success": True}


@app.get("/api/tasks")
def get_tasks():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT item_id, hash_name, min_price FROM tasks")
        rows = cursor.fetchall()

    tasks_dict = {
        row["item_id"]: {
            "hash_name": row["hash_name"],
            "min_price": row["min_price"]
        } for row in rows
    }
    return {"tasks": tasks_dict}


@app.post("/api/start")
def start_bot():
    if bot_state["running"]:
        return {"success": False, "message": "Воркер уже запущен"}
    bot_state["running"] = True
    bot_state["thread"] = threading.Thread(target=bot_worker, daemon=True)
    bot_state["thread"].start()
    return {"success": True}


@app.post("/api/stop")
def stop_bot():
    bot_state["running"] = False
    return {"success": True}


@app.get("/api/logs")
def get_logs():
    return {"logs": bot_state["logs"]}


app.mount("/", StaticFiles(directory="./static", html=True), name="static")
