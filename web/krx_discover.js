/* ============================================================
 * KRX 공매도/대차 데이터 bld 탐색 스크립트
 *
 * 사용법
 *  1) Chrome에서 https://data.krx.co.kr 에 로그인
 *  2) 아무 데이터 화면(예: 통계 > 주식 > 종목시세)을 연 상태에서 F12 → Console
 *  3) 이 파일 내용 전체를 붙여넣고 Enter
 *  4) 출력된 표를 그대로 복사해서 Claude에게 전달
 *
 * 아무것도 저장하지 않고 조회만 한다.
 * ============================================================ */
(async () => {
  const URL_ = 'https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd';
  const DAY  = '20260728';   // 조회 테스트용 최근 거래일
  const PREV = '20260721';

  // 공매도(srt) 통계 화면들이 쓰는 bld 후보 + 대차(sec lending) 후보
  const BLDS = [];
  for (let n = 30001; n <= 31201; n += 100) BLDS.push('dbms/MDC/STAT/srt/MDCSTAT' + n);
  for (let n = 30101; n <= 30901; n += 100) BLDS.push('dbms/MDC/STAT/srt/MDCSTAT' + String(n + 1));
  // 대차거래(정보데이터시스템 > 증권상품/기타)
  ['MDCSTAT10501','MDCSTAT10601','MDCSTAT10701','MDCSTAT21501','MDCSTAT21601']
    .forEach(b => BLDS.push('dbms/MDC/STAT/standard/' + b));

  // bld마다 파라미터 이름이 달라서 superset을 보낸다 (여분 키는 무시됨)
  const baseParams = {
    locale: 'ko_KR',
    mktId: 'STK', mktTpCd: '1', mktsel: 'ALL', secugrpId: 'STMFRTSCIFDRFS',
    trdDd: DAY, strtDd: PREV, endDd: DAY, tboxisuCd_finder_srtisu0_0: '',
    isuCd: '', isuCd2: '', codeNmisuCd_finder_srtisu0_0: '',
    param1isuCd_finder_srtisu0_0: '', inqCondTpCd: '1', inqTpCd: '1',
    askBidTpCd: '3', share: '1', money: '1', csvxls_isNo: 'false',
  };

  async function call(bld) {
    const body = new URLSearchParams({ ...baseParams, bld });
    try {
      const r = await fetch(URL_, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
        body,
      });
      const t = await r.text();
      if (!t.trim().startsWith('{')) return { bld, status: r.status, note: t.slice(0, 40) };
      const js = JSON.parse(t);
      const blockKey = Object.keys(js).find(k => Array.isArray(js[k]) && js[k].length);
      if (!blockKey) return { bld, status: r.status, note: 'empty(' + Object.keys(js).join(',') + ')' };
      const rows = js[blockKey];
      return {
        bld, status: r.status, rows: rows.length,
        cols: Object.keys(rows[0]).join('|'),
        sample: JSON.stringify(rows[0]).slice(0, 220),
      };
    } catch (e) { return { bld, status: 'ERR', note: String(e).slice(0, 60) }; }
  }

  console.log('탐색 시작: ' + BLDS.length + '개 bld …');
  const hits = [];
  for (const b of BLDS) {
    const r = await call(b);
    if (r.rows) { hits.push(r); console.log('✅', r.bld, r.rows + '행', r.cols); }
    await new Promise(s => setTimeout(s, 120));
  }
  console.log('\n===== 데이터가 나온 bld =====');
  console.table(hits.map(h => ({ bld: h.bld, rows: h.rows, cols: h.cols })));
  console.log('\n===== 아래 JSON을 통째로 복사해서 전달 =====');
  console.log(JSON.stringify(hits, null, 1));
  window.__krxHits = hits;
})();
