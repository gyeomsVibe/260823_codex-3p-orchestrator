/**
 * 03. 거짓 주장 결산 (claim audit, 지어낸 말이 있었는지 세는 검사)
 *
 * ★ 네 개 중 핵심이다. 그리고 한 번 크게 고쳤다. ★
 *
 * ━━ 처음 만들 때 내가 틀렸던 것 (2026-09-07 교정) ━━━━━━━━━━━━━━━━━━━━━
 * 처음엔 누적 건수만 셌다. 그래서 "지적 32건, 이것이 수정 단계의 할 일 목록" 이라고
 * 사용자에게 두 번 보고했다. **틀린 말이었다.**
 *
 * 확인해 보니 32건 전부가 최소 10.9시간 전 것이었고, 대부분 28~41시간 전이었다.
 * 그리고 "없다" 던 파일들은 지금 다 있다 — 그때 지적이 옳았고, 그래서 이미 고쳐진 것이다.
 *
 * 즉 이 기록은 **열려 있는 결함 목록이 아니라 과거에 한 말의 장부**다.
 * 이미 보낸 메시지는 되돌릴 수 없다. 장부의 숫자를 '할 일' 이라고 부르면 안 된다.
 *
 * ━━ 왜 이 구분이 중요한가 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 누적만 세면 이 숫자는 **영원히 늘기만 한다.** 32 → 40 → 60.
 * 그러면 사람은 곧 이 항목을 읽지 않게 되고, 진짜 문제가 생겨도 지나친다.
 * 이 프로젝트가 이미 두 번 겪은 경보 무감각(alarm fatigue)이다.
 *
 * 그래서 최근과 과거를 나눈다.
 *   최근에 생긴 것  -> 지금 고쳐야 할 것. 주의(WARNING)
 *   오래된 것       -> 이미 지난 기록. 참고로만 보여준다
 */

const fs = require('fs');
const path = require('path');
const { verdict } = require('./_shared');

// 규칙 번호를 사람 말로 옮긴다. R3 만 적으면 무슨 뜻인지 알 수 없다.
const RULE_NAMES = {
  R1: '존재하지 않는 파일을 완료했다고 말함',
  R2: '파일 줄 수 등 수치가 실제와 다름',
  R3: '이미 낡은 해시를 현재 값처럼 인용',
  R4: '"0건"이라 했는데 다시 세니 있었음',
  R5: '합의했다면서 누가 언제 동의했는지 못 댐',
  R6: '완료했다면서 확인한 근거를 안 댐',
  R7: '검증 못 한 것을 밝히지 않음',
};

// 이 시간 안에 생긴 것을 '최근' 으로 본다.
// 하루로 잡은 이유: 그보다 오래된 것은 이미 다음 작업으로 덮였을 가능성이 높다.
const RECENT_HOURS = 24;

module.exports = {
  id: 'claim-audit',
  name: '03 거짓 주장 결산 — 최근에 지어낸 말이 있는가',
  layer: 'SYSTEM',

  async run(ctx) {
    const root = ctx.projectDir || ctx.cwd;
    const logPath = path.join(root, '.agent-swarm', 'messages', 'claim_audit.jsonl');
    const inBuildPhase = fs.existsSync(path.join(root, '.agent-swarm', 'BUILD_PHASE'));

    const notChecked =
      '의미가 맞는지(문장이 논리적으로 옳은지), 본문 밖에서 실제로 한 일, 발신자 신원, ' +
      '오래된 지적이 정말 해소됐는지(시간만 보고 판단합니다)';

    if (!fs.existsSync(logPath)) {
      return verdict('ERROR',
        '감사 기록 파일이 없습니다. 감지기가 한 번도 돌지 않았을 수 있습니다.\n' +
        '  · "기록이 없음"을 "문제가 없음"으로 읽지 마세요',
        notChecked);
    }

    const cutoff = Date.now() - RECENT_HOURS * 3600 * 1000;
    const recent = {}, old = {};
    const bySender = {};
    let broken = 0, checks = 0, newest = 0;

    for (const line of fs.readFileSync(logPath, 'utf8').split('\n')) {
      const t = line.trim();
      if (!t) continue;
      let d;
      try { d = JSON.parse(t); } catch { broken++; continue; }
      checks++;
      const when = Date.parse(d.at || '') || 0;
      const isRecent = when >= cutoff;
      for (const f of d.findings || []) {
        const bucket = isRecent ? recent : old;
        bucket[f.rule] = (bucket[f.rule] || 0) + 1;
        if (isRecent) {
          const s = d.sender || '(미기록)';
          bySender[s] = (bySender[s] || 0) + 1;
          newest = Math.max(newest, when);
        }
      }
    }

    if (broken > 0) {
      return verdict('ERROR',
        `감사 기록 ${broken}줄이 깨져 읽히지 않습니다. 기록 자체가 손상됐습니다.`,
        notChecked);
    }

    const sum = (o) => Object.values(o).reduce((a, b) => a + b, 0);
    const nRecent = sum(recent), nOld = sum(old);

    const phaseNote = inBuildPhase
      ? '\n  · 지금은 "먼저 만드는 단계"입니다. 감지기가 막지 않고 기록만 합니다.\n' +
        '  · 고칠 준비가 되면 .agent-swarm/BUILD_PHASE 파일을 지우세요.'
      : '\n  · 지금은 "고치는 단계"입니다. 감지기가 다시 막습니다.';

    const oldNote = nOld
      ? `\n  · 참고: ${RECENT_HOURS}시간보다 오래된 기록이 ${nOld}건 더 있습니다.\n` +
        `    이미 지난 일이며 할 일 목록이 아닙니다. 그때 지적이 맞았고 그래서 고쳐진 것입니다.`
      : '';

    if (checks === 0) {
      return verdict('WARNING',
        `감사 기록이 비어 있습니다. 감지기가 돌지 않았을 수 있습니다.${phaseNote}`,
        notChecked);
    }

    if (nRecent === 0) {
      return verdict('OK',
        `최근 ${RECENT_HOURS}시간 안에 새로 지어낸 말이 없습니다. (검사 ${checks}건)` +
        oldNote + phaseNote,
        notChecked);
    }

    const breakdown = Object.entries(recent)
      .sort((a, b) => b[1] - a[1])
      .map(([r, n]) => `  · ${r} ${n}건 — ${RULE_NAMES[r] || '설명 없음'}`)
      .join('\n');
    const who = Object.entries(bySender)
      .sort((a, b) => b[1] - a[1])
      .map(([s, n]) => `${s} ${n}건`)
      .join(' · ');

    return verdict('WARNING',
      `최근 ${RECENT_HOURS}시간 안에 지적 ${nRecent}건이 있습니다. 이것이 지금 고칠 목록입니다.\n` +
      breakdown +
      `\n  · 누가: ${who}` +
      `\n  · 가장 최근: ${new Date(newest).toISOString().slice(0, 16)}` +
      oldNote + phaseNote,
      notChecked);
  },
};
