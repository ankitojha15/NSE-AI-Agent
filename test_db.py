from sqlalchemy import text

from app.database.database import engine

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))

        print("Database Connected Successfully!")

        for row in result:
            print(row)

except Exception as e:
    print("Connection Failed!")
    print(e)