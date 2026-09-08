/**
 * 01. 회귀 검사 (regression, 고치다가 다른 게 깨졌는지 보는 검사)
 *
 * 왜 이게 1번인가 —
 * 공개 자료가 말한다. 빠르게 만든 코드를 성공적으로 정리한 팀들은
 * "고치기 전에 검사 도구를 먼저 세웠다. 나란히가 아니다."
 * (Autonoma, Vibe Coding Technical Debt)
 *
 * 그래서 수정 단계에 들어가면 가장 먼저 "지금 무엇이 깨져 있는가"를 안다.
 */

const path = require('path');
const { run, verdict } = require('./_shared');

module.exports = {
  id: 'regression',
  name: '01 회귀 검사 — 고치다 깨진 것이 있는가',
  layer: 'SYSTEM',

  async run(ctx) {
    const root = ctx.projectDir || ctx.cwd;
    const r = run('python -m unittest discover -s tests -q 2>&1', root);

    // unittest 정본 출력의 "Ran N tests"와 최종 상태를 함께 확인한다.
    // 종료 코드만 믿으면 0개 수집 같은 공허한 검사를 놓칠 수 있다.
    const ran = /Ran\s+(\d+)\s+tests?/.exec(r.out);
    const failures = /failures=(\d+)/.exec(r.out);
    const errors = /errors=(\d+)/.exec(r.out);
    const skipped = /skipped=(\d+)/.exec(r.out);
    const total = ran ? parseInt(ran[1], 10) : 0;
    const nFailed = failures ? parseInt(failures[1], 10) : 0;
    const nErrors = errors ? parseInt(errors[1], 10) : 0;
    const nSkipped = skipped ? parseInt(skipped[1], 10) : 0;
    const nPassed = Math.max(0, total - nFailed - nErrors - nSkipped);

    const notChecked =
      '통합 동작(여러 모듈을 함께 돌렸을 때), 실제 AI 응답 품질, 성능';

    // 검사가 아예 안 돌았는데 통과로 읽히는 것을 막는다.
    // "검사할 것이 없음"과 "이상 없음"은 다르다.
    if (!ran || !/\b(?:OK|FAILED)\b/.test(r.out)) {
      return verdict('ERROR',
        `테스트 결과를 읽지 못했습니다. 검사가 돌지 않았을 수 있습니다.\n` +
        `  · 종료 코드: ${r.code}\n` +
        `  · 출력 끝부분: ${(r.out || '(없음)').trim().slice(-200)}\n` +
        `  · 하실 일: 터미널에서 python -m unittest discover -s tests -q 를 직접 돌려 보세요`,
        notChecked);
    }

    if (r.code !== 0 || nFailed > 0 || nErrors > 0 || /\bFAILED\b/.test(r.out)) {
      return verdict('ERROR',
        `테스트 실패 ${nFailed}개, 오류 ${nErrors}개입니다 (통과 ${nPassed}개).\n` +
        `  · 출력 끝부분: ${r.out.trim().slice(-500)}\n` +
        `  · 하실 일: 위 실패와 오류부터 고칩니다`,
        notChecked);
    }

    if (total === 0) {
      return verdict('ERROR',
        '테스트가 0개 수집됐습니다. 검사기가 아무것도 보지 않고 있습니다.',
        notChecked);
    }

    return verdict('OK',
      `테스트 ${nPassed}개가 통과했고 ${nSkipped}개를 건너뛰었습니다. 지금 깨진 것은 없습니다.`,
      notChecked);
  },
};
