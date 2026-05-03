import time, logging, io, os
import pandas as pd
import numpy as np
import streamlit as st
from screener import run_screener, format_for_display
from config import DEFAULTS, SCORING_WEIGHTS, SCORE_HIGH, SCORE_MEDIUM

logging.basicConfig(level=logging.WARNING)
st.set_page_config(page_title="S&P 500 Screener", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

st.markdown("""<style>
.main-header{font-size:2rem;font-weight:700;background:linear-gradient(90deg,#1a73e8,#0d47a1);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.sub-header{color:#666;font-size:0.9rem;margin-bottom:1.5rem;}
.disclaimer{background:#fff3cd;border:1px solid #ffc107;border-radius:6px;padding:0.75rem;font-size:0.78rem;color:#856404;margin-top:1.5rem;}
</style>""", unsafe_allow_html=True)

if "results_df" not in st.session_state: st.session_state.results_df = pd.DataFrame()
if "last_run" not in st.session_state: st.session_state.last_run = None
if "run_count" not in st.session_state: st.session_state.run_count = 0

with st.sidebar:
    st.markdown("## Controles del Screener")
    profile = st.selectbox("Perfil de Riesgo", ["Conservador","Equilibrado","Agresivo"], index=1)
    profile_map = {"Conservador":"Conservative","Equilibrado":"Balanced","Agresivo":"Aggressive"}
    profile_en = profile_map[profile]
    refresh_min = st.slider("Auto-refresco (minutos)", 1, 60, DEFAULTS["refresh_minutes"])
    auto_refresh = st.checkbox("Activar auto-refresco", value=False)
    st.divider()
    st.markdown("### Filtros Principales")
    pe_max = st.slider("P/E maximo", 5.0, 60.0, float(DEFAULTS["pe_max"]), step=0.5)
    vol_spike = st.slider("Volumen minimo (x media)", 1.0, 5.0, float(DEFAULTS["volume_spike_min"]), step=0.1)
    rsi_min = st.slider("RSI minimo (14)", 30.0, 80.0, float(DEFAULTS["rsi_min"]), step=1.0)
    st.divider()
    st.markdown("### Filtros Avanzados")
    rev_growth = st.slider("Crecimiento ingresos min %", 0.0, 50.0, float(DEFAULTS["rev_growth_min"]), step=1.0)
    earn_growth = st.slider("Crecimiento beneficios min %", 0.0, 50.0, float(DEFAULTS["earn_growth_min"]), step=1.0)
    de_max = st.slider("Deuda/Capital maximo", 0.0, 5.0, float(DEFAULTS["de_ratio_max"]), step=0.1)
    roe_min = st.slider("ROE minimo %", 0.0, 40.0, float(DEFAULTS["roe_min"]), step=1.0)
    fcf_pos = st.checkbox("Flujo de caja libre positivo", value=True)
    above_50d = st.checkbox("Precio sobre MM 50 dias", value=True)
    above_200d = st.checkbox("Precio sobre MM 200 dias", value=True)
    rs_spy = st.checkbox("Mejor que SPY en 3 meses", value=True)
    st.divider()
    top_n = st.slider("Mostrar top N resultados", 5, 100, DEFAULTS["top_n"])

filters = {"pe_max":pe_max,"volume_spike_min":vol_spike,"rsi_min":rsi_min,"rev_growth_min":rev_growth,"earn_growth_min":earn_growth,"de_ratio_max":de_max,"roe_min":roe_min,"fcf_positive":fcf_pos,"above_50d_ma":above_50d,"above_200d_ma":above_200d,"rs_vs_spy":rs_spy,"top_n":top_n}

st.markdown("<div class=\"main-header\">S&P 500 Screener de Acciones</div>", unsafe_allow_html=True)
st.markdown("<div class=\"sub-header\">Perfil equilibrado · Scoring hibrido · Valorizacion + Crecimiento + Momentum + Flujo</div>", unsafe_allow_html=True)

col1, col2, col3, _ = st.columns([2,2,2,4])
with col1: run_button = st.button("Ejecutar Screener", type="primary", use_container_width=True)
with col2: clear_button = st.button("Limpiar Cache", use_container_width=True)
with col3:
    if not st.session_state.results_df.empty:
        st.download_button("Exportar CSV", st.session_state.results_df.to_csv(index=True).encode("utf-8"), file_name="screener.csv", mime="text/csv", use_container_width=True)

if clear_button:
    cache_dir = os.path.join(os.path.dirname(__file__), "cache")
    removed = 0
    if os.path.exists(cache_dir):
        for f in os.listdir(cache_dir):
            if f.endswith(".pkl"): os.remove(os.path.join(cache_dir, f)); removed += 1
    st.success(f"Eliminados {removed} archivos de cache.")
    time.sleep(1); st.rerun()

def execute_screening():
    bar = st.progress(0, text="Iniciando...")
    status = st.empty()
    def _cb(pct, msg): bar.progress(min(pct,100), text=msg); status.caption(f"{msg}")
    try:
        df_raw = run_screener(filters=filters, profile=profile_en, progress_callback=_cb)
        df_display = format_for_display(df_raw).head(top_n) if not df_raw.empty else pd.DataFrame()
        st.session_state.results_df = df_display
        st.session_state.last_run = time.time()
        st.session_state.run_count += 1
        bar.empty(); status.empty()
        return df_display
    except Exception as e:
        bar.empty(); status.error(f"Error: {e}")
        return pd.DataFrame()

if run_button:
    execute_screening(); st.rerun()

if auto_refresh and st.session_state.last_run:
    remaining = refresh_min*60 - (time.time()-st.session_state.last_run)
    if remaining <= 0: execute_screening(); st.rerun()
    else: st.caption(f"Proximo refresco en {int(remaining//60)}m {int(remaining%60)}s")

df = st.session_state.results_df
if st.session_state.last_run:
    ts = time.strftime("%H:%M:%S", time.localtime(st.session_state.last_run))
    st.caption(f"Ultimo analisis: {ts} · Ejecucion #{st.session_state.run_count} · {len(df)} acciones")

if df.empty:
    if st.session_state.run_count == 0:
        st.info("Configura los filtros y pulsa Ejecutar Screener para comenzar.")
    else:
        st.warning("Ninguna accion paso los filtros. Prueba a relajar alguno.")
else:
    st.divider()
    m1,m2,m3,m4,m5 = st.columns(5)
    top_row = df.iloc[0] if len(df) > 0 else None
    with m1: st.metric("Acciones filtradas", len(df))
    with m2: st.metric("Senal alta (>=70)", int((df["Score"]>=SCORE_HIGH).sum()))
    with m3: st.metric("Score medio", f"{df['Score'].mean():.1f}")
    with m4:
        if top_row is not None: st.metric("Mejor accion", top_row["Ticker"])
    with m5:
        if top_row is not None: st.metric("Mejor score", f"{top_row['Score']:.1f}")

    tab1, tab2 = st.tabs(["Tabla Ranking", "Desglose Scores"])
    with tab1:
        st.markdown("#### Acciones mejor clasificadas")
        def _hl(row):
            s = row.get("Score",0)
            if pd.isna(s): return [""]*len(row)
            if s>=SCORE_HIGH: return ["background-color:#d4edda"]*len(row)
            if s>=SCORE_MEDIUM: return ["background-color:#fff3cd"]*len(row)
            return [""]*len(row)
        st.dataframe(df.style.apply(_hl,axis=1).format(na_rep="--"), use_container_width=True, height=600)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w: df.to_excel(w, index=True, sheet_name="Resultados")
        st.download_button("Exportar Excel", buf.getvalue(), file_name="screener.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with tab2:
        if "Val Score" in df.columns:
            st.markdown("#### Desglose por pilar (0-100)")
            score_cols = [c for c in ["Ticker","Company","Score","Val Score","Growth Score","Mom Score","Flow Score"] if c in df.columns]
            def _sc(val):
                try:
                    v=float(val)
                    if v>=SCORE_HIGH: return "color:#155724;font-weight:bold"
                    if v>=SCORE_MEDIUM: return "color:#856404"
                    return "color:#721c24"
                except: return ""
            st.dataframe(df[score_cols].style.applymap(_sc,subset=["Score","Val Score","Growth Score","Mom Score","Flow Score"]).format(na_rep="--"), use_container_width=True, height=500)
            w = SCORING_WEIGHTS.get(profile_en, SCORING_WEIGHTS["Balanced"])
            st.markdown(f"Pesos activos ({profile}): Valorizacion {w['valuation']*100:.0f}% · Crecimiento {w['growth']*100:.0f}% · Momentum {w['momentum']*100:.0f}% · Flujo {w['flow']*100:.0f}%")

st.markdown("""<div class="disclaimer">Aviso legal: Solo para investigacion e informacion. No constituye asesoramiento financiero. Datos de Yahoo Finance pueden estar retrasados. Consulta siempre a un asesor cualificado.</div>""", unsafe_allow_html=True)
