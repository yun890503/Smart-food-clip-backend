from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from datetime import datetime, date
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

def send_line_bubble(title: str, message: str, color: str = "#4CAF50"):
    url = "https://api.line.me/v2/bot/message/push"
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
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "md",
                        "contents": [
                            {
                                "type": "text",
                                "text": title,
                                "weight": "bold",
                                "size": "lg",
                                "color": color,
                            },
                            {"type": "separator", "margin": "md"},
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
        resp = requests.post(url, headers=headers, json=payload, timeout=5)
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

        # ===== START =====
        if event == "start":
            new_expire_days = expire_days_from_esp or expire_days_db or 0
            cur.execute("""
                UPDATE clip_settings
                SET start_date = %s,
                    expire_days = %s,
                    days_left   = %s,
                    status      = %s
                WHERE id = %s
            """, (
                date.today(),
                new_expire_days,
                days_left_from_esp,  # ⭐ ESP32 傳來的
                "counting",
                clip_id,
            ))
            conn.commit()

            send_line_bubble(
                "保存計時開始",
                f"{current_food}保存計時已開始，共 {new_expire_days} 天。",
                "#4CAF50"
            )
        # ===== UPDATE：一般每天更新剩餘天數（不發 LINE）=====
        elif event == "update":
            # 如果 ESP 有傳 days_left，就更新；沒傳就用原本 DB 的
            new_days_left = days_left_from_esp
            if new_days_left is None:
                new_days_left = row.get("days_left")

            cur.execute("""
                UPDATE clip_settings
                SET days_left = %s
                WHERE id = %s
            """, (new_days_left, clip_id))
            conn.commit()
            # 不發 LINE，只是同步資料

        # ===== EXPIRING =====
        elif event == "expiring":
            cur.execute("""
                UPDATE clip_settings
                SET status = %s,
                    days_left = %s
                WHERE id = %s
            """, ("expiring", days_left_from_esp, clip_id))
            conn.commit()

            send_line_bubble(
                "⚠ 即將到期",
                f"{current_food}即將到期，約剩 {days_left_from_esp} 天。",
                "#FF9800"
            )

        # ===== EXPIRED =====
        elif event == "expired":
            cur.execute("""
                UPDATE clip_settings
                SET status = %s,
                    days_left = %s
                WHERE id = %s
            """, ("expired", 0, clip_id))
            conn.commit()

            send_line_bubble(
                "❌ 食品已過期",
                f"{current_food}已超過保存期限。",
                "#F44336"
            )

    finally:
        cur.close()
        conn.close()

    return {"message": "event updated", "event": event}
