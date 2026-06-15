import sqlite3
import json


DB = "travel.db"


def connect():

    conn = sqlite3.connect(
        DB
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = connect()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS user_state(

        user_id TEXT PRIMARY KEY,

        step TEXT,

        temp TEXT

    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS schedules(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id TEXT,

        start_date TEXT,

        end_date TEXT,

        places TEXT

    )
    """)

    conn.commit()

    conn.close()


def save_state(
    user_id,
    step,
    temp
):

    conn = connect()

    conn.execute("""
    INSERT OR REPLACE
    INTO user_state
    VALUES
    (
        ?, ?, ?
    )
    """, (
        user_id,
        step,
        json.dumps(
            temp,
            ensure_ascii=False
        )
    ))

    conn.commit()

    conn.close()


def get_state(
    user_id
):

    conn = connect()

    cur = conn.execute("""
    SELECT *
    FROM user_state
    WHERE user_id=?
    """, (
        user_id,
    ))

    row = cur.fetchone()

    conn.close()

    if not row:

        return None

    return {

        "step":
        row["step"],

        "temp":
        json.loads(
            row["temp"]
        )

    }


def clear_state(
    user_id
):

    conn = connect()

    conn.execute("""
    DELETE
    FROM user_state
    WHERE user_id=?
    """, (
        user_id,
    ))

    conn.commit()

    conn.close()


def save_schedule(
    user_id,
    start,
    end,
    places
):

    conn = connect()

    conn.execute("""
    INSERT INTO schedules(

        user_id,

        start_date,

        end_date,

        places

    )

    VALUES
    (
        ?, ?, ?, ?
    )
    """, (

        user_id,

        start,

        end,

        json.dumps(
            places,
            ensure_ascii=False
        )

    ))

    conn.commit()

    conn.close()


def get_schedules(
    user_id
):

    conn = connect()

    cur = conn.execute("""
    SELECT *
    FROM schedules
    WHERE user_id=?
    ORDER BY id DESC
    """, (
        user_id,
    ))

    rows = cur.fetchall()

    conn.close()

    return rows


def delete_latest(
    user_id
):

    conn = connect()

    conn.execute("""
    DELETE
    FROM schedules

    WHERE id=(

        SELECT id

        FROM schedules

        WHERE user_id=?

        ORDER BY id DESC

        LIMIT 1

    )
    """, (
        user_id,
    ))

    conn.commit()

    conn.close()
