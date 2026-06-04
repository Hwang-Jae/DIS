
import pandas as pd
import clickhouse_connect
import hashlib
import time
import os


def load_xlsb_to_clickhouse(file_path, send_progress):
    def log(p, msg):
        send_progress({
            "progress": p,
            "status": msg,
            "time": time.strftime("%H:%M:%S")
        })

    try:
        client = clickhouse_connect.get_client(
            host='localhost',
            port=8123,
            username='default',
            password='clickhouse'
        )

        staging_path = file_path.replace("raw", "staging").replace(".xlsb", ".csv")
        os.makedirs(os.path.dirname(staging_path), exist_ok=True)

        # ✅ 1. XLSB → CSV
        log(5, "XLSB → CSV 변환 시작")
        df = pd.read_excel(file_path, engine='pyxlsb', dtype=str)
        df.to_csv(staging_path, index=False)
        del df
        log(10, "CSV 변환 완료")

        # ✅ 테이블 컬럼 조회
        table_info = client.query("DESCRIBE TABLE smart_factory.inspection_data")
        db_columns = [row[0] for row in table_info.result_rows]

        total_inserted = 0
        failed_rows = []
        batch_size = 20000
        version = int(time.time())

        min_time, max_time = None, None

        # ✅ 2. CSV chunk 처리
        for chunk_idx, df in enumerate(pd.read_csv(
                staging_path,
                chunksize=20000,
                dtype=str,
                low_memory=False
        )):

            log(10 + chunk_idx, f"chunk {chunk_idx+1} 처리중")

            df.columns = df.columns.str.strip()
            df = df[[c for c in df.columns if c in db_columns]]

            # ✅ ✅ ✅ [핵심 1] TRAN_TIME 처리
            if 'TRAN_TIME' in df.columns:
                df['TRAN_TIME'] = pd.to_datetime(df['TRAN_TIME'], errors='coerce')
                df['TRAN_TIME'] = df['TRAN_TIME'].fillna(pd.Timestamp("1970-01-01"))

                min_time = df['TRAN_TIME'].min() if min_time is None else min(min_time, df['TRAN_TIME'].min())
                max_time = df['TRAN_TIME'].max() if max_time is None else max(max_time, df['TRAN_TIME'].max())

            # ✅ ✅ ✅ [핵심 2] 문자열 변환
            df = df.fillna("").astype(str)

            # ✅ ✅ ✅ [핵심 3] hash 생성
            df["row_hash"] = (
                df.agg("|".join, axis=1)
                .map(lambda x: hashlib.md5(x.encode()).hexdigest())
            )

            df["version"] = version

            # ✅ ✅ ✅ [핵심 4] 숫자 컬럼 복원
            numeric_cols = [
                "INSP_ITEM_SEQ",
                "VALUE_SEQ",
                "VALUE_COUNT",
                "TARGET_VALUE",
                "SPEC_MIN_VALUE",
                "SPEC_MAX_VALUE",
                "CTRL_MIN_VALUE",
                "CTRL_MAX_VALUE",
                "INSP_VALUE"
            ]

            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

                    if col == "INSP_VALUE":
                        df[col] = df[col].astype(float)
                    else:
                        df[col] = df[col].astype(int)

            # ✅ ✅ ✅ [핵심 5] datetime 복원
            if 'TRAN_TIME' in df.columns:
                df['TRAN_TIME'] = pd.to_datetime(df['TRAN_TIME'], errors='coerce')

            data = df.values.tolist()
            cols = list(df.columns)

            # ✅ insert
            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]

                try:
                    client.insert(
                        'smart_factory.inspection_data',
                        batch,
                        column_names=cols
                    )
                    total_inserted += len(batch)

                except Exception:
                    failed_rows.extend(batch)

                    continue

                prog = min(99, int(total_inserted / (total_inserted + 1) * 100))
                log(prog, f"{total_inserted:,}건 적재중")

        # ✅ 실패 파일 저장
        fail_path = file_path.replace("raw", "failed").replace(".xlsb", ".csv")

        if failed_rows:
            os.makedirs(os.path.dirname(fail_path), exist_ok=True)
            pd.DataFrame(failed_rows, columns=cols).to_csv(fail_path, index=False)

        log(100, "완료 ✅")


        
        # ✅ 업로드 히스토리 저장
        
        from datetime import datetime
        
        min_time = pd.to_datetime(min_time)
        max_time = pd.to_datetime(max_time)
        
        client.insert(
            "smart_factory.upload_history",
            [[
                os.path.basename(file_path),
                datetime.now(),
                int(total_inserted),
                min_time,
                max_time
            ]],
            column_names=[
                "file_name",
                "upload_time",
                "row_count",
                "min_tran_time",
                "max_tran_time"
            ]
        )
        


        return {
            "success": True,
            "count": total_inserted,
            "fail_file": fail_path if failed_rows else None
        }

    except Exception as e:
        log(0, f"❌ 오류: {str(e)}")
        return {"success": False}
