import streamlit as st
import asyncio
from telethon import TelegramClient
from datetime import datetime, timezone, timedelta
import os
import time
import json 

# --- AYARLAR ---
API_ID = 32583113
API_HASH = 'f03a12cf975db6385bcc12dda7ef878d'
SESSION_NAME = 'speed_news_session'
JSON_FILE = 'kanal_listesi.json'

# --- ZAMAN DİLİMİ AYARI (UTC+2) ---
# Eğer Türkiye saati (UTC+3) isterseniz parantez içini (hours=3) yapın.
MY_TZ = timezone(timedelta(hours=2))

# --- SAYFA YAPISI ---
st.set_page_config(page_title="🚨 Telegram Haber Analizi", page_icon="📥", layout="wide")

# --- YARDIMCI FONKSİYONLAR ---
def load_channels_from_file():
    """Dosya varsa oku, yoksa varsayılanları döndür."""
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    
    default_str = "@buzzbilgiler,@TURKINFORMmedya,@turkiyedenhaberler24,@asayisberkemaltr,@conflict_tr,@haberstudio,@OrduGazete,@muhafizhaber,@ww3media,@agentokato,@rootwebofficial,@haberlerp,@BreakingNewsTurkiye,@Sansursuzmedya18,@solcugazete,@bpthaber,@trthaberdijital,@habermha,@gundemedairhs,@SansursuzHaberResmi,@buzznews_tr,@darkwebhabertg"
    return [c.strip() for c in default_str.split(',') if c.strip()]

# --- SESSION STATE ---
if 'news_data' not in st.session_state:
    st.session_state.news_data = []
if 'data_fetched' not in st.session_state:
    st.session_state.data_fetched = False

# İlk açılışta dosyadan yükle
if 'prepared_channels' not in st.session_state:
    st.session_state.prepared_channels = load_channels_from_file()

if 'hunting_mode' not in st.session_state:
    st.session_state.hunting_mode = False
if 'last_check_time' not in st.session_state:
    # Başlangıç zamanını UTC+2 olarak ayarla
    st.session_state.last_check_time = datetime.now(MY_TZ)

st.title("📥 🚨 Telegram Haber Analizi")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Kanal Havuzu")
    
    # Text area değerini session state'den al
    current_list_str = ",".join(st.session_state.prepared_channels)
    
    raw_channels_input = st.text_area(
        "Kanal Listesi (Düzenleyin)", 
        value=current_list_str, 
        height=150
    )
    
    # --- GÜNCELLEME BUTONU ---
    if st.button("🔄 Listeyi Güncelle / Hazırla"):
        channel_list = [c.strip() for c in raw_channels_input.split(',') if c.strip()]
        channel_list = list(set(channel_list))
        channel_list.sort()
        
        # Hafızayı güncelle
        st.session_state.prepared_channels = channel_list
        
        # Checkbox'ları sıfırla/güncelle
        for ch in channel_list:
            if f"pre_{ch}" not in st.session_state:
                st.session_state[f"pre_{ch}"] = True
                
        st.success(f"Liste hafızaya alındı! ({len(channel_list)} kanal)")

    # --- İNDİRME BUTONU ---
    json_string = json.dumps(st.session_state.prepared_channels, indent=2)
    
    st.download_button(
        label="📥 JSON Dosyasını İndir",
        data=json_string,
        file_name="kanal_listesi.json",
        mime="application/json",
        help="Bu dosyayı indirip GitHub'a yüklerseniz, değişiklikleriniz kalıcı olur."
    )

    st.divider()

    # --- KANAL SEÇİMİ ---
    final_target_list = []
    if st.session_state.prepared_channels:
        st.subheader("2. Hedef Kanallar")
        
        def toggle_all():
            new_state = st.session_state.master_checkbox
            for ch in st.session_state.prepared_channels:
                st.session_state[f"pre_{ch}"] = new_state

        st.checkbox("✅ Hepsini Seç / Kaldır", value=True, key="master_checkbox", on_change=toggle_all)
        
        with st.container(border=True):
            for ch in st.session_state.prepared_channels:
                if f"pre_{ch}" not in st.session_state:
                    st.session_state[f"pre_{ch}"] = True
                    
                if st.checkbox(f"@{ch}", key=f"pre_{ch}"):
                    final_target_list.append(ch)
            st.caption(f"Aktif Hedef: {len(final_target_list)}")
    else:
        st.warning("Liste boş.")

    st.divider()
    
    # --- MOD SEÇİMİ ---
    st.header("3. Çalışma Modu")
    
    tab1, tab2 = st.tabs(["📂 Manuel", "🚨 CANLI AVCI"])
    
    with tab1:
        st.caption("Geçmiş tarama")
        # Varsayılan index=1 (Özel Tarih)
        time_mode = st.radio("Zaman:", ["Son 24 Saat", "Özel Tarih"], index=1)
        
        if time_mode == "Son 24 Saat":
            end_dt = datetime.now(MY_TZ)
            start_dt = end_dt - timedelta(hours=24)
        else:
            st.info("💡 Bitiş zamanı otomatik olarak 'ŞU AN' alınır.")
            col1, col2 = st.columns(2)
            
            # Varsayılan değerler UTC+2'ye göre şu an
            now_in_tz = datetime.now(MY_TZ)
            
            with col1:
                d1 = st.date_input("📅 Başlangıç Tarihi", value=now_in_tz)
            with col2:
                # Saat varsayılan olarak 00:00 gelir
                t1 = st.time_input("⏰ Başlangıç Saati", value=datetime.min.time()) 
            
            # Başlangıç: Seçilen Gün + Seçilen Saat + UTC+2 Bilgisi
            try:
                start_dt = datetime.combine(d1, t1).replace(tzinfo=MY_TZ)
            except:
                start_dt = datetime.combine(d1, t1).astimezone(MY_TZ)
                
            # Bitiş: Şu an (UTC+2)
            end_dt = datetime.now(MY_TZ)

        msg_limit = st.slider("Limit (Kanal Başına)", 2, 200, 40)
        fetch_btn = st.button("🚀 Verileri Çek", type="primary", disabled=(len(final_target_list) == 0))

    with tab2:
        st.caption("Otomatik izleme")
        c_start, c_stop = st.columns(2)
        if c_start.button("▶️ BAŞLAT", type="primary"):
            st.session_state.hunting_mode = True
            st.session_state.last_check_time = datetime.now(MY_TZ)
            st.rerun()
        if c_stop.button("⏹️ DURDUR"):
            st.session_state.hunting_mode = False
            st.rerun()

# --- ASYNC FONKSİYONLAR ---
async def fetch_news_logic(channels, start, end, limit):
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    raw_data = []
    
    try:
        await client.start()
        show_progress = not st.session_state.hunting_mode
        if show_progress:
            status = st.empty()
            progress = st.progress(0)
        
        total = len(channels)
        
        for i, channel in enumerate(channels):
            if show_progress: status.text(f"📡 {channel} taranıyor...")
            album_map = {} 
            
            try:
                entity = await client.get_entity(channel)
                real_username = entity.username
                
                async for msg in client.iter_messages(entity, limit=limit):
                    # Tarih karşılaştırması (Python timezone aware olduğu için otomatik çevirir)
                    if msg.date < start: break
                    if msg.date > end: continue
                    
                    text_content = ""
                    if msg.text: text_content = msg.text
                    elif msg.message: text_content = msg.message
                    elif hasattr(msg, 'raw_text') and msg.raw_text: text_content = msg.raw_text
                    if text_content is None: text_content = ""

                    thumb_data = None
                    media_type = "text"
                    if msg.photo or msg.video:
                        thumb_data = await msg.download_media(file=bytes, thumb=True)
                        media_type = "video" if msg.video else "image"

                    current_item = {
                        'kanal': real_username,
                        'tarih': msg.date, # Bu tarih orijinal (Genelde UTC gelir)
                        'text': text_content,
                        'thumb': thumb_data,
                        'media_type': media_type,
                        'link': f"https://t.me/{real_username}/{msg.id}",
                        'grouped_id': msg.grouped_id
                    }

                    if msg.grouped_id:
                        if msg.grouped_id in album_map:
                            existing_item = album_map[msg.grouped_id]
                            if (not existing_item['text']) and text_content:
                                existing_item['text'] = text_content
                            continue
                        else:
                            raw_data.append(current_item)
                            album_map[msg.grouped_id] = current_item
                    else:
                        if text_content or thumb_data:
                            raw_data.append(current_item)
                        
            except Exception as e:
                print(f"Hata ({channel}): {e}")
                
            if show_progress: progress.progress((i + 1) / total)
            
        if show_progress:
            status.empty()
            progress.empty()

    except Exception as e:
        if show_progress: st.error(f"Bağlantı Hatası: {e}")
    finally:
        if client.is_connected():
            await client.disconnect()
            
    return raw_data

def run_fetch(channels, start, end, limit):
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(fetch_news_logic(channels, start, end, limit))

# --- ANA AKIŞ ---
if st.session_state.hunting_mode:
    st.info("🟢 CANLI HABER AVCISI AKTİF - İzleniyor...")
    # Şu anki zaman UTC+2
    now_current = datetime.now(MY_TZ)
    
    new_items = run_fetch(final_target_list, st.session_state.last_check_time, now_current, limit=5)
    
    if new_items:
        new_items.sort(key=lambda x: x['tarih'])
        count = 0
        for item in new_items:
            exists = any(x['link'] == item['link'] for x in st.session_state.news_data)
            if not exists:
                st.session_state.news_data.insert(0, item)
                count += 1
        
        if count > 0:
            st.toast(f"🚨 {count} YENİ HABER!", icon="🔥")
    
    st.session_state.last_check_time = now_current
    st.session_state.data_fetched = True
    time.sleep(15)
    st.rerun()

elif fetch_btn:
    st.session_state.news_data = []
    st.session_state.data_fetched = False
    
    with st.spinner('Haberler Alınıyor...'):
        items = run_fetch(final_target_list, start_dt, end_dt, msg_limit)
        
        if items:
            unique = []
            seen = set()
            items.sort(key=lambda x: x['tarih'], reverse=True)
            for item in items:
                txt = item['text'] if item['text'] else ""
                content_hash = txt.strip()
                if len(content_hash) > 20 and content_hash in seen: continue
                if len(content_hash) > 20: seen.add(content_hash)
                unique.append(item)
            
            st.session_state.news_data = unique
            st.session_state.data_fetched = True
            st.success(f"{len(unique)} haber bulundu.")
        else:
            st.warning("Haber bulunamadı.")

# --- SONUÇLAR ---
if st.session_state.news_data:
    st.divider()
    if not st.session_state.hunting_mode:
        st.subheader("🔎 Sonuç Filtresi")
        result_channels = sorted(list(set([item['kanal'] for item in st.session_state.news_data])))
        cols = st.columns(4)
        selected_view_channels = []
        for i, ch in enumerate(result_channels):
            with cols[i % 4]:
                if st.checkbox(f"@{ch}", value=True, key=f"post_{ch}"):
                    selected_view_channels.append(ch)
        display_list = [n for n in st.session_state.news_data if n['kanal'] in selected_view_channels]
    else:
        st.subheader("🔥 Canlı Akış")
        display_list = st.session_state.news_data

    for item in display_list:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4]) 
            with c1:
                if item['thumb']:
                    st.image(item['thumb'], use_container_width=True)
                    if item['media_type'] == 'video': st.caption("🎥 Video")
                else:
                    st.caption("📷 Yok")
            with c2:
                # EKRANA BASARKEN UTC+2'ye ZORLA
                local_time = item['tarih'].astimezone(MY_TZ).strftime('%H:%M:%S')
                date_str = item['tarih'].astimezone(MY_TZ).strftime('%d.%m.%Y')
                
                if st.session_state.hunting_mode:
                    st.markdown(f"### ⏰ {local_time}")
                    st.caption(f"{date_str} | @{item['kanal']}")
                else:
                    st.caption(f"📅 {date_str} {local_time} | 📢 @{item['kanal']}")
                
                if item['text'] and len(item['text'].strip()) > 0:
                    st.markdown(item['text'])
                else:
                    st.info("*(Açıklama yok)*")
                st.link_button("🔗 Git", item['link'])
elif not st.session_state.data_fetched and not st.session_state.hunting_mode:
    st.info("👈 Manuel veya Canlı modu başlatın.")
