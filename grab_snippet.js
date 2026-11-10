// 雨课堂 24H 学伴 → API 参数一键导出
// 用法: 登录雨课堂后, 在 changjie.yuketang.cn 任意页面 F12 控制台粘贴运行
(function () {
  const ck = document.cookie;
  const get = (n) => (ck.match(new RegExp(n + '=([^;]+)')) || [])[1] || '';
  const out = {
    YKT_SESSION: 'sessionid=' + get('sessionid') + '; csrftoken=' + get('csrftoken'),
    YKT_UV_ID: get('uv_id') || get('university_id') || '0',
  };
  // 找页面上已打开的 24H 学伴 iframe, 抄它的 agentId / classroomId
  const ifr = [...document.querySelectorAll('iframe')].map(f => f.src)
    .filter(u => /chatbot-window|ai-accompany/.test(u));
  out.iframe_urls = ifr;
  ifr.forEach(u => {
    const q = new URL(u, location.origin).searchParams;
    if (q.get('agentId')) out.YKT_AGENT_ID = q.get('agentId');
    if (q.get('classroomId')) out.YKT_CLASSROOM_ID = q.get('classroomId');
  });
  console.log('%c 复制下面几行到终端 export: ', 'background:#4a90e2;color:#fff');
  Object.entries(out).forEach(([k, v]) => console.log(`export ${k}='${v}'`));
  // 顺手把 capability 也打出来(24H 学伴配置)
  const aid = out.YKT_AGENT_ID;
  if (aid) {
    fetch(`/c27/online_courseware/ykt/agent/${aid}/capability/?category=1`,
      { headers: { xtbz: 'ykt', 'Xt-Agent': 'web' }, credentials: 'include' })
      .then(r => r.json()).then(j => console.log('agent capability:', j));
  }
  return out;
})();
