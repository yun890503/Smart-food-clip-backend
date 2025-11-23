from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from datetime import datetime, date

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
    days_left = safe_days - 已經過的天數
    """
    start = row.get("start_date")
    safe_days = row.get("safe_days")
    if start is None or safe_days is None:
        return None

    # start_date 可能是 datetime 或 date
    if isinstance(start, datetime):
        start_date = start.date()
    else:
        start_date = start

    today = date.today()
    passed = (today - start_date).days  # 已經過幾天（今天 - 開始日）
    return safe_days - passed


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

# 3) 新增夾子（POST）
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

