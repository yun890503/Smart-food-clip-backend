from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from datetime import datetime, date
import requests  # 👈 新增，用來打 LINE API

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 開發階段先放寬，之後再收緊
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

def compute_days_left(start_date, expire_days):
    if start_date is None or expire_days is None:
        return None
    today = datetime.now().date()
    passed = (today - start_date).days      # 已經過幾天
    return expire_days - passed             # 剩幾天

def calc_days_left(row: dict):
    """
    統一計算 days_left：
    days_left = expire_days - 已經過的天數
    """
    start = row.get("start_date")
    expire_days = row.get("expire_days")
    if start is None or expire_days is None:
        return None

    # start_date 可能是 datetime 或 date
    if isinstance(start, datetime):
        start_date = start.date()
    else:
        start_date = start

    today = date.today()
    passed = (today - start_date).days  # 已經過幾天（今天 - 開始日）
    return expire_days - passed


# ====== LINE 推播（後端代打） ======

LINE_CHANNEL_TOKEN = "2lozxJOvVLXD7lYR8T/SfT0SIfShfXuOrw7Nd0rHg3t9HZoTKJwmOaSH7Yvcgus/ZLzdpg2005w4A1SEMT9FFonU5ZnTR1N+75dard1O4oYoaukDEySHGlJbadLIs5LSIc2YOOsnl3TrDgZbpImYYgdB04t89/1O/w1cDnyilFU="
LINE_USER_ID = "U5e7511e60c22086da3ae3b68b389766b"  # 先固定你自己，之後再做多使用者

def send_line_bubble(title: str, message: str, color: str = "#4CAF50"):
    """
    用 LINE Messaging API 推送 Flex Bubble 給固定 USER_ID
    title  : 上面大的標題
    message: 下面內文
    color  : 標題文字顏色（綠 / 橘 / 紅）
    """
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
        resp = requests.post(url, headers=headers, json=payload, timeout=5)
        print("LINE status:", resp.status_code, resp.text)
    except Exception as e:
        print("❌ LINE Bubble 推播失敗：", e)


# 1) 取得所有夾子列表（➜ 加上 expire_days & days_left）
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
            CASE
                WHEN expire_days IS NULL OR start_date IS NULL THEN NULL
                ELSE expire_days - DATEDIFF(CURDATE(), start_date)
            END AS days_left
        FROM clip_settings
        ORDER BY id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


# 2) 取得單一夾子（➜ 一樣回傳 days_left）
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
            CASE
                WHEN expire_days IS NULL OR start_date IS NULL THEN NULL
                ELSE expire_days - DATEDIFF(CURDATE(), start_date)
            END AS days_left
        FROM clip_settings
        WHERE id = %s
    """, (clip_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="clip not found")

    return row


# 3) 更新夾子設定（➜ 記得也要更新 expire_days）
@app.put("/clips/{clip_id}")
def update_clip(clip_id: int, payload: dict):
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE clip_settings
        SET current_food = %s,
            expire_days  = %s,
            status       = %s
        WHERE id = %s
    """, (
        payload.get("current_food"),
        payload.get("expire_days"),
        payload.get("status", "idle"),
        clip_id,
    ))

    conn.commit()
    affected = cur.rowcount
    cur.close()
    conn.close()

    return {"message": "updated", "id": clip_id, "affected": affected}

# 4) 刪除夾子
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

# 5) 新增夾子（POST）
@app.post("/clips")
def create_clip(payload: dict):
    try:
        clip_id = payload.get("id")
        current_food = payload.get("current_food")
        expire_days = payload.get("expire_days") or 0
        status = payload.get("status", "idle")
        start_date = payload.get("start_date")

        if clip_id is None:
            raise HTTPException(status_code=400, detail="id is required")

        conn = db_conn()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO clip_settings
                (id, current_food, expire_days, start_date, status)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            clip_id,
            current_food,
            expire_days,
            start_date,
            status,
        ))

        conn.commit()
        cur.close()
        conn.close()

        return {"message": "created", "id": clip_id}
    except Exception as e:
        print("❌ create_clip error:", e)
        raise HTTPException(status_code=500, detail=str(e))


# 6) ⭐ ESP32 回報事件：start / expiring / expired
@app.post("/clips/{clip_id}/event")
def clip_event(clip_id: int, payload: dict):
    """
    ESP32 用：
      - event: "start" / "expiring" / "expired"
      - expire_days: （選填）開始時可以順便更新總天數
      - days_left: （選填）如果 ESP 有算，也可以回報
    """
    from datetime import date

    event = payload.get("event")
    expire_days_from_esp = payload.get("expire_days")
    days_left_from_esp = payload.get("days_left")

    if event not in ("start", "expiring", "expired"):
        raise HTTPException(status_code=400, detail="invalid event type")

    conn = db_conn()
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute("SELECT * FROM clip_settings WHERE id = %s", (clip_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="clip not found")

        current_food = row.get("current_food") or "未命名食品"
        expire_days = row.get("expire_days")

        # ====== START ======
        if event == "start":
            new_expire = (
                expire_days_from_esp
                if expire_days_from_esp is not None
                else expire_days
            )
            if new_expire is None:
                new_expire = 0

            cur.execute(
                """
                UPDATE clip_settings
                SET start_date = %s,
                    expire_days = %s,
                    status = %s
                WHERE id = %s
                """,
                (date.today(), new_expire, "counting", clip_id),
            )
            conn.commit()

            title = "保存計時開始"
            msg = f"{current_food}保存計時已開始，共 {new_expire} 天。"
            # 綠色
            send_line_bubble(title, msg, "#4CAF50")

        # ====== EXPIRING ======
        elif event == "expiring":
            cur.execute(
                "UPDATE clip_settings SET status = %s WHERE id = %s",
                ("expiring", clip_id),
            )
            conn.commit()

            days_left = days_left_from_esp or 0
            title = "⚠ 即將到期"
            msg = f"{current_food}即將到期，約剩 {days_left} 天，請儘快食用。"
            # 橘色
            send_line_bubble(title, msg, "#FF9800")

        # ====== EXPIRED ======
        elif event == "expired":
            cur.execute(
                "UPDATE clip_settings SET status = %s WHERE id = %s",
                ("expired", clip_id),
            )
            conn.commit()

            title = "❌ 食品已過期"
            msg = f"{current_food}已超過保存期限，請確認是否丟棄。"
            # 紅色
            send_line_bubble(title, msg, "#F44336")

    finally:
        cur.close()
        conn.close()

    return {"message": "event updated", "event": event}

