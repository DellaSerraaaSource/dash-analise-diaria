# app.py — BLiP Unique Users (core, simples, resiliente)
from __future__ import annotations

import os
import re
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple
from urllib.parse import quote

import requests
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from zoneinfo import ZoneInfo

API_URL = "https://http.msging.net/commands"
ANALYTICS_TO = "postmaster@analytics.msging.net"
DEFAULT_TZ = "America/Sao_Paulo"

# ------------------------- UI: Config básica -------------------------

st.set_page_config(page_title="BLiP — Usuários Únicos (core)", layout="wide")
st.title("Usuários únicos por 1º contato — BLiP (core)")

with st.sidebar.expander("Credenciais", expanded=True):
    st.write("Cole sua chave (apenas nesta sessão):")
    api_key_raw = st.text_input("BLIP_API_KEY", type="password")
    def _sanitize(k: str | None) -> str | None:
        if not k: return None
        k = k.strip()
        if k.lower().startswith("key "):
            k = k[4:].strip()
        if (k.startswith('"') and k.endswith('"')) or (k.startswith("'") and k.endswith("'")):
            k = k[1:-1].strip()
        return k or None
    api_key = _sanitize(api_key_raw) or _sanitize(os.getenv("BLIP_API_KEY")) or _sanitize(os.getenv("API_KEY"))

st.sidebar.header("Parâmetros")
action = st.sidebar.text_input("Ação/Bloco (flow)", value="Início")

period_mode = st.sidebar.radio("Período", ["Últimos N dias", "Intervalo de datas"], horizontal=True)
if period_mode == "Últimos N dias":
    days = st.sidebar.slider("N dias", 1, 90, 30)
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
else:
    utc_today = datetime.now(timezone.utc).date()
    start_date = st.sidebar.date_input("Início (UTC)", utc_today - timedelta(days=30))
    end_date = st.sidebar.date_input("Fim (UTC)", utc_today)
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

tz_name = st.sidebar.text_input("Fuso horário (para hora/dia)", value=DEFAULT_TZ)
start_h, end_h = st.sidebar.select_slider("Horário comercial (início → fim)", options=list(range(24)), value=(9, 18))
take = st.sidebar.number_input("Take por página", 100, 1000, 500, 50)
max_events = st.sidebar.number_input("Máx. eventos", 1000, 50000, 10000, 1000)

run = st.sidebar.button("Buscar & Analisar", type="primary")

# ------------------------- Core: utilidades -------------------------

def to_iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def business_bucket(hour: int, start_h: int, end_h: int) -> str:
    try:
        h = int(hour)
    except Exception:
        return "Fora"
    if start_h <= end_h:
        return "Dentro" if (start_h <= h < end_h) else "Fora"
    return "Dentro" if (h >= start_h or h < end_h) else "Fora"

def safe_json(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, str):
        s = obj.strip()
        try: return json.loads(s)
        except Exception: pass
        try: return json.loads(s.replace("'", '"'))
        except Exception: return {}
    return {}

def extract_identity(contact_field: Any) -> str | None:
    d = safe_json(contact_field)
    for k in ("identity", "Identity"):
        if isinstance(d.get(k), str):
            return d[k]
    m = re.search(r"[\"']Identity[\"']\s*:\s*[\"']([^\"']+)[\"']", str(contact_field))
    return m.group(1) if m else None

def to_local(ts: pd.Timestamp, tz: ZoneInfo) -> pd.Timestamp:
    if pd.isna(ts): return ts
    if ts.tzinfo is None: ts = ts.tz_localize(timezone.utc)
    return ts.tz_convert(tz)

# ------------------------- Core: coleta (retry simples) -------------------------

def fetch_events(
    api_key: str,
    action: str,
    start_iso: str,
    end_iso: str,
    take: int = 500,
    max_events: int = 10000,
    max_retries: int = 5,
    base_sleep: float = 0.8,
) -> List[Dict[str, Any]]:
    enc_action = quote(action)
    collected: List[Dict[str, Any]] = []
    skip = 0
    attempt = 0

    while True:
        uri = f"/event-track/flow/{enc_action}?$take={take}&$skip={skip}&startDate={start_iso}&endDate={end_iso}"
        payload = {"id": f"get-events-{action}-{skip}", "to": ANALYTICS_TO, "method": "get", "uri": uri}
        headers = {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}

        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=45)
            if resp.status_code == 401:
                raise RuntimeError("401 Unauthorized: verifique a chave (sem 'Key '), bot correto e gere nova se necessário.")
            if resp.status_code in (429, 500, 502, 503, 504):
                # backoff simples e retry controlado
                if attempt < max_retries:
                    sleep_s = base_sleep * (2 ** attempt)
                    st.info(f"Instabilidade ({resp.status_code}). Tentando de novo em {sleep_s:.1f}s…")
                    time.sleep(sleep_s)
                    attempt += 1
                    continue
                else:
                    resp.raise_for_status()
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            # erro fatal ou estourou retries
            st.error(f"Erro ao buscar eventos (skip={skip}): {e}")
            break

        items = (data or {}).get("resource", {}).get("items", []) or []
        collected.extend(items)
        st.write(f"Coletados {len(items)} eventos (total: {len(collected)}) | skip={skip}")

        if not items or len(collected) >= max_events:
            break
        skip += take

    return collected

# ------------------------- Core: processamento -------------------------

def preprocess_and_unique(
    raw: List[Dict[str, Any]],
    tz_name: str,
    start_h: int,
    end_h: int,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.DataFrame(raw)
    if df.empty:
        return df, df

    tz = ZoneInfo(tz_name)
    # datas (UTC com fallback)
    df["datetime_utc"] = pd.to_datetime(df.get("storageDate"), errors="coerce", utc=True)
    if df["datetime_utc"].isna().all() and "eventDate" in df.columns:
        df["datetime_utc"] = pd.to_datetime(df.get("eventDate"), errors="coerce", utc=True)
    df = df.dropna(subset=["datetime_utc"]).copy()

    # local
    df["datetime_local"] = df["datetime_utc"].apply(lambda x: to_local(x, tz))
    df["hora"] = df["datetime_local"].dt.hour

    # identidade
    df["user_id"] = df.get("contact").apply(extract_identity) if "contact" in df.columns else None
    if df["user_id"].isna().all() and "from" in df.columns:
        df["user_id"] = df["from"]

    # bucket
    df["horario_comercial"] = df["hora"].apply(lambda h: business_bucket(h, start_h, end_h))

    # primeiro contato
    df_unicos = (
        df.sort_values("datetime_local")
          .dropna(subset=["user_id"])
          .drop_duplicates(subset=["user_id"], keep="first")
          .reset_index(drop=True)
    )
    return df, df_unicos

def summarize(df_unicos: pd.DataFrame) -> Dict[str, Any]:
    if df_unicos.empty:
        vazio = pd.DataFrame(columns=["Horário", "Usuários únicos", "Percentual (%)"])
        return {"total": 0, "resumo": vazio, "semana": pd.DataFrame(), "dia": pd.DataFrame(), "hora": pd.DataFrame()}

    total = len(df_unicos)

    # resumo
    ordem = ["Dentro", "Fora"]
    resumo = (
        df_unicos["horario_comercial"]
        .value_counts()
        .reindex(ordem, fill_value=0)
        .rename_axis("Horário")
        .reset_index(name="Usuários únicos")
    )
    resumo["Percentual (%)"] = (resumo["Usuários únicos"] / total * 100).round(2)

    # semana (ano ISO + semana ISO)
    iso = df_unicos["datetime_local"].dt.isocalendar()
    dfu = df_unicos.assign(iso_year=iso.year, iso_week=iso.week)

    semana = (
        dfu.groupby(["iso_year", "iso_week", "horario_comercial"], observed=False)
        .size().unstack(fill_value=0).sort_index()
    )
    semana.index = [f"{y}-W{int(w):02d}" for y, w in semana.index]

    # dia
    dias_ord = ["Segunda-feira","Terça-feira","Quarta-feira","Quinta-feira","Sexta-feira","Sábado","Domingo"]
    dias_map = {
        "Monday": "Segunda-feira","Tuesday": "Terça-feira","Wednesday": "Quarta-feira",
        "Thursday": "Quinta-feira","Friday": "Sexta-feira","Saturday": "Sábado","Sunday": "Domingo",
    }
    # garante coluna traduzida
    if "dia_semana" not in dfu.columns:
        dfu["dia_semana"] = dfu["datetime_local"].dt.day_name().map(dias_map)
    dfu["dia_semana"] = pd.Categorical(dfu["dia_semana"], categories=dias_ord, ordered=True)
    dia = dfu.groupby(["dia_semana", "horario_comercial"], observed=False).size().unstack(fill_value=0).reindex(dias_ord)

    # hora
    hora = dfu.groupby(["hora", "horario_comercial"], observed=False).size().unstack(fill_value=0).sort_index()

    return {"total": total, "resumo": resumo, "semana": semana, "dia": dia, "hora": hora}

# ------------------------- Execução -------------------------

if run:
    if not api_key:
        st.error("Cole sua **BLIP_API_KEY** em Credenciais e tente novamente.")
        st.stop()

    start_iso, end_iso = to_iso_z(start_dt), to_iso_z(end_dt)

    with st.status("Buscando eventos...", expanded=True):
        raw = fetch_events(api_key, action, start_iso, end_iso, take=take, max_events=max_events)
        st.write(f"Eventos coletados: **{len(raw)}**")

    df, df_unicos = preprocess_and_unique(raw, tz_name, start_h, end_h)
    metrics = summarize(df_unicos)

    # KPIs
    col1, col2, col3 = st.columns(3)
    total = metrics["total"]
    r = metrics["resumo"].set_index("Horário") if not metrics["resumo"].empty else pd.DataFrame(index=["Dentro","Fora"], data={"Usuários únicos":[0,0]})
    dentro = int(r.loc["Dentro", "Usuários únicos"]) if "Dentro" in r.index else 0
    fora = int(r.loc["Fora", "Usuários únicos"]) if "Fora" in r.index else 0
    col1.metric("Usuários únicos (1º contato)", total)
    col2.metric("Dentro do comercial", f"{dentro}", f"{(dentro/max(total,1))*100:.1f}%")
    col3.metric("Fora do comercial", f"{fora}", f"{(fora/max(total,1))*100:.1f}%")

    # Gráficos simples (matplotlib)
    st.subheader("Distribuição Dentro vs Fora")
    if total > 0:
        fig1, ax1 = plt.subplots()
        metrics["resumo"].set_index("Horário")["Usuários únicos"].plot.pie(autopct="%1.1f%%", startangle=90, ax=ax1)
        ax1.set_ylabel("")
        st.pyplot(fig1)
    else:
        st.info("Sem dados para o gráfico de pizza.")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Por semana (ISO)")
        fig2, ax2 = plt.subplots(figsize=(7,4))
        if not metrics["semana"].empty:
            metrics["semana"].plot(kind="bar", stacked=True, ax=ax2)
        ax2.set_ylabel("Usuários únicos"); ax2.set_xlabel("Semana")
        st.pyplot(fig2)
    with c2:
        st.subheader("Por dia da semana")
        fig3, ax3 = plt.subplots(figsize=(7,4))
        if not metrics["dia"].empty:
            metrics["dia"].plot(kind="bar", stacked=True, ax=ax3)
        ax3.set_ylabel("Usuários únicos"); ax3.set_xlabel("Dia")
        st.pyplot(fig3)

    st.subheader("Por hora do dia")
    fig4, ax4 = plt.subplots(figsize=(10,4))
    if not metrics["hora"].empty:
        metrics["hora"].plot(kind="bar", stacked=True, ax=ax4)
    ax4.set_ylabel("Usuários únicos"); ax4.set_xlabel("Hora")
    st.pyplot(fig4)

    # Dados e export mínimo
    with st.expander("Eventos (amostra)"):
        st.dataframe(df.head(5000))
        st.download_button("Baixar CSV (eventos)", df.to_csv(index=False).encode("utf-8"), "eventos.csv", "text/csv")
    with st.expander("Primeiro contato por usuário"):
        st.dataframe(df_unicos)
        st.download_button("Baixar CSV (usuários únicos)", df_unicos.to_csv(index=False).encode("utf-8"), "usuarios_unicos.csv", "text/csv")
else:
    st.info("Ajuste os parâmetros, cole a chave e clique em **Buscar & Analisar**.")

