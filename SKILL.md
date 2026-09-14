# SKILL — python-airkorea-api 에이전트 매뉴얼

> 이 파일은 당신(AI 에이전트)이 python-airkorea-api 프로젝트에서 작업을 시작하기 전 반드시 읽어야 한다.
> 1회만 읽으면 잘못된 좌표계 변환이나 불필요한 구현 오류로 인한 30분 이상의 삽질을 방지할 수 있다.

---

## 1. 정체성

이 저장소(Python 패키지 이름 `airkorea`, GitHub 저장소 `python-airkorea-api`)는 한국환경공단 AirKorea OpenAPI(공공데이터포털 B552584)를 Python 3.10+ 환경에서 효율적으로 호출할 수 있도록 돕는 **비공식 API 클라이언트 라이브러리**다. 
downstream 서비스가 직접 안정적으로 사용할 수 있는 비동기 전용 HTTP 클라이언트, Pydantic 모델, 좌표계 변환 기능을 제공한다.

### 식별자 매핑

| 항목 | 값 |
|------|----|
| GitHub 저장소 | `python-airkorea-api` |
| Python 패키지 | `airkorea` |
| import 이름 | `import airkorea` 또는 `from airkorea.client import AirKoreaClient` |
| 핵심 의존성 | `pydantic>=2.0`, `pyproj>=3.0`, `httpx>=0.24` |
| 지원 Python 버전 | `Python >= 3.10` |

### 개발 환경

- 가상환경(`.venv`) 사용을 강력히 권장합니다.
- 기본 테스트는 외부 네트워크 호출이 없이 로컬 fixture와 mock session으로 신속하게 동작해야 합니다.
- 실제 공공데이터포털 API를 연동하여 확인하는 테스트는 `@pytest.mark.integration` 마커를 통해 Opt-in 형태로 분리되어 작동합니다.

---

## 2. 빠른 시작

```bash
# 가상환경 활성화 (Windows PowerShell 예시)
.\.venv\Scripts\Activate.ps1

# 품질 게이트 (PR 푸시 전 반드시 로컬에서 수행하여 검증할 것)
python -m compileall src/airkorea tests   # 정적 구문 오류 검사
python -m pytest                           # 전체 단위 테스트 실행
python -m pytest --cov=airkorea --cov-fail-under=90  # 테스트 커버리지 검증
python -m ruff check .                    # ruff를 이용한 린트 검사
python -m mypy src/airkorea               # mypy 정적 타입 검사

# 실제 연동 테스트 (인증키 디코딩 원본 입력)
$env:DATA_GO_KR_SERVICE_KEY="YOUR_DECODED_KEY"
python -m pytest -m integration
```

---

## 3. 디렉토리 지도

```
src/airkorea/
  client.py           — public client (AirKoreaClient), base URL, endpoint 목록 및 편리 메서드
  models.py           — public Pydantic 응답 모델 및 raw page 래퍼
  _http.py            — HTTP 호출, retry, resultCode 예외 매핑 및 exchange 로깅
  _convert.py         — 결측치(None), 문자열, 숫자, 날짜 정규화 및 변환 helper
  codes.py            — enum(SidoName, Pollutant, DataTerm 등), 라벨 및 입력 유효성 검증
  coords.py           — WGS84 좌표 ⇄ AirKorea TM 좌표 정밀 변환
  metadata.py         — 인증키 마스킹, 호출 context 및 캐시 제어
  pagination.py       — pageNo/numOfRows 기반 페이지네이션 순회 helper
  cli.py              — CLI 명령 인터페이스 진입점
tests/
  conftest.py         — fake session fixture 및 mock setup
  test_client.py      — 클라이언트 메서드 동작 단위 테스트
  test_coords.py      — 좌표 변환 정밀도 및 타입 검증 테스트
  test_expanded_api.py — 추가된 대기오염 및 예보 정보 API 테스트
  test_http.py        — retry, 예외 처리, exchange 단위 테스트
  test_live_api.py    — Opt-in integration live test
docs/                 — decisions, journal, tasks, resume 등 에이전트 문서
```

---

## 4. 절대 하지 말 것 (DO NOT)

1. **`main` 브랜치 직접 푸시 금지**: 반드시 작업 브랜치(`chore/` 또는 `feat/`)를 분기하여 PR을 생성한 후 검증하여 병합하십시오.
2. **실제 공공데이터포털 서비스키 평문 노출 금지**: 코드, fixture, 커밋 로그, 문서, issue 등에 실서비스키를 날것으로 노출해서는 절대 안 됩니다. 반드시 환경변수 `DATA_GO_KR_SERVICE_KEY`를 활용해 마스킹 처리하십시오.
3. **결측값 0 강제 형변환 금지**: AirKorea API 응답 중 결측값(`-`, 빈 문자열, `null`, `none`, `nan`)은 무조건 Python `None`으로 정규화 처리해야 합니다. 0으로 변환할 경우 실제 측정값 0(오염 물질 없음)과 섞여 통계 왜곡을 일으킵니다.
4. **WGS84와 TM 좌표계 순서 혼동 금지**:
   - public WGS84 경위도 좌표는 무조건 `LatLon(lat, lon)` (위도, 경도) 순서입니다.
   - AirKorea TM 평면 좌표는 무조건 `TmPoint(tm_x, tm_y)` (X축, Y축) 순서입니다.
5. **공식 API 철자 오타 임의 수정 금지**:
   - `getCtprvnMesureLIst`, `getCtprvnMesureSidoLIst`의 `LIst` 철자를 임의로 고치지 마십시오.
   - 월평균 endpoint인 `getMsrstnAcctoRMmrg`를 `getMsrstnAcctoRmmrg`로 바꾸지 마십시오.
6. **resultCode 실패 무시 금지**: HTTP 응답 코드가 200 OK일지라도 response body 내의 `resultCode`가 `00`이 아니면, 반드시 알맞은 typed exception(`AirKoreaResponseError` 등)으로 변환해 throw 해야 합니다.
7. **Pydantic 응답 모델 raw 정보 드롭 금지**: 신규 응답 스키마가 불확실하면 확인된 주요 필드만 Pydantic 모델로 파싱하되, `raw: dict[str, Any]` 필드를 보존하여 다운스트림이 raw 응답에 원본 접근할 수 있게 열어두어야 합니다.

---

## 5. 자주 묻는 작업

| 작업 | 시작 파일 |
|------|-----------|
| **신규 API endpoint 추가** | `src/airkorea/client.py` (`SUPPORTED_ENDPOINTS` 매핑 등록) 및 `src/airkorea/client.py`에 convenience method 작성 |
| **신규 응답 모델 추가** | `src/airkorea/models.py`에 Pydantic 모델 정의 및 `raw` 필드 보존 처리 |
| **새 좌표계 변환 로직** | `src/airkorea/coords.py` 에 pyproj 연산 추가 |
| **결측값/포맷 변환 확장** | `src/airkorea/_convert.py`에 정규화 도구 추가 및 테스트 검증 |
| **CLI 명령 추가 및 개선** | `src/airkorea/cli.py` 에 Click 명령어 등록 및 parameter 매핑 처리 |

---

## 6. 도메인 어휘

| 약어 / 용어 | 의미 |
|------|------|
| **AirKorea** | 한국환경공단이 운영하는 전국 실시간 대기오염도 공개 웹사이트 및 OpenAPI 서비스군 |
| **B552584** | 공공데이터포털에 등록된 AirKorea 실시간 대기오염정보 서비스 고유 분류 키 |
| **resultCode** | AirKorea API 응답 body에 실려오는 처리 코드. `00`이 성공이며, 그 외 코드는 에러 상황임 |
| **SidoName** | 시도 이름 코드 enum. 서울, 부산, 대구, 인천, 광주, 대전, 울산, 경기, 강원, 충북, 충남, 전북, 전남, 경북, 경남, 제주, 세종, 전국 지원 |
| **LatLon** | WGS84 위경도 좌표를 표현하는 불변 객체. `lat` (위도), `lon` (경도) 순서 |
| **TmPoint** | 중부원점(TM) 기준 평면 직각좌표계를 표현하는 불변 객체. `tm_x`, `tm_y` 순서 |

---

## 7. 작업 후 체크리스트

작업 브랜치를 PR을 통해 병합하고 푸시하기 전 아래 체크리스트를 순서대로 확인하십시오.

- [ ] `python -m compileall src/airkorea tests` 실행 및 구문 오류 없음 확인
- [ ] `python -m pytest` 실행 및 로컬 단위 테스트 100% 통과 확인
- [ ] `python -m pytest --cov=airkorea --cov-fail-under=90` 실행 및 테스트 커버리지 90% 이상 유지 확인
- [ ] `python -m ruff check .` 실행 및 린트 경고 없음 확인
- [ ] `python -m mypy src/airkorea` 실행 및 정적 타입 검사 오류 없음 확인
- [ ] `docs/journal.md`에 작업 완료 내역을 시간 역순으로 기록 완료
- [ ] `docs/tasks.md`에 관련된 태스크 상태 및 진행 여부를 성실히 업데이트 완료
- [ ] 만일 중대한 구조적 결정이 있었다면 `docs/decisions.md`에 ADR(Architectural Decision Record) 신규 작성 완료
- [ ] 사용자용 가시 변경이 포함된 경우 `CHANGELOG.md`에 상세 내역 반영 완료
