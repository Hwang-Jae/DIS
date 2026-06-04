import subprocess
import time
import sys

def run_servers():
    print("🚀 스마트 마트 백엔드 서버 통합 실행 중...")
    
    # 두 개의 백엔드 서버를 백그라운드 프로세스로 실행
    main_process = subprocess.Popen([sys.executable, "main.py"])
    mart_process = subprocess.Popen([sys.executable, "main_mart.py"])
    
    print("✅ main.py (Port 8000) 가동 중")
    print("✅ main_mart.py (Port 8001) 가동 중")
    print("종료하려면 현재 터미널에서 [Ctrl + C]를 누르세요.\n")
    
    try:
        # 서버들이 꺼지지 않고 계속 유지되도록 대기
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 서버 종료 신호를 감지했습니다. 백엔드를 안전하게 종료합니다.")
        main_process.terminate()
        mart_process.terminate()
        print("👋 모든 서버가 정상 종료되었습니다.")

if __name__ == "__main__":
    run_servers()