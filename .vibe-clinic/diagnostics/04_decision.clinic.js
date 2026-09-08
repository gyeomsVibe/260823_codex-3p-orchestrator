/**
 * 04. 의사결정 검사 (decision, 결정이 멈추지 않는지 보는 검사)
 *
 * 왜 필요한가 —
 * 세 도구는 동시에 존재할 수 없다. Codex 는 사용량 한도에 걸리고,
 * Antigravity 는 권한 문제로 막히고, Claude Code 는 사용자가 열어야 존재한다.
 *
 * 이 프로젝트는 한 번 크게 데였다.
 *   전에는 "자리에 없으면 찬성한 것으로" 처리 → 없는 합의를 기록했다(유령 만장일치)
 *   고친 뒤엔 "자리에 없으면 반대" → 아무것도 결정하지 못하는 교착이 됐다
 *
 * 지금은 "자리에 없으면 기권"이다. 그 로직이 여전히 성립하는지 매번 확인한다.
 * 교착은 결정이 아니다. 아무도 결정하지 않는 것을 안전이라 부르지 않는다.
 */

const { run, verdict } = require('./_shared');

module.exports = {
  id: 'decision-integrity',
  name: '04 의사결정 — 결정이 멈추지 않는가',
  layer: 'SYSTEM',

  async run(ctx) {
    const root = ctx.projectDir || ctx.cwd;
    const r = run('python csc_decide.py', root);

    const notChecked =
      '실제 안건에서 세 도구가 정말 투표했는지, 표가 같은 후보에 대한 것인지';

    const m = /결과:\s*(\d+)\/(\d+)\s*통과/.exec(r.out || '');
    if (!m) {
      return verdict('ERROR',
        `자체 검사 결과를 읽지 못했습니다.\n` +
        `  · 종료 코드: ${r.code}\n` +
        `  · 하실 일: python csc_decide.py 를 직접 돌려 보세요\n` +
        `  · "결과를 못 읽음"을 "이상 없음"으로 읽지 마세요`,
        notChecked);
    }

    const [, pass, all] = m;
    if (pass !== all) {
      const fails = (r.out.match(/\s*실패\s+.*/g) || []).slice(0, 5);
      return verdict('ERROR',
        `의사결정 로직 검사 ${all}개 중 ${Number(all) - Number(pass)}개가 실패했습니다.\n` +
        `  · ${fails.join('\n  · ') || '상세를 읽지 못했습니다'}\n` +
        `  · 이게 깨지면 결정이 멈추거나, 없는 합의가 기록될 수 있습니다`,
        notChecked);
    }

    return verdict('OK',
      `의사결정 로직 ${all}개 검사가 모두 통과했습니다. ` +
      `자리를 비운 도구는 기권으로 처리되고, 되돌릴 수 없는 일은 사용자 승인이 필요합니다.`,
      notChecked);
  },
};
