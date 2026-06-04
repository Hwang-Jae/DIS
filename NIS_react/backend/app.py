
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_socketio import SocketIO
import os, time, uuid

from queue_manager import (
    task_queue, task_status,
    task_progress, task_result,
    task_cancel_flag, start_worker, set_socketio
)

app = Flask(__name__)
CORS(app)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading"
)


# ✅ 추가 (핵심🔥)
set_socketio(socketio)

# ✅ worker 실행
start_worker()


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files['file']

    date_str = time.strftime("%Y-%m-%d")
    raw_dir = f"data_lake/raw/{date_str}"
    os.makedirs(raw_dir, exist_ok=True)

    file_path = f"{raw_dir}/{file.filename}"
    file.save(file_path)

    task_id = str(uuid.uuid4())

    task_status[task_id] = "waiting"

    task_queue.put({
        "task_id": task_id,
        "file": file_path
    })

    print("✅ 큐 등록됨:", task_id)  # ✅ 디버그 추가

    return jsonify({
        "task_id": task_id,
        "message": "작업 큐 등록 완료"
    })


@app.route("/download-failed")
def download_failed():
    path = request.args.get("path")

    if not os.path.exists(path):
        return jsonify({"error": "파일 없음"})

    return send_file(path, as_attachment=True)


@app.route("/tasks")
def get_tasks():
    data = {}

    for task_id in task_status:
        data[task_id] = {
            "status": task_status[task_id],
            "progress": task_progress.get(task_id, 0),
            "result": task_result.get(task_id)
        }

    return jsonify(data)


@app.route("/cancel/<task_id>", methods=["POST"])
def cancel(task_id):
    if task_id in task_cancel_flag:
        task_cancel_flag[task_id] = True
        return jsonify({"message": "취소 요청됨"})

    return jsonify({"error": "task 없음"})


@app.route("/history")
def history():
    import clickhouse_connect

    client = clickhouse_connect.get_client(
        host='localhost',
        port=8123,
        username='default',
        password='clickhouse'
    )

    result = client.query("""
        SELECT
            file_name,
            upload_time,
            row_count,
            min_tran_time,
            max_tran_time
        FROM smart_factory.upload_history
        ORDER BY upload_time DESC
        LIMIT 100
    """)

    return jsonify(result.result_rows)



if __name__ == "__main__":
    socketio.run(app, port=5000, debug=True)
