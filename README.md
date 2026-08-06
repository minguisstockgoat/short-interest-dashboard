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

## 자동 갱신

갱신 로직은 `scripts/pipeline.py` 하나에 있고 Windows·macOS 공통이다.
플랫폼별 스크립트는 얇은 래퍼일 뿐이다.

```
pipeline.py: 시세 → 유니버스 → 유동주식수 → 대차잔고 → 공매도
             → 커버리지 점검 → 회귀 추정 → 대시보드 JSON → (--deploy) 커밋·푸시
```

### macOS (상시 구동 맥미니 — 기본 운영 환경)

```bash
bash mac/setup.sh                    # 가상환경 + 의존성 + .env 생성
tar -xzf bootstrap_data.tar.gz       # Windows에서 만든 데이터 이관 (재수집 회피)
.venv/bin/python scripts/notify.py           # 텔레그램 알림 도착 확인
.venv/bin/python scripts/krx_login.py --dry-run   # 로그인 폼 인식만 확인
.venv/bin/python scripts/krx_login.py             # 실제 로그인 1회
bash mac/doctor.sh                   # 환경 점검
bash mac/daily.sh                    # 수동 1회
bash mac/install_schedule.sh         # 평일 22:00 등록 (시각 변경: 20 00)
bash mac/install_schedule.sh --uninstall
```

`install_schedule.sh` 는 launchd 작업 **세 개**를 등록한다.

| 라벨 | 성격 | 하는 일 |
|---|---|---|
| `com.shortdashboard.daily` | 평일 22:00 1회 | 갱신 + 커밋·푸시 |
| `com.shortdashboard.keepalive` | 상주 | 20분마다 KRX 세션 연장·재로그인 |
| `com.shortdashboard.agent` | 상주 | 대시보드 '수동 갱신' 버튼 수신 (127.0.0.1:8776) |

launchd는 cron과 달리 맥이 잠들어 있던 시간대의 작업을 깨어난 직후 실행하고,
상주 작업은 죽으면 자동으로 다시 띄운다.

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1              # 평일 22:00
powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1 -Time 20:00
powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1 -Uninstall
```

### GitHub Actions로는 못 한다

공매도 잔고·거래량이 KRX 로그인 세션을 요구하는데 Actions는 로그인할 수 없고,
데이터센터 IP는 KRX가 차단한다. 그래서 상시 구동 머신의 스케줄러를 쓴다.

## KRX 로그인 (네이버 SSO — 사람이 한 번, 이후 자동)

공매도 단계만 로그인 세션이 필요하다. KRX 로그인은 **네이버 계정 SSO** 라서
코드가 아이디/비밀번호를 대신 넣지 않는다(네이버가 캡차·기기등록·2단계인증을
걸기 때문에 자동 입력은 실패하거나 계정을 위험 상태로 만든다).
그래서 이 저장소는 **KRX 비밀번호를 저장하지 않는다.**

대신 전용 크롬 프로필(`.chrome-profile`)에 남는 쿠키를 세션의 근거로 쓴다.

```bash
bash mac/launch_chrome.sh          # 전용 프로필 크롬을 로그인 페이지로 띄운다
                                   #   → 열린 창에서 네이버로 KRX 로그인 (사람이 1회)
.venv/bin/python scripts/krx_login.py --status   # 세션 확인
```

한 번 로그인하면 쿠키가 프로필 디스크에 남으므로 크롬을 껐다 켜도 유지된다.
`krx_session.py` 가 CDP(`Network.getAllCookies`)로 `JSESSIONID` 를 포함한 쿠키를
읽어 `requests.Session` 에 실어주고, 이후 수집은 순수 파이썬으로 돈다.

`krx_keepalive.py` 가 20분마다 가벼운 조회를 던져 세션을 연장한다. 그래도
만료되면 `krx_login.py` 가

- 크롬이 꺼져 있으면 먼저 띄워 **프로필 쿠키로 세션 복구**를 시도하고,
- 그래도 없으면 로그인 페이지를 띄운 뒤 텔레그램으로 "네이버 로그인 한 번만"
  요청하고 조용히 기다린다. 무한 재시도는 하지 않는다.

```bash
.venv/bin/python scripts/krx_login.py --open     # 로그인 창만 띄우기
.venv/bin/python scripts/krx_login.py --reset    # 대기 상태 수동 해제
```

사람이 로그인하면 다음 점검에서 자동으로 대기 상태가 풀린다.

## 알림 (텔레그램)

무인 실행에서 가장 큰 위험은 **실패가 조용히 묻히는 것**이다. 실제로 크롬이
안 떠 있어 공매도만 며칠씩 멈췄는데도 파이프라인은 매일 "배포 완료"로 끝났다.
사람이 개입해야 풀리는 상황만 골라 보낸다.

```
TELEGRAM_BOT_TOKEN=...      # @BotFather → /newbot
TELEGRAM_CHAT_ID=...        # getUpdates 의 chat.id
```

| 사유 | 발송 조건 |
|---|---|
| 세션 만료 → 수동 로그인 요청 | 프로필 쿠키로도 복구 안 될 때 (네이버 로그인 필요) |
| 크롬 문제 | 원격 디버깅 크롬 기동 실패 |
| 공매도 지연 | 잔고가 정상(T+2)보다 더 밀렸을 때 |
| 파이프라인 중단 | 예외·비정상 종료 |

같은 사유는 쿨다운(6~24시간) 동안 반복 발송하지 않는다. 미설정이면 조용히
건너뛰되 로그에 남는다.

## 수동 갱신 버튼

대시보드 우상단의 **수동 갱신** 버튼은 `scripts/refresh_agent.py` 로 요청을 보낸다.
GitHub Pages는 정적 사이트라 페이지가 직접 파이프라인을 돌릴 수 없기 때문이다.

```bash
bash mac/agent.sh          # 127.0.0.1:8776 (install_schedule.sh 가 상주 등록)
```

버튼을 누르면 파이프라인이 백그라운드로 시작되고 진행 로그가 페이지에 흐른다.
끝나면 페이지가 자동으로 새 데이터를 다시 읽는다.

> 브라우저는 https 페이지에서 http 로 나가는 요청을 막는데 **localhost 만 예외**다.
> 즉 버튼은 **에이전트가 도는 그 컴퓨터에서 대시보드를 열었을 때** 활성화된다
> (맥미니). 다른 기기에서는 회색으로 비활성화되고, 왜 그런지 안내가 뜬다.
> 외부에서도 쓰려면 에이전트를 https 로 노출(예: Cloudflare Tunnel)한 뒤
> 버튼을 우클릭해 그 주소를 등록하면 된다. 개방한다면 `.env` 에 `AGENT_TOKEN` 을
> 반드시 설정할 것.

## 신선도 표시

`dashboard_data.json` 의 `meta` 가 지연을 그대로 노출한다.

- `shortLagDays` — 공매도 확정일이 기준일보다 몇 거래일 뒤인지
- `shortStaleDays` — 정상 지연(T+2)을 뺀 **초과** 지연. 0이 아니면 수집이 멈춘 것

초과 지연이 있으면 대시보드 상단에 배지와 배너가 뜨고 텔레그램 알림도 나간다.

### 데이터 이관

```bash
python scripts/pack_data.py              # 필수 CSV만 (~43MB)
python scripts/pack_data.py --with-raw   # 원본 캐시까지 (외부 공개 금지)
python scripts/pack_data.py --unpack bootstrap_data.tar.gz
```

새 머신에서 처음부터 수집하면 KRX에 수백 건을 요청하게 되어 IP 차단 위험이 있다.
아카이브를 옮기면 재수집 없이 이어서 돌릴 수 있다.

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

> ⚠️ **빈 응답은 캐시하지 않는다.** OPEN API는 게시 전에 물으면 빈 배열을 준다.
> 이걸 캐시에 남기면 그 날짜는 영원히 빈 값으로 굳는다 — 실제로 7/30~8/3
> 시세가 통째로 유실됐고, 파이프라인은 매일 성공으로 끝났다. `krx_open.py` 는
> 비어 있는 캐시 파일을 발견하면 지우고 다시 받는다.

## 파일

```
scripts/
  common.py          경로·유니버스 공통 (.env 자동 적재)
  envfile.py         .env 파서 (launchd는 셸 환경을 안 물려준다)
  notify.py          텔레그램 알림 (사유별 쿨다운)
  chrome.py          KRX 로그인용 크롬 기동·점검 (Win/mac 공통)
  cdp.py             얇은 CDP 클라이언트 (navigate/evaluate)
  krx_login.py       세션 확보(프로필 쿠키 복구) + 수동 로그인 요청·대기
  krx_keepalive.py   20분 주기 세션 연장 상주 프로세스
  refresh_agent.py   대시보드 '수동 갱신' 버튼 수신 HTTP 에이전트
  krx_open.py        OPEN API 시세/상장주식수 수집
  build_master.py    종목기본정보 결합 → 보통주·시총 필터 → universe.csv
  fnguide_float.py   FnGuide 유동주식수 수집
  krx_session.py     크롬(CDP) 로그인 세션 대여
  krx_short.py       공매도 잔고·거래량 수집 (--from-cache 복원 지원)
  estimate.py        α·β 회귀 + D일 추정잔고
  build_dashboard.py web/dashboard_data.json 생성
  cdp_capture.py     KRX 화면의 bld/파라미터 캡처 (신규 화면 추가용)
  cdp_listen.py      수동 조작 대기형 캡처
  pipeline.py        일일 갱신 오케스트레이션 (Windows/macOS 공통)
  pack_data.py       데이터 이관 아카이브 생성/복원
  scan_secrets.py    공개 저장소 업로드 전 민감정보 점검
  fix_ps1_bom.py     .ps1 파일 UTF-8 BOM 보정
  coverage.py        거래일 대비 수집 커버리지·결측 구간 점검
mac/                 macOS 실행 래퍼
  setup.sh           최초 셋업 (venv·의존성·.env)
  launch_chrome.sh   KRX 로그인용 크롬 (원격 디버깅 9222)
  daily.sh           launchd 진입점 — 일일 갱신
  keepalive.sh       launchd 진입점 — 세션 유지 상주
  agent.sh           launchd 진입점 — 수동 갱신 에이전트 상주
  install_schedule.sh launchd 3종 등록/해제
  doctor.sh          환경 점검
  serve.sh           로컬 서버
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
