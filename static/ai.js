'use strict';
const form = document.getElementById('ai-form');
const question = document.getElementById('ai-question');
const statusLine = document.getElementById('ai-status');
const messages = document.getElementById('ai-messages');
let history = [];
let busy = false;
function bubble(role, text) {
  const box = document.createElement('div');
  box.className = 'ai-message';
  const title = document.createElement('strong');
  title.textContent = role === 'user' ? '我的问题' : 'DeepSeek 分析（模型建议）';
  const body = document.createElement('div');
  body.className = 'ai-answer';
  body.textContent = text;
  box.append(title, body);
  messages.append(box);
}
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (busy || !form.reportValidity()) return;
  const text = question.value.trim();
  if (!text) return;
  busy = true;
  form.querySelectorAll('button').forEach(button => { button.disabled = true; });
  statusLine.textContent = '正在请求 DeepSeek，通常需要数秒至一分钟，请勿重复点击…';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 70000);
  try {
    const body = new URLSearchParams(new FormData(form));
    body.set('history', JSON.stringify(history.slice(-6)));
    const response = await fetch(form.action, {method: 'POST', body, signal: controller.signal});
    if (response.redirected) { window.location.href = response.url; return; }
    if (!(response.headers.get('content-type') || '').includes('application/json')) throw new Error('会话已过期或请求无效，请刷新页面后重试。');
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '分析请求失败，请重试。');
    bubble('user', text);
    bubble('assistant', result.answer);
    history.push({role: 'user', content: text}, {role: 'assistant', content: result.answer});
    history = history.slice(-6);
    question.value = '';
    statusLine.textContent = '分析完成 · ' + result.model + (result.usage.total_tokens ? ' · 本次用量 ' + result.usage.total_tokens + ' tokens' : '');
  } catch (error) {
    statusLine.textContent = error.name === 'AbortError' ? '请求超时，请稍后再试；离线统计不受影响。' : error.message;
  } finally {
    clearTimeout(timer);
    busy = false;
    form.querySelectorAll('button').forEach(button => { button.disabled = false; });
  }
});
document.querySelectorAll('.ai-prompt').forEach(button => {
  button.addEventListener('click', () => { question.value = button.dataset.question; form.requestSubmit(); });
});
document.getElementById('ai-clear').addEventListener('click', () => { history = []; messages.replaceChildren(); statusLine.textContent = '本页对话已清空。'; });
form.elements.device_id.addEventListener('change', () => { history = []; messages.replaceChildren(); statusLine.textContent = '分析对象已切换，对话已清空。'; });
