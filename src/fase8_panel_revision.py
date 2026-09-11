"""
Fase 8 - Panel de revision (Streamlit).
Muestra los trabajos listos para revision, con costo y score visibles por
item (cada formato de Pista A y cada escena/intento de Pista B), y permite
aprobar/rechazar/reintentar - cada accion usa una transicion con
compare-and-swap (nunca un UPDATE incondicional), asi que dos pestanas
actuando sobre el mismo trabajo a la vez nunca lo dejan en un estado
inconsistente.

Correr con: streamlit run src/fase8_panel_revision.py
(el binding a localhost lo fuerza .streamlit/config.toml, no una bandera
que haya que recordar agregar en el comando)
"""
from pathlib import Path

import streamlit as st

import db
from seguridad import sanitizar

ROOT = Path(__file__).resolve().parent.parent

db.inicializar_db()

st.set_page_config(page_title="Gorrolandia - Panel de revision", layout="wide")
st.title("Panel de revision - Gorrolandia")

MENSAJES_APROBAR = {
    "estado_invalido": "El trabajo cambio mientras revisabas (otra pestana ya lo aprobo/rechazo, o volvio a "
                        "'pendiente'/'procesando') - refresca la pagina.",
    "escena_faltante": "Falta al menos una escena de Pista B por generar todavia - refresca la pagina en unos "
                        "minutos.",
    "qa_incompleto": "El trabajo cambio mientras revisabas (una escena quedo con QA pendiente o en error) - "
                      "refresca la pagina.",
    "artefacto_invalido": "Un archivo de este trabajo se perdio o se corrompio despues de la revision - no se "
                           "puede aprobar. Este trabajo requiere reparacion manual y se queda visible aqui hasta "
                           "que se resuelva.",
}

ESTADOS_VISIBLES = ["listo_para_revision", "aprobado", "rechazado", "error", "pendiente", "procesando"]
filtro_estado = st.sidebar.selectbox("Filtrar por estado", ESTADOS_VISIBLES)

trabajos = db.listar_trabajos(estado=filtro_estado)

if not trabajos:
    st.info(f"No hay trabajos en estado '{filtro_estado}'.")
    st.stop()

st.caption(f"{len(trabajos)} trabajo(s) en estado '{filtro_estado}'")

for trabajo in trabajos:
    # aislado por trabajo_id, no por sku - dos trabajos con el mismo sku
    # (reingesta de la misma gorra) no se mezclan entre si.
    generaciones = db.generaciones_de_trabajo(trabajo["id"])
    costo_total = sum(g["costo_usd"] or 0 for g in generaciones)

    with st.container(border=True):
        col_info, col_acciones = st.columns([4, 1])
        with col_info:
            st.subheader(f"{trabajo['sku']}  ·  {trabajo['drive_file_name']}")
            st.caption(
                f"Estado: **{trabajo['estado']}**  ·  Costo total: **${costo_total:.2f}**  ·  "
                f"Creado: {trabajo['creado_en']}"
            )
            if trabajo["error"]:
                st.error(f"Error: {sanitizar(trabajo['error'])}")

        with col_acciones:
            if trabajo["estado"] == "listo_para_revision":
                if st.button("Aprobar", key=f"aprobar_{trabajo['id']}", type="primary"):
                    resultado = db.aprobar_trabajo(trabajo["id"])
                    if resultado == "aprobado":
                        st.rerun()
                    else:
                        st.warning(MENSAJES_APROBAR.get(resultado, "No se pudo aprobar - refresca la pagina."))
                if st.button("Rechazar", key=f"rechazar_{trabajo['id']}"):
                    if db.rechazar_trabajo(trabajo["id"]):
                        st.rerun()
                    else:
                        st.warning("El trabajo cambio mientras revisabas - refresca la pagina.")
            elif trabajo["estado"] == "error":
                if st.button("Reintentar", key=f"reintentar_{trabajo['id']}"):
                    if db.reintentar_trabajo(trabajo["id"]):
                        st.rerun()
                    else:
                        st.warning("El trabajo cambio mientras revisabas - refresca la pagina.")

        if generaciones:
            st.markdown("**Items generados:**")
            cols = st.columns(4)
            for i, gen in enumerate(generaciones):
                with cols[i % 4]:
                    ruta = Path(gen["ruta_output"]) if gen["ruta_output"] else None
                    if ruta and ruta.exists():
                        st.image(str(ruta), width="stretch")
                    if gen["modelo_ia"] == "compositing_local":
                        etiqueta = f"Pista A ({gen['escena_id']})"
                    else:
                        etiqueta = f"Pista B / escena {gen['escena_id']} / intento {gen['intento']}"
                    st.caption(etiqueta)

                    if gen["modelo_ia"] != "compositing_local":
                        evaluacion = db.ultima_evaluacion_vigente(gen["id"])
                        if evaluacion is None:
                            st.caption(f"QA: sin evaluar todavia  ·  ${gen['costo_usd']:.2f}")
                        elif evaluacion["qa_error"]:
                            st.caption(f"⚠️ QA fallo: {sanitizar(evaluacion['detalle'])}  ·  ${gen['costo_usd']:.2f}")
                        else:
                            aprobado_txt = "✅ aprobado" if evaluacion["aprobado"] else "❌ no aprobado"
                            st.caption(f"score: {evaluacion['score']}  ·  {aprobado_txt}  ·  ${gen['costo_usd']:.2f}")
                            if evaluacion["detalle"]:
                                st.caption(f"⚠️ {sanitizar(evaluacion['detalle'])}")
                    else:
                        st.caption(f"${gen['costo_usd']:.2f}")
        else:
            st.caption("Sin generaciones registradas todavia.")
