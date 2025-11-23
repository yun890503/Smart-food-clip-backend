from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector

app = FastAPI()

# CORS（你之前應該已經有，沒有就加）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 開發階段先放寬，之後再收緊
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB = {
    "host": "hnd1.clusters.zeabur.com",
    "port":"21682",
    "user": "root",
    "password": "ZJjLcqCY9hVMu10Q762U4n8p3ERAI5XG",
    "database": "zeabur",
}

def db_conn():
    return mysql.connector.connect(**DB)

# 1) 取得所有夾子列表
@app.get("/clips")
def list_clips():
    conn = db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, current_food, safe_days, warn_days, status
        FROM clip_settings
        ORDER BY id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

# 2) 取得單一夾子
@app.get("/clips/{clip_id}")
def get_clip(clip_id: int):
    conn = db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, current_food, safe_days, warn_days, status
        FROM clip_settings
        WHERE id = %s
    """, (clip_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="clip not found")

    return row

# 3) 更新單一夾子的通知設定
@app.put("/clips/{clip_id}")
def update_clip(clip_id: int, payload: dict):
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE clip_settings
        SET current_food = %s,
            safe_days    = %s,
            warn_days    = %s,
            status       = %s
        WHERE id = %s
    """, (
        payload.get("current_food"),
        payload.get("safe_days"),
        payload.get("warn_days"),
        payload.get("status", "idle"),
        clip_id,
    ))

    conn.commit()
    affected = cur.rowcount
    cur.close()
    conn.close()

    # ❌ 不要再用 affected == 0 當作「不存在」
    # if affected == 0:
    #     raise HTTPException(status_code=404, detail="clip not found")

    return {"message": "updated", "id": clip_id, "affected": affected}


# 4) 刪除夾子（如果你要）
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
