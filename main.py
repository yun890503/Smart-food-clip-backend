from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from datetime import datetime, date, timedelta
import requests

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB = {
    "host": "hnd1.clusters.zeabur.com",
    "port": "21682",
    "user": "root",
    "password": "ZJjLcqCY9hVMu10Q762U4n8p3ERAI5XG",
    "database": "zeabur",
}

def db_conn():
    return mysql.connector.connect(**DB)

# ====== LINE 推播 ======
LINE_CHANNEL_TOKEN = "2lozxJOvVLXD7lYR8T/SfT0SIfShfXuOrw7Nd0rHg3t9HZoTKJwmOaSH7Yvcgus/ZLzdpg2005w4A1SEMT9FFonU5ZnTR1N+75dard1O4oYoaukDEySHGlJbadLIs5LSIc2YOOsnl3TrDgZbpImYYgdB04t89/1O/w1cDnyilFU="
LINE_USER_ID = "U5e7511e60c22086da3ae3b68b389766b"
WEB_BASE_URL = "https://smart-food-clip-frontend.zeabur.app/"

def send_line_bubble(title: str, message: str, color: str = "#4CAF50", url: str | None = None):
    """
    用 LINE Messaging API 推送 Flex Bubble 給固定 USER_ID
    title  : 上面大的標題
    message: 下面內文
    color  : 標題文字顏色（綠 / 橘 / 紅）
    url    : 點整個 Bubble 要開啟的網址（預設為 WEB_BASE_URL）
    """
    if url is None:
        url = WEB_BASE_URL

    url = url or WEB_BASE_URL  # 再保險一次

    api_url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_TOKEN}",
    }

    payload = {
        "to": LINE_USER_ID,
        "messages": [
            {
                "type": "flex",
                "altText": "智慧保鮮夾提醒",
                "contents": {
                    "type": "bubble",
                    # ⭐ 在 bubble 的 body 上掛 action => 點整塊會開網址
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "md",
                        "action": {          # ← 這一段就是點擊跳轉
                            "type": "uri",
                            "label": "查看詳情",
                            "uri": url,
                        },
                        "contents": [
                            {
                                "type": "text",
                                "text": title,
                                "weight": "bold",
                                "size": "lg",
                                "color": color,
                            },
                            {
                                "type": "separator",
                                "margin": "md",
                            },
                            {
                                "type": "text",
                                "text": message,
                                "wrap": True,
                                "margin": "md",
                                "size": "sm",
                            },
                        ],
                    },
                },
            }
        ],
    }

    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=5)
        print("LINE status:", resp.status_code, resp.text)
    except Exception as e:
        print("❌ LINE Bubble 推播失敗：", e)


# ==========================
# 1) GET /clips
# ==========================
@app.get("/clips")
def list_clips():
    conn = db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT
            id,
            current_food,
            start_date,
            status,
            expire_days,
            days_left
        FROM clip_settings
        ORDER BY id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

# ==========================
# 2) GET /clips/{id}
# ==========================
@app.get("/clips/{clip_id}")
def get_clip(clip_id: int):
    conn = db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT
            id,
            current_food,
            start_date,
            status,
            expire_days,
            days_left
        FROM clip_settings
        WHERE id = %s
    """, (clip_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="clip not found")

    return row

# ==========================
# 3) PUT /clips/{id}
# ==========================
@app.put("/clips/{clip_id}")
def update_clip(clip_id: int, payload: dict):
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE clip_settings
        SET current_food = %s,
            expire_days  = %s,
            status       = %s,
            days_left    = %s
        WHERE id = %s
    """, (
        payload.get("current_food"),
        payload.get("expire_days"),
        payload.get("status", "idle"),
        payload.get("days_left"),
        clip_id,
    ))

    conn.commit()
    affected = cur.rowcount
    cur.close()
    conn.close()

    return {"message": "updated", "id": clip_id, "affected": affected}

# ==========================
# 4) DELETE /clips/{id}
# ==========================
@app.delete("/clips/{clip_id}")
def delete_clip(clip_id: int):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM clip_settings WHERE id = %s", (clip_id,))
    conn.commit()
    affected = cur.rowcount
    cur.close()
    conn.close()

    if affected == 0:
        raise HTTPException(status_code=404, detail="clip not found")

    return {"message": "deleted", "id": clip_id}

# ==========================
# 5) POST /clips
# ==========================
@app.post("/clips")
def create_clip(payload: dict):
    try:
        clip_id = payload.get("id")
        current_food = payload.get("current_food")
        expire_days = payload.get("expire_days") or 0
        status = payload.get("status", "idle")
        start_date = payload.get("start_date")
        days_left = payload.get("days_left") or expire_days

        if clip_id is None:
            raise HTTPException(status_code=400, detail="id is required")

        conn = db_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO clip_settings
                (id, current_food, expire_days, start_date, status, days_left)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            clip_id,
            current_food,
            expire_days,
            start_date,
            status,
            days_left,
        ))

        conn.commit()
        cur.close()
        conn.close()

        return {"message": "created", "id": clip_id}
    except Exception as e:
        print("❌ create_clip error:", e)
        raise HTTPException(status_code=500, detail=str(e))

# ==========================
# 6) ESP32 上報事件 event
# ==========================
@app.post("/clips/{clip_id}/event")
def clip_event(clip_id: int, payload: dict):
    event = payload.get("event")
    expire_days_from_esp = payload.get("expire_days")
    days_left_from_esp = payload.get("days_left")

    if event not in ("start", "update", "expiring", "expired"):
        raise HTTPException(status_code=400, detail="invalid event type")

    conn = db_conn()
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute("SELECT * FROM clip_settings WHERE id = %s", (clip_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="clip not found")

        current_food = row.get("current_food") or "未命名食品"
        expire_days_db = row.get("expire_days")
        start_date_db = row.get("start_date")

        # 如果 start_date 是 datetime，把它轉成 date
        if isinstance(start_date_db, datetime):
            start_date_db = start_date_db.date()

        # ===== START =====
        if event == "start":
            new_expire_days = expire_days_from_esp or expire_days_db or 0
            today = date.today()

            # ⭐ 預計到期日
            expire_date = today + timedelta(days=int(new_expire_days))
            expire_date_str = expire_date.strftime("%Y-%m-%d")

            cur.execute("""
                UPDATE clip_settings
                SET start_date = %s,
                    expire_days = %s,
                    days_left   = %s,
                    status      = %s
                WHERE id = %s
            """, (
                today,
                new_expire_days,
                days_left_from_esp,
                "counting",
                clip_id,
            ))
            conn.commit()

            # ⭐ LINE 通知帶上到期日
            send_line_bubble(
                "保存計時開始",
                f"{current_food} 保存計時已開始，共 {new_expire_days} 天。\n"
                f"預計到期日：{expire_date_str}",
                "#4CAF50"
            )

        # ===== UPDATE（每天更新，通常不推 LINE） =====
        elif event == "update":
            new_days_left = days_left_from_esp if days_left_from_esp is not None else row.get("days_left")

            cur.execute("""
                UPDATE clip_settings
                SET days_left = %s
                WHERE id = %s
            """, (new_days_left, clip_id))
            conn.commit()

        # ===== EXPIRING（7天 → 今日剩 ≤7） =====
        elif event == "expiring":
            effective_expire_days = expire_days_db or expire_days_from_esp

            # ⭐ 計算真正的到期日
            expire_date = (
                start_date_db + timedelta(days=int(effective_expire_days))
                if (start_date_db and effective_expire_days)
                else None
            )
            expire_date_str = expire_date.strftime("%Y-%m-%d") if expire_date else "未知"

            cur.execute("""
                UPDATE clip_settings
                SET status = %s,
                    days_left = %s
                WHERE id = %s
            """, ("expiring", days_left_from_esp, clip_id))
            conn.commit()

            send_line_bubble(
                "⚠ 即將到期",
                f"{current_food} 即將到期（剩 {days_left_from_esp} 天）。\n"
                f"預計到期日：{expire_date_str}",
                "#FF9800"
            )

        # ===== EXPIRED（days_left <= 0） =====
        elif event == "expired":
            expire_date = (
                start_date_db + timedelta(days=int(expire_days_db))
                if (start_date_db and expire_days_db)
                else None
            )
            expire_date_str = expire_date.strftime("%Y-%m-%d") if expire_date else "未知"

            cur.execute("""
                UPDATE clip_settings
                SET status = %s,
                    days_left = %s
                WHERE id = %s
            """, ("expired", 0, clip_id))
            conn.commit()

            send_line_bubble(
                "❌ 食品已過期",
                f"{current_food} 已超過保存期限。\n"
                f"原預計到期日：{expire_date_str}",
                "#F44336"
            )

    finally:
        cur.close()
        conn.close()

    return {"message": "event updated", "event": event}
