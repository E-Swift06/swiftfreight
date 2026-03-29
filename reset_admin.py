import sqlite3

conn = sqlite3.connect("shipping.db")
c = conn.cursor()

# delete old admin
c.execute("DELETE FROM admins")

# insert new admin with your hash
c.execute(
    "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
    ("admin", "scrypt:32768:8:1$5kcVmqHX4i2WeAEn$af61991150474c3065a9e4e32f5396027981f389295f82ef790cbe1048d778b99fc47c8bd00835a79b62c1a7e2404a4dbd40ccb15ed436fce5720c6afb648be5")
)

conn.commit()
conn.close()

print("✅ Admin password updated successfully!")