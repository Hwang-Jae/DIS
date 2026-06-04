
import { useState, useEffect, useRef } from "react";
import { io } from "socket.io-client";

export default function Dashboard() {
  const socketRef = useRef(null);
  const [tasks, setTasks] = useState({});
  const [logs, setLogs] = useState([]);

  // ✅ 자동 초기 로딩
  useEffect(() => {
    loadTasks();

    socketRef.current = io("http://localhost:5000", {
      transports: ["websocket"]
    });

    socketRef.current.on("progress", (data) => {

      // ✅ task 상태 자동 업데이트
      setTasks(prev => {
        const updated = { ...prev };

        if (!updated[data.task_id]) {
          updated[data.task_id] = {};
        }

        updated[data.task_id] = {
          ...updated[data.task_id],
          progress: data.progress,
          status: "processing"
        };

        return updated;
      });

      setLogs(prev => [
        `[${data.time || ""}] (${data.task_id}) ${data.status}`,
        ...prev
      ]);
    });

    return () => socketRef.current.disconnect();
  }, []);

  // ✅ 초기 조회
  const loadTasks = async () => {
    const res = await fetch("http://localhost:5000/tasks");
    const data = await res.json();
    setTasks(data);
  };

  // ✅ 업로드
  const upload = async (files) => {
    for (let f of files) {
      const fd = new FormData();
      fd.append("file", f);

      await fetch("http://localhost:5000/upload", {
        method: "POST",
        body: fd
      });
    }
  };

  // ✅ 취소
  const cancelTask = async (task_id) => {
    await fetch(`http://localhost:5000/cancel/${task_id}`, {
      method: "POST"
    });
  };

  return (
    <div style={{ padding: 20 }}>

      <input type="file" multiple onChange={(e) => upload(e.target.files)} />

      <h3>📊 실시간 작업 대시보드</h3>

      {Object.entries(tasks).map(([id, t]) => (
        <div key={id} style={{
          border: "1px solid #ccc",
          padding: 10,
          marginBottom: 10
        }}>

          <div><b>ID:</b> {id}</div>
          <div><b>Status:</b> {t.status}</div>

          {/* ✅ progress */}
          <div style={{ background: "#eee", height: 10 }}>
            <div style={{
              width: (t.progress || 0) + "%",
              height: 10,
              background: "green"
            }} />
          </div>

          {/* ✅ 취소 버튼 */}
          {t.status === "processing" && (
            <button onClick={() => cancelTask(id)}>
              ❌ 취소
            </button>
          )}

          {/* ✅ 실패 다운로드 */}
          {t.result?.fail_file && (
            <a href={`http://localhost:5000/download-failed?path=${t.result.fail_file}`}>
              실패 데이터 다운로드
            </a>
          )}

        </div>
      ))}

      <h3>🧾 로그</h3>

      <div style={{
        height: 250,
        overflow: "auto",
        background: "#111",
        color: "#0f0",
        padding: 10
      }}>
        {logs.map((l, i) => (
          <div key={i}>{l}</div>
        ))}
      </div>

    </div>
  );
}
``
