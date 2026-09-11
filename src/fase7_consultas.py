"""
Fase 7 - Reporte agregado respondido unicamente con consultas SQL sobre la
base de datos (db.py), sin mirar logs sueltos. Criterio de aprobacion de la
fase: poder responder costo total, costo por SKU, tasa de reintento, y cual
escena tiene peor tasa de aprobacion.
"""
from db import conectar


def main():
    con = conectar()
    cur = con.cursor()

    print("=== Costo total ===")
    cur.execute("SELECT ROUND(SUM(costo_usd), 4) FROM generaciones")
    print(f"${cur.fetchone()[0]}\n")

    print("=== Costo por SKU ===")
    cur.execute("""
        SELECT sku, ROUND(SUM(costo_usd), 4) as costo
        FROM generaciones GROUP BY sku ORDER BY sku
    """)
    for sku, costo in cur.fetchall():
        print(f"  {sku}: ${costo}")

    print("\n=== Tasa de reintento (Pista B) ===")
    cur.execute("""
        SELECT COUNT(DISTINCT sku || '-' || escena_id)
        FROM generaciones WHERE modelo_ia = 'nano_banana'
    """)
    combinaciones = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(DISTINCT sku || '-' || escena_id)
        FROM generaciones WHERE modelo_ia = 'nano_banana' AND intento > 1
    """)
    combinaciones_con_reintento = cur.fetchone()[0]
    tasa = (combinaciones_con_reintento / combinaciones * 100) if combinaciones else 0
    print(f"  {combinaciones_con_reintento} de {combinaciones} combinaciones sku+escena "
          f"necesitaron reintento ({tasa:.1f}%)")

    print("\n=== Escena con peor tasa de aprobacion (en el primer intento) ===")
    cur.execute("""
        SELECT escena_id,
               COUNT(*) as total_primeros_intentos,
               SUM(CASE WHEN score_qa >= 80 THEN 1 ELSE 0 END) as aprobados
        FROM generaciones
        WHERE modelo_ia = 'nano_banana' AND intento = 1
        GROUP BY escena_id
        ORDER BY (CAST(aprobados AS FLOAT) / total_primeros_intentos) ASC
    """)
    for escena_id, total, aprobados in cur.fetchall():
        tasa_aprob = aprobados / total * 100 if total else 0
        print(f"  escena {escena_id}: {aprobados}/{total} aprobados en 1er intento ({tasa_aprob:.0f}%)")

    con.close()


if __name__ == "__main__":
    main()
