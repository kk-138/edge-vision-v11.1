# ==========================================
# 🛑 必須放在 import ultralytics 之前
# monkey-patch onnxruntime.InferenceSession，
# 強制注入執行緒限制（Ultralytics 內部不開放 sess_options 參數）
# ==========================================
import os
import onnxruntime as ort

_original_init = ort.InferenceSession.__init__


def _make_patched_init(intra_threads: int, inter_threads: int = 1):
    def _patched_init(self, path_or_bytes, sess_options=None, providers=None, **kwargs):
        if sess_options is None:
            sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = intra_threads
        sess_options.inter_op_num_threads = inter_threads
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

        if providers is None:
            providers = ["CPUExecutionProvider"]

        _original_init(self, path_or_bytes, sess_options=sess_options, providers=providers, **kwargs)

    return _patched_init


def limit_onnxruntime_threads(intra_threads: int, inter_threads: int = 1):
    """
    在建立 YOLO() 之前呼叫一次，之後所有 onnxruntime.InferenceSession
    （包含 Ultralytics 內部建立的）都會套用這裡指定的執行緒數。
    """
    ort.InferenceSession.__init__ = _make_patched_init(intra_threads, inter_threads)


from ultralytics import YOLO  # noqa: E402  (故意放在 patch 之後 import)


class FallDetector:
    def __init__(self, model_path="best.onnx"):
        print(f"載入知識蒸餾跌倒偵測模型: {model_path} ...")
        self.model = YOLO(model_path, task="detect")

    def predict(self, frame, conf_thres=0.35):
        """單張畫面推論，回傳格式與原本一致：[[x1,y1,x2,y2,conf,class_name], ...]"""
        return self.predict_batch([frame], conf_thres=conf_thres)[0]

    def predict_batch(self, frames, conf_thres=0.35):
        """
        多張畫面一次推論（batch），回傳長度與 frames 相同的 list，
        每個元素是該畫面對應的 [[x1,y1,x2,y2,conf,class_name], ...]

        用途：多攝影機場景下，把所有鏡頭的畫面一次丟進模型，
        比每支攝影機各自呼叫一次 predict() 更省 CPU
        （底層卷積運算在 batch 矩陣運算上有更好的快取利用率）。
        """
        results = self.model(frames, conf=conf_thres, iou=0.4, verbose=False, agnostic_nms=True)

        batch_boxes = []
        for result in results:
            frame_boxes = []
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = box.conf[0].item()
                cls_id = int(box.cls[0].item())
                class_name = self.model.names[cls_id]
                frame_boxes.append([int(x1), int(y1), int(x2), int(y2), conf, class_name])
            batch_boxes.append(frame_boxes)

        return batch_boxes