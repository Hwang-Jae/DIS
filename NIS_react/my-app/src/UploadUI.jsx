
import { useState, useEffect, useRef } from "react";
import { io } from "socket.io-client";

export default function Dashboard() {
  const socketRef = useRef(null);

  const [tasks, setTasks] = useState({});
  const [logs, setLogs] = useState([]);
  const [filter, setFilter] = useState("all");

  const [history, setHistory] = useState([]);

  useEffect(() => {
    loadTasks();

    loadHistory();

    socketRef.current = io("http://localhost:5000", {
      transports: ["websocket"]
    });

    socketRef.current.on("connect", () => {
      console.log("✅ WebSocket 연결됨");
    });

    socketRef.current.on("progress", (data) => {
      console.log("📡 수신:", data);

      // ✅ task 업데이트
      setTasks(prev => {
        const updated = { ...prev };

        if (!updated[data.task_id]) {
          updated[data.task_id] = {};
        }

        updated[data.task_id] = {
          ...updated[data.task_id],
          progress: data.progress,
          status: data.progress === 100 ? "done" : "processing"
        };

        return updated;
      });

      // ✅ 로그 추가
      setLogs(prev => [
        `[${data.time}] (${data.task_id}) ${data.status}`,
        ...prev
      ]);
    });

    return () => socketRef.current.disconnect();
  }, []);

  
  const fileInputRef = useRef();

  const startUpload = async () => {
    const files = fileInputRef.current.files;

    if (!files || files.length === 0) {
      alert("파일 선택하세요");
      return;
    }

    console.log("업로드 시작:", files);

    for (let file of files) {
      const fd = new FormData();
      fd.append("file", file);

      await fetch("http://localhost:5000/upload", {
        method: "POST",
        body: fd
      });
    }
  };

  
  const loadHistory = async () => {
    const res = await fetch("http://localhost:5000/history");
    const data = await res.json();
    setHistory(data);
  };



  const loadTasks = async () => {
    const res = await fetch("http://localhost:5000/tasks");
    const data = await res.json();
    setTasks(data);
  };

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

  const cancelTask = async (task_id) => {
    await fetch(`http://localhost:5000/cancel/${task_id}`, {
      method: "POST"
    });
  };

  // ✅ 필터 적용
  const filteredTasks = Object.entries(tasks).filter(([id, t]) => {
    if (filter === "all") return true;
    return t.status === filter;
  });

  return (
    <div style={{ padding: 20}}>

      <h2>📊 실시간 업로드 대시보드</h2>

      {/* ✅ 업로드 */}
      <input type="file" multiple onChange={(e) => upload(e.target.files)} />

      {/* ✅ 필터 */}
      <div style={{ marginTop: 10 }}>
        <button onClick={() => setFilter("all")}>전체</button>
        <button onClick={() => setFilter("processing")}>처리중</button>
        <button onClick={() => setFilter("done")}>완료</button>
        <button onClick={() => setFilter("cancelled")}>취소</button>
      </div>

      {/* ✅ 작업 리스트 */}
      <h3 style={{ marginTop: 20 }}>📁 작업 목록</h3>

      {filteredTasks.map(([id, t]) => (

        <div key={id} style={{
          border: "1px solid #ddd",
          padding: 12,
          marginBottom: 10,
          borderRadius: 5
        }}>

          <div><b>ID:</b> {id}</div>
          <div><b>Status:</b> {t.status}</div>

          {/* ✅ 애니메이션 progress */}
          <div style={{
            background: "#eee",
            height: 12,
            borderRadius: 6,
            overflow: "hidden",
            marginTop: 5
          }}>
            <div style={{
              width: `${t.progress || 0}%`,
              height: 12,
              background: t.progress === 100 ? "#2ecc71" : "#3498db",
              transition: "width 0.5s ease"
            }} />
          </div>

          {/* ✅ 취소 버튼 */}
          {t.status === "processing" && (
            <button
              style={{ marginTop: 5, background: "red", color: "white" }}
              onClick={() => cancelTask(id)}
            >
              ❌ 취소
            </button>
          )}

          {/* ✅ 실패 다운로드 버튼 */}
          {t.result?.fail_file && (
            <button
              style={{ marginTop: 5 }}
              onClick={() => {
                window.location.href =
                  `http://localhost:5000/download-failed?path=${t.result.fail_file}`;
              }}
            >
              ⬇ 실패데이터 다운로드
            </button>
          )}

        </div>
      ))}

      {/* ✅ 로그 */}
      <h3 style={{ marginTop: 20 }}>🧾 실시간 로그</h3>

      <div style={{
        height: 250,
        overflow: "auto",
        background: "#111",
        color: "#0f0",
        padding: 10,
        fontFamily: "monospace"
      }}>
        {logs.map((log, i) => (
          <div key={i}>{log}</div>
        ))}
      </div>

    </div>
  );
}
