
from queue import Queue
import threading

task_queue = Queue()
task_status = {}
task_progress = {}
task_result = {}
task_cancel_flag = {}

socketio_instance = None


def set_socketio(sio):
    global socketio_instance
    socketio_instance = sio


def worker():
    from upload_xlsb_to_clickhouse import load_xlsb_to_clickhouse

    while True:
        job = task_queue.get()

        task_id = job["task_id"]
        file_path = job["file"]

        task_status[task_id] = "processing"
        task_progress[task_id] = 0
        task_cancel_flag[task_id] = False

        def send_progress(data):
            data["task_id"] = task_id

            if task_cancel_flag.get(task_id):
                raise Exception("취소됨")

            task_progress[task_id] = data.get("progress", 0)

            print("📡 SEND:", data)

            if socketio_instance:
                socketio_instance.emit("progress", data)

        try:
            result = load_xlsb_to_clickhouse(file_path, send_progress)

            task_status[task_id] = "done"
            task_result[task_id] = result

        except Exception:
            task_status[task_id] = "cancelled"

        task_queue.task_done()


def start_worker():
    print("🚀 Worker 시작됨")
    t = threading.Thread(target=worker, daemon=True)
    t.start()

