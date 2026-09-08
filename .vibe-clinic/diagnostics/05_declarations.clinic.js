/**
 * 05. 선언 대조 (declaration check, 파일이 적어 둔 말과 실제가 같은지 보는 검사)
 *
 * ━━ 왜 이 진단이 필요한가 — 진단 4개가 놓친 구멍 ━━━━━━━━━━━━━━━━━━━━━
 * 2026-09-07 실측: 브로커가 죽어 있는데 자가진단은 건강도 75% 를 보고했다.
 * 네 진단 중 어느 것도 "지금 시스템이 선언한 상태와 실제가 다르다" 를 보지 않았기 때문이다.
 *
 * 그 순간 broker.json 은 status="RUNNING" 이라고 적혀 있었고 프로세스는 없었다.
 * **파일이 거짓말을 하고 있는데 건강도는 75% 였다.**
 *
 * ━━ 이 프로젝트가 이 형태로만 다섯 번 데였다 ━━━━━━━━━━━━━━━━━━━━━━━━
 *   broker.json    status "RUNNING"  실제 죽음
 *   workers/*.json status "ready"    실제 죽음, 하트비트 288분 정지
 *   GOVERNANCE 표  "미응답"          실제로는 구현 완료된 지 오래
 *   훅 브리핑      "막힘 3건"        실제 0건
 *   예시 진단      "건강도 100%"     아무것도 검사하지 않음
 *
 * 그래서 이 진단은 브로커를 보는 것이 아니다. **선언과 실제의 벌어짐 자체**를 본다.
 * 브로커를 없애기로 결정하더라도 이 진단은 남는다. 대상이 아니라 형태를 보기 때문이다.
 */

const fs = require('fs');
const path = require('path');
const { run, verdict } = require('./_shared');

// PID 가 살아 있는지는 Node 로 직접 보지 않는다.
// 이 프로젝트에서 os.kill 기반 판정이 이 환경에서 망가진 적이 있어(모든 PID 를 죽었다고 답함),
// 이미 검증된 파이썬 쪽 판정기를 그대로 쓴다. 판정 출처를 둘로 만들지 않는다.
function pidState(root, pid) {
  const r = run(`python -c "import sys;sys.path.insert(0,'.');` +
                `from csc_process import probe_pid;print(probe_pid(${pid}))"`, root);
  return r.ok ? (r.out || '').trim() : 'unknown';
}

module.exports = {
  id: 'declaration-check',
  name: '05 선언 대조 — 파일이 적은 말과 실제가 같은가',
  layer: 'SYSTEM',

  async run(ctx) {
    const root = ctx.projectDir || ctx.cwd;
    const swarm = path.join(root, '.agent-swarm');
    const lies = [];
    const checked = [];

    // ① 브로커: RUNNING 이라고 적혀 있는데 프로세스가 없는가
    const brokerPath = path.join(swarm, 'broker.json');
    if (fs.existsSync(brokerPath)) {
      try {
        const b = JSON.parse(fs.readFileSync(brokerPath, 'utf8'));
        const claim = String(b.status || '').toUpperCase();
        checked.push('브로커');
        if (claim === 'RUNNING') {
          const st = pidState(root, b.pid);
          if (st === 'gone') {
            lies.push(`broker.json 은 "RUNNING"(실행 중) 이라 적혀 있는데 ` +
                      `프로세스 ${b.pid} 는 없습니다`);
          }
        }
      } catch (e) {
        lies.push(`broker.json 을 읽을 수 없습니다: ${e.message}`);
      }
    }

    // ② 워커: ready 라고 적혀 있는데 죽었거나 하트비트가 멈췄는가
    const wdir = path.join(swarm, 'workers');
    if (fs.existsSync(wdir)) {
      for (const f of fs.readdirSync(wdir)) {
        if (!f.endsWith('.json') || f.endsWith('.cursor.json')) continue;
        try {
          const w = JSON.parse(fs.readFileSync(path.join(wdir, f), 'utf8'));
          checked.push(`워커 ${w.agent || f}`);
          if (String(w.status || '') !== 'ready') continue;
          const st = pidState(root, w.pid);
          const ageMin = (Date.now() / 1000 - (w.heartbeat_epoch || 0)) / 60;
          if (st === 'gone') {
            lies.push(`${w.agent} 는 "ready"(준비됨) 라 적혀 있는데 ` +
                      `프로세스 ${w.pid} 는 없습니다 (마지막 신호 ${ageMin.toFixed(0)}분 전)`);
          } else if (ageMin > 5) {
            lies.push(`${w.agent} 는 "ready" 라 적혀 있는데 ` +
                      `${ageMin.toFixed(0)}분째 신호가 없습니다`);
          }
        } catch (e) {
          lies.push(`워커 파일 ${f} 을 읽을 수 없습니다: ${e.message}`);
        }
      }
    }

    // ③ 진단 자신: 아무것도 검사하지 않는 진단이 섞여 있는가
    const ddir = path.join(root, '.vibe-clinic', 'diagnostics');
    if (fs.existsSync(ddir)) {
      for (const f of fs.readdirSync(ddir)) {
        if (!f.endsWith('.clinic.js') || f.startsWith('_')) continue;
        const src = fs.readFileSync(path.join(ddir, f), 'utf8');
        if (!/run\(|readFileSync|existsSync/.test(src)) {
          lies.push(`진단 ${f} 이 아무것도 측정하지 않습니다 — 늘 통과를 내보냅니다`);
        }
      }
      checked.push('진단 자체');
    }

    const notChecked =
      '문서에 적힌 계획과 실제 구현이 같은지, 사람이 한 말과 실제가 같은지. ' +
      '이 진단은 기계가 쓴 상태 파일만 봅니다';

    if (checked.length === 0) {
      return verdict('ERROR',
        '대조할 상태 파일을 하나도 찾지 못했습니다. 검사한 것이 없으므로 통과라고 할 수 없습니다.',
        notChecked);
    }

    if (lies.length === 0) {
      return verdict('OK',
        `파일이 적어 둔 상태와 실제가 일치합니다. (${checked.length}개 대조: ${checked.join(', ')})`,
        notChecked);
    }

    return verdict('WARNING',
      `파일이 적어 둔 것과 실제가 다릅니다 — ${lies.length}건.\n` +
      lies.map((l) => `  · ${l}`).join('\n') +
      `\n  · 하실 일: 지금 당장 위험하진 않습니다. 다만 다른 화면이 이 파일을 믿고\n` +
      `    "정상"이라고 말할 수 있으므로, python csc.py activate 로 실제와 맞추세요.\n` +
      `  · 이 프로젝트가 같은 형태로 다섯 번 속았습니다. 그래서 이 진단이 있습니다.`,
      notChecked);
  },
};
