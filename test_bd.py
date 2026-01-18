#!/usr/bin/env python3
"""Test BD tables"""
from CONFIG.db import get_connection

try:
    conn = get_connection()
    cursor = conn.cursor()
    
    # Verificar tablas
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('imagenes_avisos', 'archivos_csv_avisos')")
    tables = cursor.fetchall()
    
    if len(tables) == 2:
        print("✅ Tablas encontradas:")
        for t in tables:
            print(f"  - {t[0]}")
    else:
        print(f"⚠️  Solo {len(tables)}/2 tablas encontradas")
        for t in tables:
            print(f"  - {t[0]}")
    
    cursor.close()
    conn.close()
    print("\n✅ BD conectada correctamente")
    
except Exception as e:
    print(f"❌ Error: {e}")
