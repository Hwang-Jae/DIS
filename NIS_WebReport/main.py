from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import clickhouse_connect
from pydantic import BaseModel
from typing import Optional
from fastapi.responses import StreamingResponse
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# 컬럼 맵핑 사전
COLUMN_MAP = {
    "로트": "LOT_ID", "로트 아이디": "LOT_ID", "제품": "LOT_ID",
    "설비": "EQUIPMENT_CODE", "설비 코드": "EQUIPMENT_CODE",
    "생산 시간": "TRAN_TIME", "검사 시간": "TRAN_TIME",
    "검사 버전": "INSP_VERSION",
    "검사 항목 명": "INSP_ITEM_NAME",
    "검사 순서": "INSP_ITEM_SEQ",
    "라인 코드": "LINE_CODE",
    "품번 코드": "PRODUCT_CODE", "제품 코드": "PRODUCT_CODE",
    "공정 코드": "OPERATION_CODE",
    "스팩 유형": "SPEC_TYPE",
    "목표치": "TARGET_VALUE",
    "스팩 하한값": "SPEC_MIN_VALUE",
    "스팩 상한값": "SPEC_MAX_VALUE",
    "스팩 단위": "SPEC_UNIT",
    "이상치 유무": "ABNORMAL_FLAG",
    "검사 결과 값": "INSP_VALUE",
    "최종 판정 결과": "FINAL_RESULT", "판정 결과": "FINAL_RESULT",
    "합격": "OK", "불량": "NG"
}

def map_user_query_to_columns(user_input: str):
    mapped_query = user_input
    sorted_keys = sorted(COLUMN_MAP.keys(), key=len, reverse=True)
    for keyword in sorted_keys:
        if keyword in mapped_query:
            mapped_query = mapped_query.replace(keyword, COLUMN_MAP[keyword])
    return mapped_query

class ChatRequest(BaseModel):
    message: str

def get_db_client():
    return clickhouse_connect.get_client(
        host='localhost', port=8123, username='default', password='clickhouse',
        connect_timeout=30, send_receive_timeout=300
    )

@app.get("/api/dashboard")
async def get_dashboard_stats():
    try:
        client = get_db_client()
        status_query = "SELECT FINAL_RESULT, count() as cnt FROM smart_factory.inspection_data GROUP BY FINAL_RESULT"
        status_data = client.query(status_query).result_rows
        
        ok_count, ng_count = 0, 0
        for row in status_data:
            if row[0] == 'OK': ok_count = row[1]
            elif row[0] == 'NG': ng_count = row[1]
            
        trend_query = """
            SELECT toDate(TRAN_TIME) as dt, count() as cnt, sum(FINAL_RESULT='NG') as ng_cnt 
            FROM smart_factory.inspection_data 
            GROUP BY dt ORDER BY dt DESC LIMIT 7
        """
        trend_data = client.query(trend_query).result_rows
        trend_data.reverse()
        
        labels = [str(r[0]) for r in trend_data]
        totals = [r[1] for r in trend_data]
        ngs = [r[2] for r in trend_data]

        return {
            "total": ok_count + ng_count,
            "ok": ok_count, "ng": ng_count,
            "trend": {"labels": labels, "totals": totals, "ngs": ngs}
        }
    except Exception as e:
        logger.error(f"Dashboard Error: {e}")
        return {"error": str(e)}

@app.get("/api/data")
async def get_data(date: Optional[str] = None, lot: Optional[str] = None, result: Optional[str] = None):
    try:
        client = get_db_client()
        query = "SELECT LOT_ID, TRAN_TIME, INSP_ITEM_NAME, INSP_VALUE, FINAL_RESULT FROM smart_factory.inspection_data WHERE 1=1"
        if date: query += f" AND toDate(TRAN_TIME) = '{date}'"
        if lot: query += f" AND LOT_ID LIKE '%{lot}%'"
        if result: query += f" AND FINAL_RESULT = '{result}'"
        query += " ORDER BY TRAN_TIME DESC LIMIT 100"
        result_data = client.query(query)
        return [{"LOT_ID": row[0], "TRAN_TIME": str(row[1]), "INSP_ITEM_NAME": row[2], "INSP_VALUE": row[3], "FINAL_RESULT": row[4]} for row in result_data.result_rows]
    except Exception as e:
        return []

@app.post("/api/chat")
async def chat_with_ai(request: ChatRequest):
    processed_message = map_user_query_to_columns(request.message)
    
    async def generate_response():
        yield json.dumps({"step": f"📍 [의도 분석] 질의 변환: {processed_message}"}) + "\n"
        
        system_prompt = f"""당신은 스마트팩토리 데이터 분석가입니다.
테이블: smart_factory.inspection_data
컬럼: LOT_ID, EQUIPMENT_CODE, TRAN_TIME, FINAL_RESULT, INSP_VALUE, INSP_ITEM_NAME 등

사용자의 질문을 분석하여 어떤 데이터를 조회하고 어떻게 시각화할지 결정하세요.
반드시 아래의 JSON 형식으로만 응답해야 합니다.

{{
    "sql": "SELECT ... LIMIT 50", 
    "type": "table|line|bar|pie",
    "title": "분석 제목",
    "x_axis": "그래프 X축 컬럼명 (table일 경우 생략)",
    "y_axis": "그래프 Y축 컬럼명 (table일 경우 생략)",
    "message": "사용자에게 전달할 한국어 분석 코멘트"
}}
규칙: 
- '추이', '흐름', '시간별' 이면 type을 'line'으로 하세요. (GROUP BY 필요)
- '비교', '빈도', '순위' 이면 type을 'bar'로 하세요.
- 단순 '목록', '조회' 이면 type을 'table'로 하세요.
- sql 쿼리 끝에 세미콜론(;)을 붙이지 마세요.
"""

        try:
            async with httpx.AsyncClient(timeout=300.0) as http_client:
                yield json.dumps({"step": "🧠 [AI 추론] 최적의 시각화 모델 및 쿼리 설계 중..."}) + "\n"
                
                payload = {"model": "gpt-oss:20b", "prompt": f"{system_prompt}\n질문: {processed_message}", "stream": False}
                res = await http_client.post("http://localhost:11434/api/generate", json=payload)
                ai_raw = res.json().get("response", "")
                
                # 정규식(re)을 사용하지 않고 안전하게 JSON 문자열만 추출하여 파싱 에러 방지
                start_idx = ai_raw.find('{')
                end_idx = ai_raw.rfind('}')
                
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = ai_raw[start_idx:end_idx+1]
                    try:
                        ai_intent = json.loads(json_str)
                        raw_sql = ai_intent.get("sql", "").strip().replace(';', '')
                        
                        # 강제 LIMIT 적용 (문자열 탐색 방식 적용)
                        if "LIMIT" not in raw_sql.upper():
                            raw_sql += " LIMIT 50"

                        chart_type = ai_intent.get("type", "table")
                        msg = ai_intent.get("message", "분석이 완료되었습니다.")
                        x_axis = ai_intent.get("x_axis", "")
                        y_axis = ai_intent.get("y_axis", "")
                        
                        yield json.dumps({"step": f"🗄️ [DB 실행] 쿼리 실행: {raw_sql[:50]}..."}) + "\n"
                        
                        client = get_db_client()
                        result = client.query(raw_sql)
                        rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
                        
                        yield json.dumps({"step": f"📊 [시각화 렌더링] {len(rows)}건 데이터 기반 {chart_type} 생성 중..."}) + "\n"
                        
                        response_payload = {
                            "response_type": chart_type,
                            "data": rows,
                            "message": msg,
                            "x_axis": x_axis,
                            "y_axis": y_axis
                        }
                        
                        # default=str 옵션을 추가하여 datetime 객체를 문자열로 안전하게 변환
                        yield json.dumps({"step": "✅ 완료", "final_data": response_payload}, default=str, ensure_ascii=False) + "\n"
                        
                    except json.JSONDecodeError:
                        yield json.dumps({"step": f"⚠️ [JSON 파싱 에러] AI 응답 형식이 올바르지 않습니다."}) + "\n"
                else:
                    yield json.dumps({"step": f"⚠️ [분석 실패] AI가 규격에 맞는 답변을 생성하지 못했습니다.\n원문: {ai_raw[:100]}"}) + "\n"
        except Exception as e:
            yield json.dumps({"step": f"❌ [시스템 에러] {str(e)}"}) + "\n"

    return StreamingResponse(generate_response(), media_type="application/x-ndjson")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)