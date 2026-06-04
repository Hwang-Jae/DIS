import csv
import io
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import clickhouse_connect

app = FastAPI(
    title="Smart Factory Data Mart API",
    description="클릭하우스 대용량 데이터 마트 조회 및 스트리밍 다운로드 API"
)

# 프론트엔드와 백엔드 포트가 다를 때 발생하는 CORS 문제를 방지하기 위한 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 로컬 테스트용이므로 모두 허용하며, 운영 환경에서는 프론트엔드 도메인만 지정 권장
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ClickHouse 클라이언트 연결 설정 함수
def get_clickhouse_client():
    try:
        # 실제 환경에 맞게 host, port, username, password, database명을 변경하세요.
        return clickhouse_connect.get_client(
            host='localhost',
            port=8123,
            username='default',
            password='clickhouse',
            database='smart_factory'
        )
    except Exception as e:
        print(f"ClickHouse 연결 실패: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")


#def get_db_client():
#    return clickhouse_connect.get_client(
#        host='localhost', port=8123, username='default', password='clickhouse',
#        connect_timeout=30, send_receive_timeout=300
#    )


# API 서버 정상 작동 확인용 헬스체크 엔드포인트
@app.get("/")
async def health_check():
    return {"status": "healthy", "message": "Smart Factory Data Mart API Server is running"}


# [기능 1] 웹 화면 표시용: 최신 샘플 데이터만 제한하여 조회
@app.get("/api/datamart/sample")
async def get_datamart_sample(limit: int = 500):
    client = get_clickhouse_client()
    
    # 100만 건 중 화면 렌더링 부하를 줄이기 위해 상위 일부 데이터만 최신순으로 가져옴
    query = """
        SELECT LOT_ID, EQUIPMENT_CODE, TRAN_TIME, INSP_ITEM_NAME, INSP_VALUE, FINAL_RESULT 
        FROM smart_factory.inspection_data 
        ORDER BY TRAN_TIME DESC 
        LIMIT %(limit)s
    """
    
    try:
        result = client.query(query, parameters={'limit': limit})
        
        # 프론트엔드에서 사용하기 편하도록 JSON 객체(딕셔너리 리스트) 배열로 파싱
        columns = ['lot_id', 'equipment_code', 'tran_time', 'insp_item_name', 'insp_value', 'final_result']
        data = [dict(zip(columns, row)) for row in result.result_rows]
        
        return {
            "status": "success",
            "count": len(data),
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 조회 중 오류 발생: {str(e)}")


# [기능 2] 100만 건 대용량 데이터 처리용: 클릭하우스에서 브라우저로 직접 데이터를 흘려보내는(Streaming) CSV 다운로드
@app.get("/api/datamart/download")
async def download_datamart_csv():
    client = get_clickhouse_client()
    
    # 전체 100만 건 대용량 대상 쿼리
    query = """
        SELECT LOT_ID, EQUIPMENT_CODE, TRAN_TIME, INSP_ITEM_NAME, INSP_VALUE, FINAL_RESULT 
        FROM smart_factory.inspection_data 
        ORDER BY TRAN_TIME DESC
    """
    
    # 서버 메모리 점유율을 늘리지 않고, 데이터를 한 줄씩 읽어 클라이언트에 즉시 전송하는 Generator
    def csv_data_generator():
        # 1. CSV 파일 상단에 들어갈 컬럼명(Header) 설정
        header = ["LOT_ID", "EQUIPMENT_CODE", "TRAN_TIME", "INSP_ITEM_NAME", "INSP_VALUE", "FINAL_RESULT"]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(header)
        yield output.getvalue()
        
        # 버퍼 비우기
        output.seek(0)
        output.truncate(0)
        
        try:
            # 2. query_row_block_stream을 사용하여 클릭하우스가 주는 데이터 블록 단위로 처리
            # 이 방식을 쓰면 100만 건을 조회해도 서버 메모리는 수 MB 수준으로 꽉 잡혀있습니다.
            with client.query_row_block_stream(query) as stream:
                for block in stream:
                    writer.writerows(block)
                    yield output.getvalue()
                    
                    # 메모리 누수 방지를 위해 청크 전송 직후 StringIO 버퍼 초기화
                    output.seek(0)
                    output.truncate(0)
        except Exception as e:
            # 스트리밍 도중 예기치 못한 DB 오류 발생 시 파일 내부에 에러 기록
            yield f"\n[데이터 스트리밍 중 오류가 발생했습니다: {str(e)}]\n"
        finally:
            output.close()

    # StreamingResponse를 사용해 데이터를 다운로드 파일 형태로 응답
    return StreamingResponse(
        csv_data_generator(),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=smart_factory_datamart_all.csv",
            "Cache-Control": "no-cache"
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
# 백엔드 실행 명령어 (터미널 입력용):
# uvicorn main:app --host 0.0.0.0 --port 8000 --reload