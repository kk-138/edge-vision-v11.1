import sys
import sounddevice as sd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("=" * 40)
print("可用音訊設備列表 (Audio Devices)")
print("=" * 40)
print(sd.query_devices())
print("=" * 40)
print("請在上方列表中找到您要使用的 麥克風 (輸入) 與 喇叭 (輸出) 的設備 ID (最前面的數字)。")
print("並將其填入 new_app_with_multicam.py 頂部的：")
print("INTERCOM_MIC_DEVICE = <設備ID>")
print("INTERCOM_SPEAKER_DEVICE = <設備ID>")

