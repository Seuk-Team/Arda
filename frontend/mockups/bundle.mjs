/* 목업 화면 전부를 index.html 한 파일로 묶는다.
   파일 하나만 넘기면 되니까 전달·리뷰가 쉽고, localhost:5500 루트로도 바로 열린다.
   실행: node frontend/mockups/bundle.mjs

   iframe 을 안 쓰는 이유 — file:// 로 열면 교차 출처로 막힌다.
   대신 css/body/js 를 뽑아 두고 화면을 바꿀 때마다 갈아 끼운다. */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const DIR = path.dirname(fileURLToPath(import.meta.url))

/* 값은 좌측 상단 제목에 쓴다. 순서가 곧 화면 순서 — 첫 항목이 시작 화면이다. */
const TITLES = {
  'mockup-dashboard.html': '대시보드',
  'mockup-postings.html': '채용 공고',
  'mockup.html': '공고의 지원자',
  'mockup-applicants.html': '지원자',
  'mockup-interviews.html': '면접 일정',
  'mockup-evaluations.html': '평가 현황',
  'mockup-settings.html': '설정',
  'mockup-posting-new.html': '공고 등록',
  'mockup-applicant-new.html': '지원자 등록',
  'mockup-login.html': '로그인',
  'mockup-apply.html': '지원서 접수',
  'mockup-mobile.html': '모바일',
}

function split(html) {
  const css = [...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi)].map((m) => m[1]).join('\n')
  const js = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)].map((m) => m[1]).join('\n')
  const bodyMatch = html.match(/<body[^>]*>([\s\S]*)<\/body>/i)
  const body = (bodyMatch ? bodyMatch[1] : '').replace(/<script[\s\S]*?<\/script>/gi, '')
  return { css, body, js }
}

const screens = Object.keys(TITLES)
  .map((file) => `  ${JSON.stringify(file)}: ${JSON.stringify(split(fs.readFileSync(path.join(DIR, file), 'utf8')))},`)
  .join('\n')

const out = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Arda 목업 모음</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap" rel="stylesheet">
<style id="scr"></style>
</head>
<body>
<script>
var SCREENS = {
${screens}
};

var TITLES = ${JSON.stringify(TITLES)};
var styleEl = document.getElementById('scr');

function show(file, query) {
  var s = SCREENS[file];
  if (!s) { return; }

  styleEl.textContent = s.css;
  document.body.innerHTML = s.body;
  document.title = 'Arda 목업 — ' + (TITLES[file] || file);

  // 원본은 location.search 로 파라미터를 읽고 location.href 로 화면을 옮긴다.
  // 한 파일 안에는 주소가 없으므로 그 두 지점만 갈아끼운다.
  var code = s.js
    .replace(/location\\.href\\s*=/g, '__loc.href=')
    .replace(/location\\.search/g, JSON.stringify(query || ''));
  try {
    new Function('__loc', code)({ set href(u) { go(u); } });
  } catch (err) {
    console.error('[' + file + '] script error', err);
  }
}

function go(url) {
  var u = String(url);
  var i = u.indexOf('?');
  var file = (i < 0 ? u : u.slice(0, i)).split('/').pop();
  var query = i < 0 ? '' : u.slice(i);
  if (SCREENS[file]) { show(file, query); window.scrollTo(0, 0); }
}

// 화면 안의 링크는 전부 여기서 가로챈다
document.addEventListener('click', function (e) {
  var a = e.target.closest && e.target.closest('a[href]');
  if (!a) { return; }
  var href = a.getAttribute('href');
  if (!href || href.charAt(0) === '#') { return; }
  if (/^(https?:|mailto:)/i.test(href)) { return; }
  e.preventDefault();
  go(href);
}, true);

show(${JSON.stringify(Object.keys(TITLES)[0])}, '');
</script>
</body>
</html>
`

fs.writeFileSync(path.join(DIR, 'index.html'), out)
console.log('index.html', (out.length / 1024).toFixed(0) + 'KB', Object.keys(TITLES).length + ' screens')
