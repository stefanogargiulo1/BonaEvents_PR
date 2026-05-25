import sqlite3

conn = sqlite3.connect("tickets.db")

cursor = conn.cursor()

cursor.execute("""

CREATE TABLE IF NOT EXISTS tickets (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    ticket_code TEXT,

    event TEXT,
    rate TEXT,
    customer TEXT,
    email TEXT,
    phone TEXT

)

""")

conn.commit()

conn.close()

print("Database creato 😎")