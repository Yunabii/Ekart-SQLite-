import sqlite3

def init_db():
    con = sqlite3.connect("database.db")
    cur = con.cursor()

    with open("schema.sql") as f:
        cur.executescript(f.read())

    con.commit()
    con.close()
    print("Database created successfully!")

if __name__ == "__main__":
    init_db()