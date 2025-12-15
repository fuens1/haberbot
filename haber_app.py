import streamlit as st
import asyncio
from telethon import TelegramClient
from datetime import datetime, timezone, timedelta
import os
import time

# --- AYARLAR ---
API_ID = 32583113
API_HASH = 'f03a12cf975db6385bcc12dda7ef878d'
SESSION_NAME = 'speed_news_session' 

# --- SAYFA YAPISI ---
st.set_page_config(page_title="🚨 Telegram Haber Analizi", page_icon="🚨", layout="wide")

# --- SESSION STATE ---
if 'news_data' not in st.session_state:
    st.session_state.news_data = []
if 'data_fetched' not in st.session_state:
    st.session_state.data_fetched = False
if 'prepared_channels' not in st.session_state:
    st.session_state.prepared_channels = []
# Canlı Mod için State'ler
if 'hunting_mode' not in st.session_state:
    st.session_state.hunting_mode = False
if 'last_check_time' not in st.session_state:
    st.session_state.last_check_time = datetime.now(timezone.utc)

st.title("🚨 Telegram Haber Analizi")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Kanal Havuzu")
    default_channels = "@buzzbilgiler,@TURKINFORMmedya,@turkiyedenhaberler24,@asayisberkemaltr,@conflict_tr,@haberstudio,@OrduGazete,@muhafizhaber,@ww3media,@agentokato,@rootwebofficial,@haberlerp,@BreakingNewsTurkiye,@Sansursuzmedya18,@solcugazete,@bpthaber,@trthaberdijital,@habermha,@gundemedairhs,@SansursuzHaberResmi,@buzznews_tr,@darkwebhabertg"
    raw_channels_input = st.text_area("Kanal Listesi", default_channels, height=100)
    
    if st.button("📋 Listeyi Hazırla"):
        channel_list = [c.strip() for c in raw_channels_input.split(',') if c.strip()]
        channel_list = list(set(channel_list))
        channel_list.sort()
        st.session_state.prepared_channels = channel_list
        
        for ch in channel_list:
            if f"pre_{ch}" not in st.session_state:
                st.session_state[f"pre_{ch}"] = True
        st.success(f"{len(channel_list)} kanal hazırlandı!")

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
                if st.checkbox(f"@{ch}", value=True, key=f"pre_{ch}"):
                    final_target_list.append(ch)
            st.caption(f"Aktif Hedef: {len(final_target_list)}")
    else:
        st.warning("Önce 'Listeyi Hazırla' butonuna basınız.")

    st.divider()
    
    # --- MOD SEÇİMİ (MANUEL / CANLI) ---
    st.header("3. Çalışma Modu")
    
    tab1, tab2 = st.tabs(["📂 Manuel Arşiv", "🚨 CANLI AVCI"])
    
    with tab1:
        st.caption("Geçmişe dönük tarama yapar.")
        time_mode = st.radio("Zaman:", ["Son 24 Saat", "Özel Tarih"], index=0)
        
        if time_mode == "Son 24 Saat":
            end_dt = datetime.now(timezone.utc)
            start_dt = end_dt - timedelta(hours=24)
        else:
            col1, col2 = st.columns(2)
            d1 = col1.date_input("Başlangıç", value=datetime.now())
            d2 = col2.date_input("Bitiş", value=datetime.now())
            start_dt = datetime.combine(d1, datetime.min.time()).replace(tzinfo=timezone.utc)
            end_dt = datetime.combine(d2, datetime.max.time()).replace(tzinfo=timezone.utc)

        msg_limit = st.slider("Limit", 2, 200, 40)
        fetch_btn = st.button("🚀 Verileri Çek (Manuel)", type="primary", disabled=(len(final_target_list) == 0))

    with tab2:
        st.caption("Sürekli izleme yapar ve yeni haber düşünce ekrana aktarır.")
        
        c_start, c_stop = st.columns(2)
        if c_start.button("▶️ AVCISI BAŞLAT", type="primary"):
            st.session_state.hunting_mode = True
            # Başlangıç zamanını şu an yapıyoruz ki eskileri getirmesin
            st.session_state.last_check_time = datetime.now(timezone.utc)
            st.rerun()
            
        if c_stop.button("⏹️ DURDUR"):
            st.session_state.hunting_mode = False
            st.rerun()

# --- ORTAK ASYNC FONKSİYON (Albüm Fix Dahil) ---
async def fetch_news_logic(channels, start, end, limit):
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    raw_data = []
    
    try:
        await client.start()
        # Progress bar sadece manuel modda gösterilsin, canlı modda kafa karıştırmasın
        show_progress = not st.session_state.hunting_mode
        
        if show_progress:
            status = st.empty()
            progress = st.progress(0)
        
        total = len(channels)
        
        for i, channel in enumerate(channels):
            if show_progress: status.text(f"📡 {channel} taranıyor...")
            
            # ALBÜM TAKİP SÖZLÜĞÜ
            album_map = {} 
            
            try:
                entity = await client.get_entity(channel)
                real_username = entity.username
                
                async for msg in client.iter_messages(entity, limit=limit):
                    if msg.date < start: break
                    if msg.date > end: continue
                    
                    # 1. Metin Çıkarma
                    text_content = ""
                    if msg.text: text_content = msg.text
                    elif msg.message: text_content = msg.message
                    elif hasattr(msg, 'raw_text') and msg.raw_text: text_content = msg.raw_text
                    if text_content is None: text_content = ""

                    # 2. Medya
                    thumb_data = None
                    media_type = "text"
                    if msg.photo or msg.video:
                        thumb_data = await msg.download_media(file=bytes, thumb=True)
                        media_type = "video" if msg.video else "image"

                    # 3. Öğe Oluşturma
                    current_item = {
                        'kanal': real_username,
                        'tarih': msg.date,
                        'text': text_content,
                        'thumb': thumb_data,
                        'media_type': media_type,
                        'link': f"https://t.me/{real_username}/{msg.id}",
                        'grouped_id': msg.grouped_id
                    }

                    # --- ALBÜM BİRLEŞTİRME ---
                    if msg.grouped_id:
                        if msg.grouped_id in album_map:
                            existing_item = album_map[msg.grouped_id]
                            # Metin varsa güncelle
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

# --- ANA İŞLEM AKIŞI ---

# A) CANLI AVCI MODU AKTİFSE
if st.session_state.hunting_mode:
    st.info("🟢 CANLI HABER AVCISI AKTİF - Yeni haber bekleniyor (Her 15sn güncellenir)...")
    
    # Şu anki zaman
    now_utc = datetime.now(timezone.utc)
    
    # Son kontrolden (last_check_time) şu ana kadar olanları çek
    # Limit 5 yeterli çünkü son 15 saniyede 5'ten fazla haber düşmez
    new_items = run_fetch(final_target_list, st.session_state.last_check_time, now_utc, limit=5)
    
    if new_items:
        # Yeni haberleri sırala (Eskiden yeniye)
        new_items.sort(key=lambda x: x['tarih'])
        
        count = 0
        for item in new_items:
            # Tekilleştirme (Basit ID kontrolü, zaten listede var mı?)
            exists = any(x['link'] == item['link'] for x in st.session_state.news_data)
            if not exists:
                # EN BAŞA EKLE (Insert 0)
                st.session_state.news_data.insert(0, item)
                count += 1
        
        if count > 0:
            st.toast(f"🚨 {count} YENİ HABER YAKALANDI!", icon="🔥")
    
    # Zamanı güncelle
    st.session_state.last_check_time = now_utc
    st.session_state.data_fetched = True
    
    # Otomatik Yenileme
    time.sleep(15)
    st.rerun()

# B) MANUEL ÇEKİM BUTONU
elif fetch_btn:
    st.session_state.news_data = []
    st.session_state.data_fetched = False
    
    with st.spinner('Arşiv taranıyor...'):
        items = run_fetch(final_target_list, start_dt, end_dt, msg_limit)
        
        if items:
            # Tekilleştirme
            unique = []
            seen = set()
            items.sort(key=lambda x: x['tarih'], reverse=True)
            
            for item in items:
                txt = item['text'] if item['text'] else ""
                content_hash = txt.strip()
                if len(content_hash) > 20 and content_hash in seen:
                    continue
                if len(content_hash) > 20: seen.add(content_hash)
                unique.append(item)
            
            st.session_state.news_data = unique
            st.session_state.data_fetched = True
            st.success(f"{len(unique)} haber bulundu.")
        else:
            st.warning("Haber bulunamadı.")

# --- SONUÇ GÖSTERİMİ (ORTAK) ---
if st.session_state.news_data:
    st.divider()
    
    # Canlı modda filtreyi göstermeyelim, direkt aksiyon olsun
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
        # Canlı modda hepsi görünsün
        st.subheader("🔥 Canlı Akış")
        display_list = st.session_state.news_data

    # Ekrana Bas
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
                local_time = item['tarih'].astimezone().strftime('%H:%M:%S')
                date_str = item['tarih'].astimezone().strftime('%d.%m.%Y')
                
                # Canlı modda saati vurgula
                if st.session_state.hunting_mode:
                    st.markdown(f"### ⏰ {local_time}")
                    st.caption(f"{date_str} | @{item['kanal']}")
                else:
                    st.caption(f"📅 {date_str} {local_time} | 📢 @{item['kanal']}")
                
                if item['text'] and len(item['text'].strip()) > 0:
                    st.markdown(item['text'])
                else:
                    st.info("*(Açıklama yok)*")
                
                st.link_button("🔗 Kaynağa Git", item['link'])

elif not st.session_state.data_fetched and not st.session_state.hunting_mode:
    if len(st.session_state.prepared_channels) > 0:
        st.info("👈 Manuel çekim veya Canlı Avcı modunu başlatabilirsiniz.")
    else:
        st.info("👈 Önce kanal listesini girip 'Listeyi Hazırla' butonuna basın.")