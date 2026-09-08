/**
 * 02. 규칙 동기화 검사 (principle sync, 세 도구가 같은 규칙을 갖고 있는지 보는 검사)
 *
 * 왜 필요한가 —
 * 세 도구(Codex·Claude Code·Antigravity)는 각자 자기 규칙 파일을 읽는다.
 * 한쪽만 고치면 셋이 서로 다른 규칙을 따르게 되고,
 * 그 순간 "동기화됐다"는 말은 선언일 뿐 사실이 아니게 된다.
 *
 * 실제로 그런 일이 있었다. 문구가 '있는지'만 검사했더니
 * SKILL.md 가 '위반 시 제재' 계약을 빠뜨린 채 통과하고 있었다.
 */

const { run, verdict } = require('./_shared');

module.exports = {
  id: 'principle-sync',
  name: '02 규칙 동기화 — 세 도구가 같은 규칙을 갖고 있는가',
  layer: 'SYSTEM',

  async run(ctx) {
    const root = ctx.projectDir || ctx.cwd;
    const r = run('python csc_sync.py', root);

    const notChecked =
      '규칙을 실제로 지키는지(문서에 있다는 것과 지킨다는 것은 다름), ' +
      'Codex·Antigravity 가 그 파일을 정말 읽었는지';

    if (!r.out || !r.out.includes('결과:')) {
      return verdict('ERROR',
        `동기화 검사가 결과를 내지 못했습니다.\n` +
        `  · 종료 코드: ${r.code}\n` +
        `  · 하실 일: python csc_sync.py 를 직접 돌려 보세요`,
        notChecked);
    }

    if (r.out.includes('불일치')) {
      const missing = (r.out.match(/누락된 계약: .*/g) || []).slice(0, 6);
      return verdict('ERROR',
        `세 도구의 규칙이 어긋나 있습니다.\n` +
        `  · ${missing.join('\n  · ') || '상세를 읽지 못했습니다'}\n` +
        `  · 하실 일: 정본(USER_FIRST_PRINCIPLE.md)을 고친 뒤 나머지 파일에 같은 계약을 반영합니다\n` +
        `  · 한쪽만 고치면 동기화가 아니라 분열입니다`,
        notChecked);
    }

    const line = (r.out.match(/결과: 정상.*/) || ['결과 확인'])[0];
    return verdict('OK', `${line.trim()}`, notChecked);
  },
};
