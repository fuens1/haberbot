import streamlit as st
import asyncio
from telethon import TelegramClient
from datetime import datetime, timezone, timedelta
import os
import time
import json
import hashlib  # Resim karşılaştırması için eklendi

# --- AYARLAR ---
API_ID = 32583113
API_HASH = 'f03a12cf975db6385bcc12dda7ef878d'
SESSION_NAME = 'speed_news_session'
JSON_FILE = 'kanal_listesi.json'

# --- GÜÇLENDİRİLMİŞ REKLAM FİLTRESİ ---
BLACKLIST_KEYWORDS = [
    # Bahis / Casino
    "bet", "casino", "slot", "bonus", "freespin", "gates of olympus", 
    "bonanza", "tıkla kazan", "giriş için", "deneme bonusu", "çevrimsiz",
    
    # Reklam / Tanıtım Genel
    "#reklam", " reklam", "(reklam)", "reklamveren", "sponsorlu", 
    "#işbirliği", "iş birliği", "tanıtım", "promo", "discount", "çekiliş",
    
    # Kripto / Finans Reklamları
    "%0 komisyon", "limit emri komisyonu", "referans kodu", "üyelik", 
    "yatırım tavsiyesi değildir", "ytd", "kazanç fırsatı", "avantajlı",
    "hoş geldin ödülü", "ayrıcalıklar", "şimdi seninle"
]

# --- ZAMAN DİLİMİ AYARI (UTC+2) ---
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

def get_image_hash(image_bytes):
    """Resim verisinden MD5 hash üretir (Resim karşılaştırması için)."""
    if image_bytes is None:
        return None
    return hashlib.md5(image_bytes).hexdigest()

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
    st.session_state.last_check_time = datetime.now(MY_TZ)

st.title("📥 🚨 Telegram Haber Analizi")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Kanal Havuzu")
    
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
        
        st.session_state.prepared_channels = channel_list
        
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
        time_mode = st.radio("Zaman:", ["Son 24 Saat", "Özel Tarih"], index=1)
        
        if time_mode == "Son 24 Saat":
            end_dt = datetime.now(MY_TZ)
            start_dt = end_dt - timedelta(hours=24)
        else:
            st.info("💡 Bitiş zamanı otomatik olarak 'ŞU AN' alınır.")
            col1, col2 = st.columns(2)
            
            now_in_tz = datetime.now(MY_TZ)
            
            with col1:
                d1 = st.date_input("📅 Başlangıç Tarihi", value=now_in_tz)
            with col2:
                t1 = st.time_input("⏰ Başlangıç Saati", value=datetime.min.time()) 
            
            try:
                start_dt = datetime.combine(d1, t1).replace(tzinfo=MY_TZ)
            except:
                start_dt = datetime.combine(d1, t1).astimezone(MY_TZ)
                
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
                    if msg.date < start: break
                    if msg.date > end: continue
                    
                    text_content = ""
                    if msg.text: text_content = msg.text
                    elif msg.message: text_content = msg.message
                    elif hasattr(msg, 'raw_text') and msg.raw_text: text_content = msg.raw_text
                    if text_content is None: text_content = ""

                    # --- GÜÇLENDİRİLMİŞ FİLTRE ---
                    text_lower = text_content.lower()
                    is_ad = False
                    for bad_word in BLACKLIST_KEYWORDS:
                        if bad_word in text_lower:
                            is_ad = True
                            break
                    
                    if is_ad:
                        continue 
                    # -----------------------------

                    thumb_data = None
                    media_type = "text"
                    if msg.photo or msg.video:
                        thumb_data = await msg.download_media(file=bytes, thumb=True)
                        media_type = "video" if msg.video else "image"

                    current_item = {
                        'kanal': real_username,
                        'tarih': msg.date,
                        'text': text_content,
                        'thumb': thumb_data,
                        'media_type': media_type,
                        'link': f"https://t.me/{real_username}/{msg.id}",
                        'grouped_id': msg.grouped_id,
                        # Resim Hash'i (Deduplication için)
                        'img_hash': get_image_hash(thumb_data)
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

# --- ANA AKIŞ: VERİ TOPLAMA ---
if st.session_state.hunting_mode:
    # Bilgilendirme mesajı en tepeye
    st.info("🟢 CANLI HABER AVCISI AKTİF - İzleniyor... (Her 15 saniyede bir güncellenir)")
    
    # 1. Veriyi çek
    now_current = datetime.now(MY_TZ)
    new_items = run_fetch(final_target_list, st.session_state.last_check_time, now_current, limit=5)
    
    # 2. Listeye ekle (Tekrarları önleyerek)
    if new_items:
        # Önce tarihe göre sırala
        new_items.sort(key=lambda x: x['tarih'])
        
        for item in new_items:
            # Kontrol: Link aynı mı VEYA Resim Hash'i aynı mı?
            exists = False
            for old_item in st.session_state.news_data:
                # Link kontrolü
                if old_item['link'] == item['link']:
                    exists = True
                    break
                # Resim kontrolü (Eğer resim varsa)
                if item['img_hash'] is not None and old_item['img_hash'] == item['img_hash']:
                    exists = True
                    break
            
            if not exists:
                st.session_state.news_data.insert(0, item)
    
    st.session_state.last_check_time = now_current
    st.session_state.data_fetched = True

elif fetch_btn:
    st.session_state.news_data = []
    st.session_state.data_fetched = False
    
    with st.spinner('Haberler Alınıyor...'):
        items = run_fetch(final_target_list, start_dt, end_dt, msg_limit)
        
        if items:
            # --- MANTIKSAL DEĞİŞİKLİK: İLK PAYLAŞILANI TUTMAK ---
            # 1. Önce ESKİDEN YENİYE sırala (Böylece ilk gördüğümüz, en eski tarihli olur)
            items.sort(key=lambda x: x['tarih'], reverse=False)
            
            unique_items = []
            seen_texts = set()
            seen_images = set()
            
            for item in items:
                # Metin Hash'i (Text Deduplication)
                txt = item['text'] if item['text'] else ""
                content_hash = hashlib.md5(txt.strip().encode('utf-8')).hexdigest() if len(txt.strip()) > 20 else None
                
                # Resim Hash'i
                img_hash = item['img_hash']
                
                is_duplicate = False
                
                # Metin tekrarı kontrolü
                if content_hash and content_hash in seen_texts:
                    is_duplicate = True
                
                # Resim tekrarı kontrolü (Eğer resim varsa)
                if img_hash and img_hash in seen_images:
                    is_duplicate = True
                
                if not is_duplicate:
                    unique_items.append(item)
                    if content_hash:
                        seen_texts.add(content_hash)
                    if img_hash:
                        seen_images.add(img_hash)
            
            # 2. Listeyi tekrar YENİDEN ESKİYE (Ekranda göstermek için) çevir
            unique_items.sort(key=lambda x: x['tarih'], reverse=True)
            
            st.session_state.news_data = unique_items
            st.session_state.data_fetched = True
            st.success(f"{len(unique_items)} haber bulundu.")
        else:
            st.warning("Haber bulunamadı.")

# --- SONUÇLARI EKRANA BAS ---
if st.session_state.news_data:
    st.divider()
    
    # Temizleme Butonu
    if st.button("🗑️ LİSTEYİ TEMİZLE", use_container_width=True, type="secondary"):
        st.session_state.news_data = []
        st.session_state.data_fetched = False
        st.rerun()

    if st.session_state.hunting_mode:
        display_list = st.session_state.news_data
    else:
        st.subheader("🔎 Sonuç Filtresi")
        result_channels = sorted(list(set([item['kanal'] for item in st.session_state.news_data])))
        cols = st.columns(4)
        selected_view_channels = []
        for i, ch in enumerate(result_channels):
            with cols[i % 4]:
                if st.checkbox(f"@{ch}", value=True, key=f"post_{ch}"):
                    selected_view_channels.append(ch)
        display_list = [n for n in st.session_state.news_data if n['kanal'] in selected_view_channels]

    # Kartları oluştur
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

# --- OTOMATİK YENİLEME MANTIĞI (En Sonda) ---
if st.session_state.hunting_mode:
    time.sleep(15)
    st.rerun()
