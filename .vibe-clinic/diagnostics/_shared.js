/**
 * 진단 공통 도구 (shared helper for diagnostics).
 *
 * 왜 이 파일이 있는가 —
 * 네 개의 진단이 전부 "명령을 돌리고 출력을 읽는" 같은 일을 한다.
 * 각자 구현하면 네 곳에서 조금씩 다르게 실패한다.
 * 이 프로젝트는 같은 판정을 두 곳에서 다르게 계산해 서로 다른 답을 낸 적이 두 번 있다.
 *
 * 반드시 지키는 계약:
 *   1. 명령이 실패하면 실패했다고 말한다. 조용히 통과시키지 않는다.
 *   2. 출력을 읽지 못하면 '읽지 못했다'고 말한다. '문제 없음'과 구분한다.
 *   3. 무엇을 검사하지 않았는지 항상 함께 돌려준다.
 */

const { execSync } = require('child_process');

/**
 * 명령을 돌리고 결과를 그대로 돌려준다.
 *
 * execSync 는 종료 코드가 0이 아니면 예외를 던진다. 그 예외를 삼키지 않는다 —
 * 삼키면 "검사가 안 돌았다"와 "문제가 없다"가 같아 보인다.
 * 이 프로젝트가 반복해서 데인 형태다.
 */
function run(cmd, cwd) {
  try {
    const out = execSync(cmd, {
      cwd,
      encoding: 'utf8',
      timeout: 180000,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });
    return { ok: true, code: 0, out: out || '' };
  } catch (e) {
    // stdout 도 함께 돌려준다. 실패한 명령의 출력에 원인이 들어 있는 경우가 많다.
    // 실제로 이 프로젝트에서 stderr 를 버리는 바람에 원인 규명에 몇 시간이 걸린 적이 있다.
    return {
      ok: false,
      code: typeof e.status === 'number' ? e.status : -1,
      out: (e.stdout || '') + (e.stderr || ''),
      err: e.message,
    };
  }
}

/**
 * 검사 결과에 '검사하지 않은 것'을 반드시 붙인다.
 *
 * "통과"를 "참"으로 읽히게 두면 이 진단 자체가 새로운 거짓말이 된다.
 * 통과는 '내가 본 범위에서 문제를 못 찾았다'는 뜻이지 '문제가 없다'가 아니다.
 */
function verdict(status, summary, notChecked) {
  const limit = notChecked ? `\n  · 검사하지 않은 것: ${notChecked}` : '';
  return { status, details: `${summary}${limit}` };
}

module.exports = { run, verdict };
