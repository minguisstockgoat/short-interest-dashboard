# 국내 공매도 잔고 대시보드

**https://minguisstockgoat.github.io/short-interest-dashboard/**

시총 1조원 이상 개별 보통주(272종목)의 공매도 순보유잔고·증감·상장/유동주식수 대비 비율을
한 화면에 나열하고, 종목 클릭 시 과거 잔고비율 추이를 보여준다.
공시 시차(T+2) 구간은 종목별 회귀로 추정한다.

> 시장 데이터를 참고용으로 정리한 개인 프로젝트입니다. 투자 판단의 근거로 쓰기 위한
> 것이 아니며, 원본 데이터의 정확성을 보증하지 않습니다.

## 실행

```powershell
# 대시보드 로컬 보기
powershell -ExecutionPolicy Bypass -File .\serve.ps1     # → http://127.0.0.1:8765/

# 데이터 갱신 (KRX 공매도만 로그인 필요)
powershell -ExecutionPolicy Bypass -File .\launch_chrome.ps1   # 크롬 띄우고 직접 로그인
powershell -ExecutionPolicy Bypass -File .\update.ps1

# KRX가 차단 중이거나 로그인이 안 됐으면 나머지만 갱신
powershell -ExecutionPolicy Bypass -File .\update.ps1 -SkipKrxShort
```

## 자동 갱신 (평일 18:30)

```powershell
powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1              # 등록
powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1 -Time 20:00  # 시각 변경
powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1 -Uninstall   # 해제
```

작업 스케줄러가 `daily.ps1` 을 실행한다 → `update.ps1` 로 갱신 → 산출물 검증 →
`docs/` 변경분 커밋·푸시 → GitHub Pages 자동 재배포. 로그는 `logs/daily_*.log`(30일 보관).

**GitHub Actions로는 못 한다.** 공매도 잔고·거래량이 KRX 로그인 세션을 요구하는데
Actions는 로그인할 수 없고, 데이터센터 IP는 KRX가 차단한다. 그래서 PC의 작업 스케줄러를 쓴다.
크롬이 로그인 상태로 떠 있지 않으면 `daily.ps1` 이 자동으로 `-SkipKrxShort` 로 넘어가
시세·유동주식수·대차잔고만 갱신하고 로그에 남긴다(공매도는 직전 값 유지).

`.ps1` 파일은 **UTF-8 BOM**으로 저장해야 한다. Windows PowerShell 5.1은 BOM이 없으면
ANSI로 읽어 한글이 깨지고 따옴표 짝이 어긋나 파싱 오류가 난다 → `scripts/fix_ps1_bom.py`.

## 추정 모델

공매도 순보유잔고는 **T+2 시차**로 공시되므로 D일 시점의 확정치는 D-2까지다.
미공시 구간을 관측 가능한 두 동인으로 채운다.

```
ΔBal(t) = α · ΔLoan(t) + β · ShortVol(t) + ε(t)

Est(D) = Bal(D-2) + Σ_{t∈{D-1, D}} [ α·ΔLoan(t) + β·ShortVol(t) ]
```

- `ΔBal` 공매도잔고 증감(주), `ΔLoan` 대차잔고 증감(주), `ShortVol` 공매도 거래량(주)
- 세 변수 모두 **주식 수 단위**라 단위 정합적이다.
- α·β는 **종목별 최근 60거래일(최소 12)** 실제 잔고 증감에 대해 **절편 없는 OLS**로 매일 재추정.
- 표본 부족·설명력 부족(R² < 0.05) 종목은 **유니버스 풀링 회귀** 계수로 폴백(`source=pooled`).
- 경제적으로 α, β ∈ [0,1]이 자연스러워 추정에는 클리핑값을 쓰고 원값(`alpha_raw`/`beta_raw`)도 보존.

## 데이터 소스

| 항목 | 소스 | 비고 |
|---|---|---|
| 종가·거래량·시가총액·**상장주식수** | KRX OPEN API (`data-dbg.krx.co.kr`) | `KRX_API_KEY` |
| 종목구분(보통주/우선주/스팩) | KRX OPEN API 종목기본정보 | 유니버스 필터 |
| **유동주식수·유동비율** | FnGuide Company Guide Snapshot | 7일 캐시 |
| **공매도 순보유잔고** | KRX 정보데이터시스템 `MDCSTAT30501` | 로그인 필요, T+2 |
| **공매도 거래량** | KRX 정보데이터시스템 `MDCSTAT30101` | 로그인 필요 |
| **대차잔고(종목별)** | 금융투자협회 FreeSIS `STATSCU0100000140` | **로그인 불필요**, D일까지 |

### 대차잔고 (KOFIA FreeSIS)

KRX의 대차 화면은 SPA 내부 라우팅이라 자동 수집이 어렵지만, 금융투자협회 FreeSIS가
같은 데이터를 **인증 없는 순수 JSON API**로 제공하고 KRX보다 하루 빠르다.

```
POST https://freesis.kofia.or.kr/meta/getMetaDataList.do
{"dmSearch":{"tmpV1":"D","tmpV45":"<시작>","tmpV46":"<종료>",
             "tmpV72":"<종목코드6자리>","OBJ_NM":"STATSCU0100000140BO"}}
→ ds1: TMPV1 일자 / TMPV2 종목명 / TMPV3 대차체결 / TMPV4 대차상환
        TMPV5 대차잔고(주) / TMPV6 잔고금액(백만원)
```

종목당 1회 요청으로 기간 전체를 받는다(272종목 ≈ 100초). 화면의 종목 검색 UI는
동작하지 않지만 API는 6자리 코드를 그대로 받는다. 응답 말미의 `합계` 행은 걸러낸다.

## KRX 접근 방식

`data.krx.co.kr`은 로그인 세션이 있어야 데이터를 준다(미로그인 시 `LOGOUT` 응답).
비밀번호를 코드가 다루지 않도록, **사용자가 크롬에서 직접 로그인**하고
스크립트는 CDP(원격 디버깅 9222)로 세션 쿠키만 빌려 쓴다 → `scripts/krx_session.py`.

> ⚠️ **레이트리밋 주의.** KRX는 짧은 시간에 요청이 몰리면 엣지단에서 IP를 차단하며
> (전 도메인 403, OPEN API 포함) 수 시간 지속된다. `krx_short.py`는 전역 0.7초 간격,
> 워커 2개가 기본값이다. 403을 만나면 즉시 중단하고 재시도하지 말 것.
> 이미 받은 분량은 `py scripts/krx_short.py --from-cache` 로 네트워크 없이 복원된다.

## 파일

```
scripts/
  common.py          경로·유니버스 공통
  krx_open.py        OPEN API 시세/상장주식수 수집
  build_master.py    종목기본정보 결합 → 보통주·시총 필터 → universe.csv
  fnguide_float.py   FnGuide 유동주식수 수집
  krx_session.py     크롬(CDP) 로그인 세션 대여
  krx_short.py       공매도 잔고·거래량 수집 (--from-cache 복원 지원)
  estimate.py        α·β 회귀 + D일 추정잔고
  build_dashboard.py web/dashboard_data.json 생성
  cdp_capture.py     KRX 화면의 bld/파라미터 캡처 (신규 화면 추가용)
  cdp_listen.py      수동 조작 대기형 캡처
  scan_secrets.py    공개 저장소 업로드 전 민감정보 점검
  fix_ps1_bom.py     .ps1 파일 UTF-8 BOM 보정
  coverage.py        거래일 대비 수집 커버리지·결측 구간 점검
docs/                GitHub Pages 게시 대상
  index.html         대시보드 (랭킹 테이블 + 종목별 추이 차트)
  dashboard_data.json
  robots.txt         검색엔진 색인 차단
data/
  prices.csv  master.csv  universe.csv  free_float.csv
  short_balance.csv  short_volume.csv  short_panel.csv
  short_coef.csv  short_estimate.csv
  raw/               원본 캐시 (재수집 없이 복원 가능)
```
