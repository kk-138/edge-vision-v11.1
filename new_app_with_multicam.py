import os
import sys
import time
import signal
import threading
import cv2
import requests
import numpy as np
from datetime import datetime
from collections import deque
import json
import queue
import shutil
from flask import Flask, Response, jsonify, render_template, request, send_from_directory
import sounddevice as sd
from flask_sock import Sock

# 自動切換工作目錄至腳本所在目錄，避免從專案根目錄執行時找不到模型或設定檔
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 載入優化工具與推論模型 (請確保 fall_detector.py 在同一層目錄)
from fall_detector import limit_onnxruntime_threads, FallDetector

# ================= 效能防護設定 (防線 1) =================
n_cores = os.cpu_count() or 4
INTRA_THREADS = 6
cv2.setNumThreads(1)
limit_onnxruntime_threads(intra_threads=INTRA_THREADS, inter_threads=1)
print(f"系統初始化 － 設定 intra_op_num_threads = {INTRA_THREADS}")

# ================= 攝影機與環境設定 =================
CONFIG_FILE = "cameras.json"

def load_camera_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            for item in cfg:
                if "zone" not in item:
                    item["zone"] = "浴室門口"
            return cfg
    else:
        default = [{"source": 0, "name": "CAM 0", "zone": "浴室門口"}]
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=4)
        return default

def save_camera_config(config_list):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_list, f, ensure_ascii=False, indent=4)

# ================= 區域管理設定 =================
ZONES_FILE = "zones.json"
DEFAULT_ZONES = ["客廳走道", "浴室門口", "主臥床緣", "廚房", "玄關大門", "樓梯口", "陽台"]

def load_zones():
    zones = list(DEFAULT_ZONES)
    if os.path.exists(ZONES_FILE):
        try:
            with open(ZONES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    zones = data
        except Exception as e:
            print(f"Error loading zones.json: {e}")
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                for item in cfg:
                    z = item.get("zone")
                    if z and z not in zones:
                        zones.append(z)
        except Exception:
            pass
    save_zones(zones)
    return zones

def save_zones(zones_list):
    seen = set()
    cleaned = []
    for z in zones_list:
        z_str = str(z).strip()
        if z_str and z_str not in seen:
            seen.add(z_str)
            cleaned.append(z_str)
    with open(ZONES_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=4)
    return cleaned

camera_config = load_camera_config()
load_zones()

# ================= 區域跌倒統計設定 =================
ZONE_COUNTS_FILE = "zone_counts.json"

def load_zone_counts():
    if os.path.exists(ZONE_COUNTS_FILE):
        try:
            with open(ZONE_COUNTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def increment_zone_count(zone_name):
    counts = load_zone_counts()
    counts[zone_name] = counts.get(zone_name, 0) + 1
    try:
        with open(ZONE_COUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(counts, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving zone_counts.json: {e}")

def reset_zone_counts():
    try:
        with open(ZONE_COUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"Error resetting zone_counts.json: {e}")
        return False

CAMERA_SOURCES = [c["source"] for c in camera_config]
N_CAMERAS = len(CAMERA_SOURCES)
SKIP_INTERVAL = 3        # 跳幀間隔 (防線 4)

EVENT_DIR = "event_videos"
DAILY_DIR = "daily_videos"
EVENT_IMG_DIR = "event_images"
FALSE_POSITIVE_DIR = "false_positives"
os.makedirs(EVENT_DIR, exist_ok=True)
os.makedirs(DAILY_DIR, exist_ok=True)
os.makedirs(EVENT_IMG_DIR, exist_ok=True) # 🌟 讓系統自動建立照片資料夾
os.makedirs(FALSE_POSITIVE_DIR, exist_ok=True) # 🌟 誤報事件影片微調資料夾 (供模型微調，UI不呈現)

ASSUMED_FPS = 10 
RETENTION_SECONDS = 3 * 24 * 60 * 60  # 3 天保留期
PRE_FALL_FRAMES = 15 * ASSUMED_FPS  
POST_FALL_FRAMES = 15 * ASSUMED_FPS 

SETTINGS_FILE = "settings.json"

def load_settings():
    default_settings = {
        "DISCORD_WEBHOOK_URL": "",
        "FALL_CONFIRM_SECONDS": 2.0,
        "FALL_CONF_THRESHOLD": 0.35,
        "STATIONARY_MINUTES": 10,
        "ENABLE_FALL_NOTIF": True,
        "ENABLE_INTRUSION_NOTIF": True,
        "INCLUDE_SNAPSHOT": True,
        "INCLUDE_VIDEO": True,
        "ALERT_COOLDOWN_SECONDS": 30,
        "L2_COUNTDOWN_SECONDS": 15,
        "DAILY_RETENTION_DAYS": 3,
        "PRE_FALL_SECONDS": 15,
        "POST_FALL_SECONDS": 15,
        "DEBOUNCE_ASPECT_RATIO": 1.25,
        "DEBOUNCE_TILT_ANGLE": 60,
        "L1_BORDER_BLINK": True,
        "L1_DISCORD_NOTIF": True
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_settings.update(data)
                return default_settings
        except Exception:
            pass
    return default_settings

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

app_settings = load_settings()

COOLDOWN_SECONDS = 30
CHUNK_SECONDS = 60  # 24 小時錄影的單檔長度 (測試用 60 秒)

# ================= 全域狀態與網頁串流變數 =================
app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
sock = Sock(app)
detector = FallDetector("best.onnx")

# ================= 即時對講與監視器音訊回放 (Intercom) =================
intercom_audio_queue = queue.Queue(maxsize=300)
intercom_stream = None

def play_intercom_chime(kind="connect"):
    """現場喇叭播放提示音：connect (叮咚升調) / disconnect (掛斷降調)"""
    try:
        sr = 16000
        if kind == "connect":
            t1 = np.linspace(0, 0.12, int(sr * 0.12), False)
            t2 = np.linspace(0, 0.18, int(sr * 0.18), False)
            w1 = (np.sin(2 * np.pi * 587.33 * t1) * 6000 * np.linspace(1, 0.4, len(t1))).astype(np.int16)
            w2 = (np.sin(2 * np.pi * 880.0 * t2) * 6000 * np.linspace(1, 0.2, len(t2))).astype(np.int16)
            tone = np.concatenate([w1, w2])
        else:
            t1 = np.linspace(0, 0.12, int(sr * 0.12), False)
            t2 = np.linspace(0, 0.2, int(sr * 0.2), False)
            w1 = (np.sin(2 * np.pi * 659.25 * t1) * 5000 * np.linspace(1, 0.4, len(t1))).astype(np.int16)
            w2 = (np.sin(2 * np.pi * 440.0 * t2) * 5000 * np.linspace(1, 0.2, len(t2))).astype(np.int16)
            tone = np.concatenate([w1, w2])
        if not intercom_audio_queue.full():
            intercom_audio_queue.put(tone)
    except Exception as e:
        print(f"提示音產生失敗: {e}")

def intercom_playback_loop():
    """背景執行緒：即時從佇列獲取 PCM 並直接送至監視器/主機硬體喇叭播放"""
    global intercom_stream

    def _get_stream():
        global intercom_stream
        if intercom_stream is not None:
            return intercom_stream
        try:
            intercom_stream = sd.OutputStream(samplerate=16000, channels=1, dtype='int16')
            intercom_stream.start()
            print("監視器雙向對講喇叭通道已啟動 (16kHz 16-bit PCM)")
            return intercom_stream
        except Exception as err:
            intercom_stream = None
            return None

    _get_stream()

    while is_running:
        try:
            chunk = intercom_audio_queue.get(timeout=0.5)
            if chunk is None:
                continue
            stream = _get_stream()
            if stream is not None:
                try:
                    stream.write(chunk)
                except Exception as write_err:
                    print(f"音訊寫入錯誤: {write_err}")
                    try:
                        stream.stop()
                        stream.close()
                    except Exception:
                        pass
                    intercom_stream = None
        except queue.Empty:
            continue
        except Exception as e:
            time.sleep(0.02)

# intercom_thread = threading.Thread(target=intercom_playback_loop, daemon=True)
# intercom_thread.start()

# 全域程式運行旗標與關閉處理
is_running = True
active_streams = []

def graceful_shutdown(signum=None, frame=None):
    """安全關閉系統常式：釋放所有攝影機與檔案寫入器，確保 Ctrl+C 俐落退出"""
    global is_running, intercom_stream
    print("\n" + "=" * 60)
    print("收到關閉訊號，正在安全退出系統")
    is_running = False
    
    # 1. 釋放所有攝影機硬體串流
    try:
        for s in active_streams:
            if s is not None:
                s.release()
    except Exception as e:
        print(f"釋放攝影機提示: {e}")

    # 2. 安全關閉所有進行中的連續錄影寫入器 (確保 MP4 索引正常封裝)
    try:
        for state in cam_states:
            w = state.get("continuous_writer")
            if w:
                w.release()
    except Exception as e:
        print(f"釋放錄影寫入器提示: {e}")

    # 3. 釋放音訊輸出裝置
    try:
        if intercom_stream is not None:
            intercom_stream.stop()
            intercom_stream.close()
    except Exception as e:
        print(f"釋放音效裝置提示: {e}")

    print("所有攝影機串流、音訊通道與錄影檔案已安全關閉。系統已順利退出！")
    print("=" * 60)
    os._exit(0)

# 網頁串流用的最新拼接畫面
latest_display_frame = None
display_lock = threading.Lock()

# 獨立管理每支攝影機的狀態
cam_states = []
for i in range(N_CAMERAS):
    cam_states.append({
        "name": camera_config[i].get("name", f"CAM {i}"),
        "zone": camera_config[i].get("zone", "浴室門口"),
        "is_online": False,
        "status": {"is_falling": False, "fall_count": 0, "is_loitering": False},
        "pre_fall_buffer": deque(maxlen=60 * ASSUMED_FPS),
        "post_fall_buffer": [],
        "is_recording_event": False,
        "continuous_writer": None,
        "chunk_start_time": 0,
        "last_alert_time": 0,
        "last_fence_alert_time": 0,
        "last_stationary_alert_time": 0,
        "stationary_start_time": 0,
        "last_known_center": None,
        "last_boxes": [],
        "fence_polygon": [],
        "is_active": True,
        "is_privacy_mode": False
    })

# ================= 獨立讀取執行緒 (防線 2) =================
class CameraStream:
    def __init__(self, src, width=640, height=480):
        self.src = src
        if isinstance(src, int) or (isinstance(src, str) and src.isdigit()):
            self.cap = cv2.VideoCapture(int(src), cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(src)
        
        if self.cap.isOpened():
            try:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            except Exception as e:
                print(f"無法設定攝影機參數 (src={src}): {e}")
        self.ret = False
        self.frame = None
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self):
        while self.running and is_running:
            if not getattr(self, 'cap', None) or not self.cap.isOpened():
                time.sleep(1.0)
                if isinstance(self.src, int) or (isinstance(self.src, str) and self.src.isdigit()):
                    self.cap = cv2.VideoCapture(int(self.src), cv2.CAP_DSHOW)
                else:
                    self.cap = cv2.VideoCapture(self.src)
                
                if self.cap.isOpened():
                    try:
                        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    except Exception as e:
                        print(f"重連時無法設定攝影機參數 (src={self.src}): {e}")
                continue

            ret, frame = self.cap.read()
            with self.lock:
                self.ret = ret
                if ret: self.frame = frame
            
            # 如果讀取失敗（例如斷線或被其他串流佔用），釋放並暫停，下個迴圈重新連接
            if not ret:
                time.sleep(1.0)
                self.cap.release()

    def read(self):
        with self.lock:
            if self.frame is None: return False, None
            return self.ret, self.frame.copy()

    def release(self):
        self.running = False
        try:
            self.thread.join(timeout=0.5)
        except Exception:
            pass
        try:
            self.cap.release()
        except Exception:
            pass

# ================= 輔助功能模組 =================
def send_discord_alert(frame, cam_idx, event_type="跌倒", image_name=None, image_path=None):
    """發送附帶圖片的 Discord 警報，並確保照片獨立存檔"""
    if not image_path or not os.path.exists(image_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_name = f"cam{cam_idx}_{event_type}_{timestamp}.jpg"
        image_path = os.path.join(EVENT_IMG_DIR, image_name)
        cv2.imwrite(image_path, frame)
        print(f"已儲存事件截圖：{image_path}")
    
    cam_name = cam_states[cam_idx].get("name", f"CAM {cam_idx}") if cam_idx < len(cam_states) else f"CAM {cam_idx}"
    cam_zone = cam_states[cam_idx].get("zone", "未設定區域") if cam_idx < len(cam_states) else "未設定區域"

    if event_type == "越界":
        if not app_settings.get("ENABLE_INTRUSION_NOTIF", True):
            print("越界推播通知已設定為停用，跳過發送")
            return
        msg = f"警告！{cam_name} ({cam_zone}) 偵測到「危險區域越界」！\n越界當下之截圖畫面："
    elif event_type == "異常滯留":
        if not app_settings.get("L1_DISCORD_NOTIF", True):
            print("異常滯留推播通知已設定為停用，跳過發送")
            return
        stat_mins = float(app_settings.get("STATIONARY_MINUTES", 10))
        msg = f"警示！{cam_name} ({cam_zone}) 偵測到長輩異常滯留超過 {stat_mins} 分鐘\n請確認長輩活動狀態，附上現場截圖。"
    elif event_type == "危險區域跌倒":
        if not app_settings.get("ENABLE_FALL_NOTIF", True):
            print("跌倒推播通知已設定為停用，跳過發送")
            return
        msg = f"！！極危險！！{cam_name} ({cam_zone}) 偵測到長輩在「危險區域內跌倒」！\n請立即確認或派人查看！\n30 秒事件影片正在背景生成中！"
    else:
        if not app_settings.get("ENABLE_FALL_NOTIF", True):
            print("⚠️ 跌倒推播通知已設定為停用，跳過發送")
            return
        msg = f"警告！{cam_name} ({cam_zone}) 偵測到「跌倒事件」！\n30 秒事件影片正在背景生成中！"
        
    webhook_url = app_settings.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("未設定 Discord Webhook URL，跳過通知發送")
        return

    data = {"content": msg}
    try:
        if app_settings.get("INCLUDE_SNAPSHOT", True) and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                requests.post(webhook_url, data=data, files={"file": (image_name, f, "image/jpeg")}, timeout=10)
        else:
            requests.post(webhook_url, json=data, timeout=10)
    except Exception as e:
        print(f"Discord 傳送失敗: {e}")

def create_video_writer(filepath, fps, dim):
    """建立支援瀏覽器 HTML5 <video> 直接回放的 H.264 (avc1) 影片寫入器，若未支援則自動降級"""
    writer = cv2.VideoWriter(filepath, cv2.VideoWriter_fourcc(*'avc1'), fps, dim)
    if not writer.isOpened():
        print("avc1 (H.264) 編碼器初始化失敗，降級使用 mp4v")
        writer = cv2.VideoWriter(filepath, cv2.VideoWriter_fourcc(*'mp4v'), fps, dim)
    return writer

def save_event_video(pre_frames, post_frames, timestamp, cam_idx):
    """背景合併並儲存 30 秒事件影片 (H.264 編碼，支援網頁原生回放)"""
    all_frames = pre_frames + post_frames
    if not all_frames: return
    height, width, _ = all_frames[0].shape
    filepath = os.path.join(EVENT_DIR, f"cam{cam_idx}_event_{timestamp}.mp4")
    out = create_video_writer(filepath, ASSUMED_FPS, (width, height))
    for f in all_frames: out.write(f)
    out.release()
    print(f"攝影機 {cam_idx} 獨立 30 秒事件影片已生成：{filepath}")

def cleanup_old_videos(directory):
    """清理超過保留期的舊檔案 (依據 DAILY_RETENTION_DAYS 設定動態清理)"""
    if not os.path.exists(directory):
        return
    now = time.time()
    try:
        days = float(app_settings.get("DAILY_RETENTION_DAYS", 3))
    except (ValueError, TypeError):
        days = 3.0
    retention_seconds = max(1.0, days) * 24 * 60 * 60

    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path) and (now - os.path.getctime(file_path) > retention_seconds):
            try:
                os.remove(file_path)
                print(f"已刪除超過 {days} 天的過期檔案：{filename}")
            except Exception as e:
                print(f"刪除過期檔案失敗 {file_path}: {e}")

# ================= 非同步 AI 推論 =================
inference_in_progress = False

def calculate_iomin(box1, box2):
    """計算 Intersection over Minimum Area，用來判斷是否有小框包含在大框內"""
    x1_1, y1_1, x2_1, y2_1 = box1[:4]
    x1_2, y1_2, x2_2, y2_2 = box2[:4]
    
    x_left = max(x1_1, x1_2)
    y_top = max(y1_1, y1_2)
    x_right = min(x2_1, x2_2)
    y_bottom = min(y2_1, y2_2)
    
    if x_right <= x_left or y_bottom <= y_top:
        return 0.0
        
    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    box1_area = max(0.01, (x2_1 - x1_1) * (y2_1 - y1_1))
    box2_area = max(0.01, (x2_2 - x1_2) * (y2_2 - y1_2))
    
    return intersection_area / min(box1_area, box2_area)

def filter_overlapping_boxes(boxes, overlap_threshold=0.4):
    """如果兩個框高度重疊 (包含)，只保留信心值較高的一個"""
    if not boxes:
        return []
    # 依照信心值 (conf) 由高到低排序
    sorted_boxes = sorted(boxes, key=lambda b: b[4], reverse=True)
    keep = []
    
    for box in sorted_boxes:
        overlap = False
        for k_box in keep:
            if calculate_iomin(box, k_box) > overlap_threshold:
                overlap = True
                break
        if not overlap:
            keep.append(box)
            
    return keep

def do_async_inference(frames_to_infer):
    global inference_in_progress
    try:
        conf_thres = float(app_settings.get("FALL_CONF_THRESHOLD", 0.35))
        batch_boxes = detector.predict_batch(frames_to_infer, conf_thres=conf_thres)
        for idx, b in enumerate(batch_boxes):
            if idx < len(cam_states):
                filtered_b = filter_overlapping_boxes(b, overlap_threshold=0.4)
                cam_states[idx]["last_boxes"] = filtered_b
                cam_states[idx]["last_infer_frame"] = frames_to_infer[idx]
    except Exception as e:
        print(f"AI 推論發生錯誤: {e}")
    finally:
        inference_in_progress = False

def get_frame_with_boxes(base_frame, boxes):
    """為警報截圖加上 AI 辨識框線"""
    f = base_frame.copy()
    for box in boxes:
        x1, y1, x2, y2, conf, class_name = box
        color = (0, 0, 255) if class_name.lower() == 'fall' else (0, 255, 0)
        label = f"FALL! {conf:.2f}" if class_name.lower() == 'fall' else f"{class_name} {conf:.2f}"
        cv2.rectangle(f, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
        cv2.putText(f, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    return f

# ================= 核心背景引擎 (24小時獨立運作) =================
# 動作駐列 (用來安全地新增/刪除攝影機)
camera_action_queue = queue.Queue()

def core_monitor_loop():
    """防線 2：專屬的背景執行緒，確保影像讀取與推論不被網頁請求卡住"""
    global latest_display_frame, N_CAMERAS, active_streams
    streams = [CameraStream(src) for src in CAMERA_SOURCES]
    active_streams = streams
    frame_count = 0
    print(f"核心監控引擎已啟動，監控 {N_CAMERAS} 號攝影機")

    try:
        while is_running:
            time.sleep(0.05)  # 防線 3：限制迴圈速率，避免 CPU 空轉

            # 處理新增/刪除/重新命名攝影機的請求
            while not camera_action_queue.empty():
                action = camera_action_queue.get()
                if action["action"] == "add":
                    src = action["source"]
                    name = action.get("name") or f"CAM {N_CAMERAS}"
                    zone = action.get("zone") or "浴室門口"
                    streams.append(CameraStream(src))
                    cam_states.append({
                        "name": name,
                        "zone": zone,
                        "is_online": False,
                        "status": {"is_falling": False, "fall_count": 0, "is_loitering": False},
                        "pre_fall_buffer": deque(maxlen=PRE_FALL_FRAMES),
                        "post_fall_buffer": [],
                        "is_recording_event": False,
                        "continuous_writer": None,
                        "chunk_start_time": 0,
                        "last_alert_time": 0,
                        "last_fence_alert_time": 0,
                        "last_stationary_alert_time": 0,
                        "stationary_start_time": 0,
                        "last_known_center": None,
                        "last_boxes": [],
                        "fence_polygon": [],
                        "is_active": True,
                        "is_privacy_mode": False
                    })
                    camera_config.append({"source": src, "name": name, "zone": zone})
                    save_camera_config(camera_config)
                    CAMERA_SOURCES.append(src)
                    N_CAMERAS += 1
                elif action["action"] == "delete":
                    idx = action["idx"]
                    if 0 <= idx < N_CAMERAS:
                        streams[idx].release()
                        streams.pop(idx)
                        cam_states.pop(idx)
                        camera_config.pop(idx)
                        CAMERA_SOURCES.pop(idx)
                        save_camera_config(camera_config)
                        N_CAMERAS -= 1
                elif action["action"] in ("rename", "update_info"):
                    idx = action["idx"]
                    if 0 <= idx < N_CAMERAS:
                        if action.get("name"):
                            cam_states[idx]["name"] = action["name"]
                            camera_config[idx]["name"] = action["name"]
                        if action.get("zone"):
                            cam_states[idx]["zone"] = action["zone"]
                            camera_config[idx]["zone"] = action["zone"]
                        save_camera_config(camera_config)
                elif action["action"] == "toggle_active":
                    idx = action["idx"]
                    active = action["active"]
                    if 0 <= idx < N_CAMERAS:
                        if active and streams[idx] is None:
                            streams[idx] = CameraStream(CAMERA_SOURCES[idx])
                            cam_states[idx]["is_active"] = True
                        elif not active and streams[idx] is not None:
                            streams[idx].release()
                            streams[idx] = None
                            cam_states[idx]["is_active"] = False

            if N_CAMERAS == 0:
                continue

            frames = []
            read_ok = []
            for idx, s in enumerate(streams):
                if s is not None:
                    ret, frame = s.read()
                else:
                    ret, frame = False, None
                
                read_ok.append(ret)
                if not ret:
                    # 如果攝影機離線或被手動關閉，給予一個黑色空畫面
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    if not cam_states[idx].get("is_active", True):
                        cv2.putText(frame, "CAMERA POWER OFF", (180, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
                frames.append(frame)
                cam_states[idx]["is_online"] = ret

            frame_count += 1
            current_time = time.time()

            # 防線 4：跳幀 + 異步 Batch 批次推論
            global inference_in_progress
            need_infer = (frame_count % SKIP_INTERVAL == 0) or any(len(state["last_boxes"]) == 0 for state in cam_states)
            if need_infer and not inference_in_progress:
                inference_in_progress = True
                infer_frames = [f.copy() for f in frames]
                threading.Thread(target=do_async_inference, args=(infer_frames,), daemon=True).start()

            processed_frames = []

            # 依設定計算跌倒需連續維持之幀數 (例：2 秒 * 10 FPS = 20 幀)
            confirm_sec = float(app_settings.get("FALL_CONFIRM_SECONDS", 2))
            required_fall_frames = max(2, int(confirm_sec * ASSUMED_FPS))

            # 分別處理每路攝影機的邏輯
            for cam_idx in range(N_CAMERAS):
                frame = frames[cam_idx]
                state = cam_states[cam_idx]
                boxes = state["last_boxes"]
                
                fall_detected = False

                # ====== 電子圍籬前置作業 ======
                fence_pts = state.get("fence_polygon", [])
                poly = None
                if fence_pts and len(fence_pts) >= 3:
                    h, w = frame.shape[:2]
                    poly = np.array([[(p['x'] / 100.0) * w, (p['y'] / 100.0) * h] for p in fence_pts], np.int32)
                    cv2.polylines(frame, [poly], isClosed=True, color=(0, 255, 255), thickness=2)
                
                intrusion_detected = False
                fall_in_fence_detected = False

                # 隱藏實體辨識框，僅在背景做邏輯運算
                for box in boxes:
                    x1, y1, x2, y2, conf, class_name = box
                    is_falling = (class_name.lower() == 'fall')
                    if is_falling:
                        fall_detected = True 

                    # 檢查電子圍籬入侵
                    if poly is not None:
                        bottom_center = ((x1 + x2) / 2, y2)
                        if cv2.pointPolygonTest(poly, bottom_center, False) >= 0:
                            intrusion_detected = True
                            if is_falling:
                                fall_in_fence_detected = True

                # ====== 觸發越界警報 ======
                cooldown_sec = float(app_settings.get("ALERT_COOLDOWN_SECONDS", 30))
                if intrusion_detected and not fall_detected:  # 如果已經跌倒了，就交給跌倒邏輯處理更嚴重的警報
                    if current_time - state.get("last_fence_alert_time", 0) > cooldown_sec:
                        print(f"攝影機 {cam_idx} ({state.get('zone','')}) 觸發危險區域越界！")
                        alert_img = get_frame_with_boxes(state.get("last_infer_frame", frame), boxes)
                        if poly is not None:
                            cv2.polylines(alert_img, [poly], isClosed=True, color=(0, 255, 255), thickness=2)
                        raw_img = state.get("last_infer_frame", frame)
                        
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        img_name = f"cam{cam_idx}_越界_{timestamp}.jpg"
                        img_path = os.path.join(EVENT_IMG_DIR, img_name)
                        raw_img_path = os.path.join(EVENT_IMG_DIR, img_name.replace(".jpg", "_raw.jpg"))
                        
                        cv2.imwrite(img_path, alert_img)
                        cv2.imwrite(raw_img_path, raw_img)
                        
                        threading.Thread(target=send_discord_alert, args=(alert_img, cam_idx, "越界", img_name, img_path)).start()
                        state["last_fence_alert_time"] = current_time

                # ====== 觸發異常滯留警報 (Level 1) ======
                stat_minutes = float(app_settings.get("STATIONARY_MINUTES", 10))
                current_center = None
                for box in boxes:
                    x1, y1, x2, y2, conf, class_name = box
                    if class_name.lower() != 'fall':
                        current_center = ((x1 + x2) / 2, (y1 + y2) / 2)
                        break
                
                if current_center is not None:
                    if state.get("last_known_center") is None:
                        state["last_known_center"] = current_center
                        state["stationary_start_time"] = current_time
                    else:
                        prev_x, prev_y = state["last_known_center"]
                        curr_x, curr_y = current_center
                        dist = ((curr_x - prev_x)**2 + (curr_y - prev_y)**2) ** 0.5
                        if dist > 50:  # 容許 50 像素的微小晃動
                            state["last_known_center"] = current_center
                            state["stationary_start_time"] = current_time
                        else:
                            elapsed = current_time - state.get("stationary_start_time", current_time)
                            if elapsed >= stat_minutes * 60:
                                if current_time - state.get("last_stationary_alert_time", 0) > cooldown_sec:
                                    print(f"攝影機 {cam_idx} ({state.get('zone','')}) 偵測到異常滯留超過 {stat_minutes} 分鐘！")
                                    alert_img = get_frame_with_boxes(state.get("last_infer_frame", frame), boxes)
                                    if poly is not None:
                                        cv2.polylines(alert_img, [poly], isClosed=True, color=(0, 255, 255), thickness=2)
                                    raw_img = state.get("last_infer_frame", frame)

                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    img_name = f"cam{cam_idx}_異常滯留_{timestamp}.jpg"
                                    img_path = os.path.join(EVENT_IMG_DIR, img_name)
                                    raw_img_path = os.path.join(EVENT_IMG_DIR, img_name.replace(".jpg", "_raw.jpg"))

                                    cv2.imwrite(img_path, alert_img)
                                    cv2.imwrite(raw_img_path, raw_img)

                                    threading.Thread(target=send_discord_alert, args=(alert_img, cam_idx, "異常滯留", img_name, img_path)).start()
                                    state["last_stationary_alert_time"] = current_time
                                    state["status"]["is_loitering"] = True
                else:
                    state["last_known_center"] = None
                    state["stationary_start_time"] = 0
                    state["status"]["is_loitering"] = False

                # ====== 軌道 1：30 秒事件精華邏輯 ======
                state["pre_fall_buffer"].append(frame.copy())
                
                if fall_detected:
                    state["status"]["fall_count"] += 1
                    state["status"]["not_fall_count"] = 0
                    if state["status"]["fall_count"] >= required_fall_frames: 
                        state["status"]["is_falling"] = True
                        if not state["status"].get("has_alerted", False) and not state["is_recording_event"]:
                            if current_time - state["last_alert_time"] > cooldown_sec:
                                state["status"]["has_alerted"] = True
                                event_type = "危險區域跌倒" if fall_in_fence_detected else "跌倒"
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            
                                increment_zone_count(state.get("zone", "未設定區域"))
                                
                                img_name = f"cam{cam_idx}_{event_type}_{timestamp}.jpg"
                                img_path = os.path.join(EVENT_IMG_DIR, img_name)
                                raw_img_path = os.path.join(EVENT_IMG_DIR, img_name.replace(".jpg", "_raw.jpg"))
                                
                                alert_img = get_frame_with_boxes(state.get("last_infer_frame", frame), boxes)
                                if poly is not None:
                                    cv2.polylines(alert_img, [poly], isClosed=True, color=(0, 255, 255), thickness=2)
                                cv2.imwrite(img_path, alert_img)
                                cv2.imwrite(raw_img_path, state.get("last_infer_frame", frame))
                                print(f"攝影機 {cam_idx} ({state.get('zone','')}) 觸發{event_type}！已儲存截圖：{img_path}")

                                threading.Thread(target=send_discord_alert, args=(alert_img, cam_idx, event_type, img_name, img_path)).start()
                                state["last_alert_time"] = current_time 
                                if app_settings.get("INCLUDE_VIDEO", True):
                                    state["is_recording_event"] = True
                                    state["post_fall_buffer"] = [] 
                                    # 凍結事件發生當下的 pre_fall_buffer，避免跳轉與重複畫面
                                    pre_sec = float(app_settings.get("PRE_FALL_SECONDS", 15))
                                    pre_frames_needed = max(10, int(pre_sec * ASSUMED_FPS))
                                    state["frozen_pre_frames"] = list(state["pre_fall_buffer"])[-pre_frames_needed:]
                                    state["event_timestamp"] = timestamp
                else:
                    state["status"]["not_fall_count"] = state["status"].get("not_fall_count", 0) + 1
                    # 必須連續 N 幀都沒偵測到跌倒，才真正解除狀態 (防抖機制，避免 AI 單幀閃爍誤判長輩已爬起)
                    if state["status"]["not_fall_count"] >= required_fall_frames:
                        state["status"]["fall_count"] = 0
                        state["status"]["is_falling"] = False
                        state["status"]["has_alerted"] = False

                if state["is_recording_event"]:
                    state["post_fall_buffer"].append(frame.copy())
                    post_sec = float(app_settings.get("POST_FALL_SECONDS", 15))
                    post_frames_needed = max(10, int(post_sec * ASSUMED_FPS))
                    if len(state["post_fall_buffer"]) >= post_frames_needed:
                        pre_to_save = state.pop("frozen_pre_frames", [])
                        evt_timestamp = state.pop("event_timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))
                        threading.Thread(target=save_event_video, args=(pre_to_save, state["post_fall_buffer"], evt_timestamp, cam_idx)).start()
                        state["is_recording_event"] = False

                # ====== 軌道 2：24 小時連續錄影邏輯 (僅在攝影機上線時錄製) ======
                if state.get("is_online", False):
                    height, width, _ = frame.shape
                    writer = state.get("continuous_writer")
                    need_new_writer = (
                        writer is None 
                        or (current_time - state["chunk_start_time"] >= CHUNK_SECONDS)
                        or state.get("writer_dim") != (width, height)
                    )
                    if need_new_writer:
                        if writer is not None:
                            writer.release()
                        
                        # 第一路攝影機負責觸發清理即可，避免重複執行
                        if cam_idx == 0:
                            cleanup_old_videos(DAILY_DIR)
                            cleanup_old_videos(EVENT_DIR)
                            cleanup_old_videos(EVENT_IMG_DIR) # 🌟 順便清理 3 天前的舊照片

                        filepath = os.path.join(DAILY_DIR, f"cam{cam_idx}_record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
                        state["continuous_writer"] = create_video_writer(filepath, ASSUMED_FPS, (width, height))
                        state["writer_dim"] = (width, height)
                        state["chunk_start_time"] = current_time
                        print(f"攝影機 {cam_idx} 開始錄製新連續區段：{filepath}")

                    if state["continuous_writer"] is not None:
                        state["continuous_writer"].write(frame)
                else:
                    if state.get("continuous_writer") is not None:
                        state["continuous_writer"].release()
                        state["continuous_writer"] = None

               # 將處理好的畫面加入陣列準備拼接
                # 這裡原本有 cv2.putText 顯示 CAM 名稱，現在交給前端 HTML 顯示以支援中文
                
                # 保持原始比例
                processed_frames.append(frame)

            # ====== 網頁畫面更新 ======
            # 將多路畫面水平拼接（如果畫面太大，可以在這裡縮放）
            for idx, processed_frame in enumerate(processed_frames):
                cam_states[idx]["latest_frame"] = processed_frame.copy()

    finally:
        for s in streams: s.release()
        for state in cam_states:
            if state["continuous_writer"]: state["continuous_writer"].release()

# ================= Flask 網頁路由 =================
# 加上 cam_idx 參數
def stream_generator(cam_idx):
    """為每支攝影機提供獨立的串流生成器"""
    while is_running:
        if cam_idx >= N_CAMERAS:
            break
        state = cam_states[cam_idx]
        
        if state.get("is_privacy_mode", False):
            # 回傳帶有隱私模式字樣的黑畫面
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "PRIVACY MODE ON", (150, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255,255,255), 2)
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.1)
            continue
            
        # 直接從 cam_states 裡面拿最新處理好的單路畫面
        frame = state.get("latest_frame")
        if frame is None:
            time.sleep(0.1)
            continue
            
        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.05)

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/monitor')
def index():
    # 將 N_CAMERAS 這個變數傳遞給網頁模板
    return render_template('index.html', n_cameras=N_CAMERAS)

# 透過迴圈自動幫其他頁面建立路由 (避免寫一長串)
pages = [
    "三階段警報", "危險區域入侵越界警報", 
    "高齡友善介面", "跌倒與異常姿態偵測", 
    "緊急聯繫與雙向語音", "隱私模式開關"
]

for page in pages:
    # 這邊使用一個小技巧，動態建立路由函數
    app.add_url_rule(f'/{page}.html', endpoint=page, view_func=lambda p=page: render_template(f'{p}.html', n_cameras=N_CAMERAS, camera_config=camera_config, cam_states=cam_states))

# 改成帶參數的路由
@app.route('/video_feed/<int:cam_idx>')
def video_feed(cam_idx):
    if cam_idx >= N_CAMERAS:
        return "Camera not found", 404
    return Response(stream_generator(cam_idx), mimetype='multipart/x-mixed-replace; boundary=frame')

# ================= 雙向對講 WebSocket 與 API 路由 =================
@sock.route('/ws/intercom/<int:cam_idx>')
def intercom_socket(ws, cam_idx):
    print(f"通話功能目前已暫時關閉。")
    try:
        while is_running:
            data = ws.receive()
            if data is None:
                break
    except Exception:
        pass

@app.route('/api/intercom/test_beep', methods=['POST'])
def intercom_test_beep():
    play_intercom_chime("connect")
    return jsonify({"success": True, "message": "現場喇叭提示音已播放"})

@app.route('/api/set_fence/<int:cam_idx>', methods=['POST'])
def set_fence(cam_idx):
    if cam_idx >= N_CAMERAS:
        return jsonify({"error": "Camera not found"}), 404
    data = request.json
    if not data or 'pointsPercent' not in data:
        return jsonify({"error": "Invalid data"}), 400
    
    cam_states[cam_idx]["fence_polygon"] = data['pointsPercent']
    return jsonify({"success": True})

@app.route('/api/rename_camera/<int:cam_idx>', methods=['POST'])
def rename_camera(cam_idx):
    if cam_idx >= N_CAMERAS:
        return jsonify({"error": "Camera not found"}), 404
    data = request.json or {}
    new_name = data.get('name', '').strip()
    if not new_name:
        return jsonify({"error": "Invalid data"}), 400
    
    camera_action_queue.put({"action": "rename", "idx": cam_idx, "name": new_name})
    return jsonify({"success": True, "name": new_name})

@app.route('/api/update_camera/<int:cam_idx>', methods=['POST'])
def update_camera_info(cam_idx):
    if cam_idx >= N_CAMERAS:
        return jsonify({"error": "Camera not found"}), 404
    data = request.json or {}
    name = data.get("name", "").strip() or None
    zone = data.get("zone", "").strip() or None
    camera_action_queue.put({"action": "update_info", "idx": cam_idx, "name": name, "zone": zone})
    return jsonify({"success": True, "name": name, "zone": zone})

# ================= 區域管理 API =================
@app.route('/api/zones', methods=['GET'])
def get_zones():
    return jsonify({"zones": load_zones()})

@app.route('/api/zones/add', methods=['POST'])
def add_zone():
    data = request.json or {}
    zone = data.get("zone", "").strip()
    if not zone:
        return jsonify({"error": "區域名稱不可為空"}), 400
    zones = load_zones()
    if zone not in zones:
        zones.append(zone)
        save_zones(zones)
    return jsonify({"success": True, "zones": zones, "added": zone})

@app.route('/api/zones/edit', methods=['POST'])
def edit_zone():
    data = request.json or {}
    old_zone = data.get("old_zone", "").strip()
    new_zone = data.get("new_zone", "").strip()
    if not old_zone or not new_zone:
        return jsonify({"error": "請提供舊名稱與新名稱"}), 400
    zones = load_zones()
    if old_zone in zones:
        idx = zones.index(old_zone)
        zones[idx] = new_zone
    elif new_zone not in zones:
        zones.append(new_zone)
    save_zones(zones)
    # 同步更新使用 old_zone 的攝影機
    for i, c in enumerate(camera_config):
        if c.get("zone") == old_zone:
            camera_action_queue.put({"action": "update_info", "idx": i, "name": c.get("name"), "zone": new_zone})
    return jsonify({"success": True, "zones": zones, "old_zone": old_zone, "new_zone": new_zone})

@app.route('/api/zones/delete', methods=['POST'])
def delete_zone():
    data = request.json or {}
    zone = data.get("zone", "").strip()
    if not zone:
        return jsonify({"error": "未指定刪除之區域"}), 400
    zones = load_zones()
    if zone in zones:
        zones.remove(zone)
        save_zones(zones)
    return jsonify({"success": True, "zones": zones, "deleted": zone})

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    if request.method == 'POST':
        data = request.json or {}
        for str_key in ["DISCORD_WEBHOOK_URL", "EMERGENCY_CONTACT_NAME", "EMERGENCY_CONTACT_PHONE"]:
            if str_key in data:
                app_settings[str_key] = str(data[str_key]).strip()
        for float_key in ["FALL_CONFIRM_SECONDS", "FALL_CONF_THRESHOLD", "DEBOUNCE_ASPECT_RATIO"]:
            if float_key in data:
                try:
                    app_settings[float_key] = float(data[float_key])
                except (ValueError, TypeError):
                    pass
        for int_key in ["STATIONARY_MINUTES", "ALERT_COOLDOWN_SECONDS", "L2_COUNTDOWN_SECONDS", "DAILY_RETENTION_DAYS", "PRE_FALL_SECONDS", "POST_FALL_SECONDS", "DEBOUNCE_TILT_ANGLE"]:
            if int_key in data:
                try:
                    app_settings[int_key] = int(data[int_key])
                except (ValueError, TypeError):
                    pass
        for bool_key in ["ENABLE_FALL_NOTIF", "ENABLE_INTRUSION_NOTIF", "INCLUDE_SNAPSHOT", "INCLUDE_VIDEO", "ENABLE_AUTO_CALL", "L1_BORDER_BLINK", "L1_DISCORD_NOTIF"]:
            if bool_key in data:
                app_settings[bool_key] = bool(data[bool_key])
        save_settings(app_settings)
        return jsonify({"success": True, "settings": app_settings})
    return jsonify(app_settings)

@app.route('/api/toggle_camera_power/<int:cam_idx>', methods=['POST'])
def toggle_camera_power(cam_idx):
    if cam_idx >= N_CAMERAS:
        return jsonify({"error": "Camera not found"}), 404
    data = request.json
    active = data.get("active", True)
    camera_action_queue.put({"action": "toggle_active", "idx": cam_idx, "active": active})
    return jsonify({"success": True, "active": active})

@app.route('/api/available_cameras', methods=['GET'])
def get_available_cameras():
    available = []
    used_sources = [c.get("source") for c in camera_config]
    # 掃描 0 到 3 的本機鏡頭
    for i in range(4):
        if i in used_sources or str(i) in used_sources:
            continue
        # 測試是否可以開啟
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                available.append(i)
            cap.release()
    return jsonify({"available": available})

def preview_stream(idx):
    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
    if not cap.isOpened():
        return
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.05)
    finally:
        cap.release()

@app.route('/api/preview_camera/<int:idx>')
def preview_camera(idx):
    return Response(preview_stream(idx), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/add_camera', methods=['POST'])
def add_camera():
    data = request.json
    source = data.get("source")
    if source is None:
        return jsonify({"error": "Invalid source"}), 400
    
    if str(source).isdigit():
        source = int(source)
    
    name = data.get("name") or f"CAM {N_CAMERAS}"
    zone = data.get("zone") or "浴室門口"
    original_n = N_CAMERAS
    camera_action_queue.put({"action": "add", "source": source, "name": name, "zone": zone})
    
    import time
    for _ in range(30):
        if N_CAMERAS > original_n:
            break
        time.sleep(0.1)
        
    return jsonify({"success": True})

@app.route('/api/delete_camera/<int:cam_idx>', methods=['POST'])
def delete_camera(cam_idx):
    if cam_idx >= N_CAMERAS:
        return jsonify({"error": "Camera not found"}), 404
    original_n = N_CAMERAS
    camera_action_queue.put({"action": "delete", "idx": cam_idx})
    
    import time
    for _ in range(30):
        if N_CAMERAS < original_n:
            break
        time.sleep(0.1)
        
    return jsonify({"success": True})

@app.route('/api/set_privacy/<int:cam_idx>', methods=['POST'])
def set_privacy(cam_idx):
    if cam_idx >= N_CAMERAS:
        return jsonify({"error": "Camera not found"}), 404
    data = request.json
    active = data.get("active", False)
    cam_states[cam_idx]["is_privacy_mode"] = active
    return jsonify({"success": True, "active": active})

@app.route('/status')
def status():
    # 匯總所有攝影機的狀態、名稱與所屬區域
    response_data = {
        f"cam_{i}": {
            "name": cam_states[i].get("name", f"CAM {i}"),
            "zone": cam_states[i].get("zone", "未設定區域"),
            "is_online": cam_states[i].get("is_online", False),
            "is_active": cam_states[i].get("is_active", True),
            "is_privacy_mode": cam_states[i].get("is_privacy_mode", False),
            "status": cam_states[i]["status"],
            "last_boxes": cam_states[i].get("last_boxes", [])
        } for i in range(N_CAMERAS)
    }
    response_data["global_settings"] = {
        "L1_BORDER_BLINK": app_settings.get("L1_BORDER_BLINK", True)
    }
    return jsonify(response_data)

@app.route('/records/events')
def get_event_records():
    files = [f for f in os.listdir(EVENT_DIR) if f.endswith('.mp4')]
    images = [f for f in os.listdir(EVENT_IMG_DIR) if f.endswith(('.jpg', '.png', '.jpeg'))]
    return jsonify({
        "events": sorted(files, reverse=True),
        "images": sorted(images, reverse=True)
    })

@app.route('/event_videos/<path:filename>')
def serve_event_video(filename):
    return send_from_directory(EVENT_DIR, filename, conditional=True)

@app.route('/event_images/<path:filename>')
def serve_event_image(filename):
    return send_from_directory(EVENT_IMG_DIR, filename)

@app.route('/daily_videos/<path:filename>')
def serve_daily_video(filename):
    return send_from_directory(DAILY_DIR, filename, conditional=True)

@app.route('/records/daily')
def get_daily_records():
    files = [f for f in os.listdir(DAILY_DIR) if f.endswith('.mp4')]
    return jsonify({"daily": sorted(files, reverse=True)})

@app.route('/api/records/reset_zones', methods=['POST'])
def api_reset_zones():
    success = reset_zone_counts()
    return jsonify({"success": success})

@app.route('/api/records/all')
def get_all_records():
    """統一回傳所有真實的 event_videos, event_images 與 daily_videos"""
    # 1. 取得事件錄影
    event_vids = []
    if os.path.exists(EVENT_DIR):
        for f in os.listdir(EVENT_DIR):
            if f.endswith('.mp4'):
                p = os.path.join(EVENT_DIR, f)
                st = os.stat(p)
                event_vids.append({
                    "filename": f,
                    "size_mb": round(st.st_size / (1024 * 1024), 2),
                    "mtime": st.st_mtime,
                    "time_str": datetime.fromtimestamp(st.st_mtime).strftime("%Y/%m/%d %H:%M:%S")
                })
    event_vids.sort(key=lambda x: x["mtime"], reverse=True)

    # 2. 取得跌倒快照截圖
    event_imgs = []
    if os.path.exists(EVENT_IMG_DIR):
        for f in os.listdir(EVENT_IMG_DIR):
            if f.endswith(('.jpg', '.png', '.jpeg')):
                p = os.path.join(EVENT_IMG_DIR, f)
                st = os.stat(p)
                event_imgs.append({
                    "filename": f,
                    "size_kb": round(st.st_size / 1024, 1),
                    "mtime": st.st_mtime,
                    "time_str": datetime.fromtimestamp(st.st_mtime).strftime("%Y/%m/%d %H:%M:%S")
                })
    event_imgs.sort(key=lambda x: x["mtime"], reverse=True)

    # 3. 取得 24 小時連續錄影分段檔
    daily_vids = []
    if os.path.exists(DAILY_DIR):
        for f in os.listdir(DAILY_DIR):
            if f.endswith('.mp4'):
                p = os.path.join(DAILY_DIR, f)
                st = os.stat(p)
                daily_vids.append({
                    "filename": f,
                    "size_mb": round(st.st_size / (1024 * 1024), 2),
                    "mtime": st.st_mtime,
                    "time_str": datetime.fromtimestamp(st.st_mtime).strftime("%Y/%m/%d %H:%M:%S")
                })
    daily_vids.sort(key=lambda x: x["mtime"], reverse=True)

    return jsonify({
        "events": event_vids,
        "images": event_imgs,
        "daily": daily_vids,
        "zones": load_zones(),
        "zone_counts": load_zone_counts(),
        "cameras": [{
            "idx": i,
            "name": cam_states[i].get("name", f"CAM {i}"),
            "zone": cam_states[i].get("zone", "未設定區域")
        } for i in range(N_CAMERAS)]
    })

@app.route('/api/trigger_fall_record/<int:cam_idx>', methods=['POST'])
def trigger_fall_record(cam_idx):
    """手動觸發產生真實的跌倒快照截圖與 30 秒事件錄影 (方便測試驗證)"""
    if cam_idx >= N_CAMERAS:
        return jsonify({"error": "Camera not found"}), 404
    state = cam_states[cam_idx]
    increment_zone_count(state.get("zone", "未設定區域"))
    frame = state.get("latest_frame")
    if frame is None:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.putText(frame, f"TEST FALL EVENT CAM {cam_idx}", (100, 360), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    img_name = f"cam{cam_idx}_跌倒_{timestamp}.jpg"
    img_path = os.path.join(EVENT_IMG_DIR, img_name)
    cv2.imwrite(img_path, frame)
    print(f"手動產生測試快照：{img_path}")

    # 合成測試事件影片 (依據設定的 PRE_FALL_SECONDS 與 POST_FALL_SECONDS)
    pre_sec = float(app_settings.get("PRE_FALL_SECONDS", 15))
    post_sec = float(app_settings.get("POST_FALL_SECONDS", 15))
    pre_needed = max(10, int(pre_sec * ASSUMED_FPS))
    post_needed = max(10, int(post_sec * ASSUMED_FPS))
    
    pre = list(state.get("pre_fall_buffer", []))[-pre_needed:]
    if len(pre) < pre_needed:
        pre = [frame.copy()] * (pre_needed - len(pre)) + pre
    post = [frame.copy()] * post_needed
    save_event_video(pre, post, timestamp, cam_idx)

    return jsonify({
        "success": True,
        "image": img_name,
        "video": f"cam{cam_idx}_event_{timestamp}.mp4"
    })

# ================= 歷史紀錄影片刪除 API =================
@app.route('/api/records/delete_single', methods=['POST'])
def delete_single_record():
    data = request.json or {}
    category = data.get("category") # "events" 或 "daily"
    filename = data.get("filename")
    image_filename = data.get("image_filename")
    deleted_files = []

    if not category or (not filename and not image_filename):
        return jsonify({"error": "缺少必要參數"}), 400

    target_dir = EVENT_DIR if category == "events" else DAILY_DIR
    
    if filename:
        clean_name = os.path.basename(filename)
        path = os.path.join(target_dir, clean_name)
        if os.path.exists(path):
            try:
                os.remove(path)
                deleted_files.append(clean_name)
            except Exception as e:
                print(f"Error removing {path}: {e}")

    if category == "events" and image_filename:
        clean_img = os.path.basename(image_filename)
        img_path = os.path.join(EVENT_IMG_DIR, clean_img)
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
                deleted_files.append(clean_img)
            except Exception as e:
                print(f"Error removing {img_path}: {e}")

    return jsonify({"success": True, "deleted": deleted_files})

@app.route('/api/records/delete_batch', methods=['POST'])
def delete_batch_records():
    data = request.json or {}
    category = data.get("category", "events") # "events" 或 "daily"
    items = data.get("items", []) # [{ "filename": "...", "image_filename": "..." }]
    deleted_count = 0

    target_dir = EVENT_DIR if category == "events" else DAILY_DIR
    for item in items:
        fn = item.get("filename") if isinstance(item, dict) else item
        img_fn = item.get("image_filename") if isinstance(item, dict) else None
        
        if fn:
            clean_fn = os.path.basename(fn)
            path = os.path.join(target_dir, clean_fn)
            if os.path.exists(path):
                try:
                    os.remove(path)
                    deleted_count += 1
                except Exception as e:
                    print(f"Error removing {path}: {e}")
        
        if category == "events" and img_fn:
            clean_img = os.path.basename(img_fn)
            img_path = os.path.join(EVENT_IMG_DIR, clean_img)
            if os.path.exists(img_path):
                try:
                    os.remove(img_path)
                except Exception as e:
                    print(f"Error removing {img_path}: {e}")

    return jsonify({"success": True, "deleted_count": deleted_count})

@app.route('/api/records/delete_all', methods=['POST'])
def delete_all_records():
    data = request.json or {}
    category = data.get("category", "all") # "events", "daily", or "all"
    deleted_count = 0

    dirs_to_clean = []
    if category in ("events", "all"):
        dirs_to_clean.append(EVENT_DIR)
        dirs_to_clean.append(EVENT_IMG_DIR)
    if category in ("daily", "all"):
        dirs_to_clean.append(DAILY_DIR)

    for d in dirs_to_clean:
        if os.path.exists(d):
            for fname in os.listdir(d):
                p = os.path.join(d, fname)
                if os.path.isfile(p):
                    try:
                        os.remove(p)
                        deleted_count += 1
                    except Exception as e:
                        print(f"Error removing {p}: {e}")

    return jsonify({"success": True, "deleted_count": deleted_count, "category": category})

# ================= 誤報事件微調收集 API (供模型微調，UI 不呈現) =================
@app.route('/api/records/mark_false_alarm', methods=['POST'])
def mark_false_alarm():
    data = request.json or {}
    filename = data.get("filename")
    image_filename = data.get("image_filename")
    is_false_alarm = data.get("is_false_alarm", True)

    manifest_path = os.path.join(FALSE_POSITIVE_DIR, "manifest.json")
    manifest = []
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            manifest = []

    copied_files = []
    removed_files = []

    if is_false_alarm:
        # 僅儲存乾淨截圖供 YOLO 微調使用，不再複製整個影片
        if image_filename:
            clean_img = os.path.basename(image_filename)
            raw_img = clean_img.replace(".jpg", "_raw.jpg")
            
            src_img_raw = os.path.join(EVENT_IMG_DIR, raw_img)
            src_img_annotated = os.path.join(EVENT_IMG_DIR, clean_img)
            
            # 優先使用乾淨的原圖，若無則退回使用標註過的圖
            src_img = src_img_raw if os.path.exists(src_img_raw) else src_img_annotated
            dst_img = os.path.join(FALSE_POSITIVE_DIR, clean_img)
            
            if os.path.exists(src_img):
                try:
                    shutil.copy2(src_img, dst_img)
                    copied_files.append(clean_img)
                except Exception as e:
                    print(f"Error copying {src_img} to {dst_img}: {e}")

        # 記錄至 manifest
        if filename or image_filename:
            manifest = [m for m in manifest if m.get("filename") != filename and m.get("image") != image_filename]
            manifest.append({
                "filename": filename,
                "image": image_filename,
                "marked_at": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
                "status": "falsealarm",
                "purpose": "model_fine_tuning"
            })
    else:
        # 取消標示誤報：從微調資料夾中移除
        if filename:
            clean_vid = os.path.basename(filename)
            fp_vid = os.path.join(FALSE_POSITIVE_DIR, clean_vid)
            if os.path.exists(fp_vid):
                try:
                    os.remove(fp_vid)
                    removed_files.append(clean_vid)
                except Exception as e:
                    print(f"Error removing {fp_vid}: {e}")

        if image_filename:
            clean_img = os.path.basename(image_filename)
            fp_img = os.path.join(FALSE_POSITIVE_DIR, clean_img)
            if os.path.exists(fp_img):
                try:
                    os.remove(fp_img)
                    removed_files.append(clean_img)
                except Exception as e:
                    print(f"Error removing {fp_img}: {e}")

        manifest = [m for m in manifest if m.get("filename") != filename and m.get("image") != image_filename]

    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error writing manifest: {e}")

    return jsonify({
        "success": True,
        "is_false_alarm": is_false_alarm,
        "copied": copied_files,
        "removed": removed_files,
        "manifest_count": len(manifest)
    })


if __name__ == '__main__':
    # 註冊 Ctrl+C (SIGINT) 與關閉訊號處理常式
    signal.signal(signal.SIGINT, graceful_shutdown)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, graceful_shutdown)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, graceful_shutdown)

    # 啟動背景核心引擎 (讓錄影與 AI 獨立於網頁運作)
    engine_thread = threading.Thread(target=core_monitor_loop, daemon=True)
    engine_thread.start()
    
    print("=" * 60)
    print("輕量化 Edge-Vision 安全防護系統已啟動")
    print("按下 Ctrl + C 即可立即結束程式並釋放所有攝影機資源")
    print("=" * 60)

    try:
        # 啟動 Flask 伺服器
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, threaded=True)
    except (KeyboardInterrupt, SystemExit):
        graceful_shutdown()