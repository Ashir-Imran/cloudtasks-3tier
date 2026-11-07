(() => {
  const $ = (s) => document.querySelector(s);
  const state = { token: localStorage.getItem('token'), mode: 'login', page: 1, perPage: 8, total: 0, editing: null };
  const PRI = { 1: 'Low', 2: 'Medium', 3: 'High' };
  const STATUS = { todo: 'To do', in_progress: 'In progress', done: 'Done' };

  // ---------- helpers
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'class') el.className = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) el.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid != null) el.append(kid);   // append() => text nodes, XSS-safe
    return el;
  }
  let toastTimer;
  function toast(msg, bad) {
    const t = $('#toast');
    t.textContent = msg; t.className = 'toast' + (bad ? ' bad' : ''); t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3000);
  }
  function setErr(sel, msg) { const e = $(sel); e.textContent = msg || ''; e.hidden = !msg; }

  async function api(path, opts = {}) {
    const headers = {};
    if (state.token) headers.Authorization = 'Bearer ' + state.token;
    let body;
    if (opts.form) body = opts.form;
    else if (opts.body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.body); }
    const r = await fetch('/api' + path, { method: opts.method || 'GET', headers, body });
    if (r.status === 401 && state.token && !path.startsWith('/auth/login') && !path.startsWith('/auth/register')) {
      logout(); throw new Error('Session expired, please log in again');
    }
    if (!r.ok) {
      let msg = 'Request failed (' + r.status + ')';
      try { msg = (await r.json()).error || msg; } catch (e) { /* not json */ }
      throw new Error(msg);
    }
    if (opts.raw) return r;
    return r.status === 204 ? null : r.json();
  }

  // ---------- auth
  function showAuth() {
    $('#auth-view').hidden = false; $('#app-view').hidden = true; $('#userbox').hidden = true;
  }
  function logout() {
    state.token = null; localStorage.removeItem('token'); showAuth();
  }
  async function enter() {
    try {
      const me = await api('/auth/me');
      $('#username').textContent = me.name || me.email;
      $('#auth-view').hidden = true; $('#app-view').hidden = false; $('#userbox').hidden = false;
      await refresh();
    } catch (e) { showAuth(); }
  }
  document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => {
    state.mode = tab.dataset.mode;
    document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t === tab));
    $('#name-row').hidden = state.mode !== 'register';
    $('#auth-submit').textContent = state.mode === 'login' ? 'Log in' : 'Create account';
    $('#a-pass').autocomplete = state.mode === 'login' ? 'current-password' : 'new-password';
    setErr('#auth-err', '');
  }));
  $('#auth-form').addEventListener('submit', async (e) => {
    e.preventDefault(); setErr('#auth-err', '');
    const payload = { email: $('#a-email').value, password: $('#a-pass').value };
    if (state.mode === 'register') payload.name = $('#a-name').value;
    try {
      const res = await api('/auth/' + state.mode, { method: 'POST', body: payload });
      state.token = res.token; localStorage.setItem('token', res.token);
      $('#a-pass').value = ''; await enter();
    } catch (err) { setErr('#auth-err', err.message); }
  });
  $('#logout').addEventListener('click', logout);

  // ---------- stats + list
  async function loadStats() {
    const s = await api('/stats');
    document.querySelectorAll('[data-stat]').forEach((el) => { el.textContent = s[el.dataset.stat]; });
  }
  function dueBadge(t) {
    if (!t.due_date) return null;
    const overdue = t.status !== 'done' && t.due_date < new Date().toISOString().slice(0, 10);
    return h('span', { class: 'badge' + (overdue ? ' overdue' : '') }, (overdue ? 'Overdue: ' : 'Due ') + t.due_date);
  }
  async function loadTasks() {
    const p = new URLSearchParams({ page: state.page, per_page: state.perPage });
    const q = $('#f-q').value.trim(), st = $('#f-status').value, pr = $('#f-priority').value;
    if (q) p.set('q', q); if (st) p.set('status', st); if (pr) p.set('priority', pr);
    const res = await api('/tasks?' + p);
    state.total = res.total;
    const ul = $('#tasks'); ul.replaceChildren();
    if (!res.items.length) ul.append(h('li', { class: 'empty' }, 'No tasks found. Create one to get started.'));
    res.items.forEach((t) => {
      const cb = h('input', { type: 'checkbox', 'aria-label': 'Mark done', onchange: async () => {
        try { await api('/tasks/' + t.id, { method: 'PUT', body: { status: cb.checked ? 'done' : 'todo' } }); refresh(); }
        catch (err) { toast(err.message, true); }
      } });
      cb.checked = t.status === 'done';
      ul.append(h('li', { class: 'task' + (t.status === 'done' ? ' done' : '') },
        cb,
        h('div', { class: 'main', onclick: () => openDialog(t.id) },
          h('div', { class: 'title' }, t.title),
          h('div', { class: 'meta' },
            h('span', { class: 'badge p' + t.priority }, PRI[t.priority]),
            h('span', { class: 'badge' }, STATUS[t.status]),
            dueBadge(t),
            t.attachment_count > 0 ? h('span', { class: 'badge' }, '\uD83D\uDCCE ' + t.attachment_count) : null))));
    });
    const pages = Math.max(1, Math.ceil(state.total / state.perPage));
    $('#page-info').textContent = 'Page ' + state.page + ' of ' + pages + ' (' + state.total + ' tasks)';
    $('#prev').disabled = state.page <= 1; $('#next').disabled = state.page >= pages;
  }
  async function refresh() {
    try { await Promise.all([loadStats(), loadTasks()]); } catch (e) { toast(e.message, true); }
  }
  let searchTimer;
  $('#f-q').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { state.page = 1; loadTasks().catch((e) => toast(e.message, true)); }, 300); });
  ['#f-status', '#f-priority'].forEach((s) => $(s).addEventListener('change', () => { state.page = 1; loadTasks().catch((e) => toast(e.message, true)); }));
  $('#prev').addEventListener('click', () => { state.page--; loadTasks(); });
  $('#next').addEventListener('click', () => { state.page++; loadTasks(); });

  // ---------- task dialog
  const dlg = $('#task-dialog');
  async function openDialog(id) {
    setErr('#dlg-err', ''); state.editing = id || null;
    $('#task-form').reset();
    $('#dlg-title').textContent = id ? 'Edit task' : 'New task';
    $('#dlg-delete').hidden = !id; $('#att-box').hidden = !id;
    if (id) {
      try {
        const t = await api('/tasks/' + id);
        $('#t-title').value = t.title; $('#t-desc').value = t.description;
        $('#t-pri').value = t.priority; $('#t-status').value = t.status; $('#t-due').value = t.due_date || '';
        renderAttachments(t.attachments);
      } catch (e) { toast(e.message, true); return; }
    }
    dlg.showModal();
  }
  function renderAttachments(list) {
    const ul = $('#att-list'); ul.replaceChildren();
    if (!list.length) ul.append(h('li', {}, h('span', { class: 'hint' }, 'No files yet.')));
    list.forEach((a) => ul.append(h('li', {},
      h('span', {}, a.filename + ' (' + Math.ceil(a.size_bytes / 1024) + ' KB)'),
      h('button', { type: 'button', class: 'btn ghost', onclick: () => download(a) }, 'Download'),
      h('button', { type: 'button', class: 'btn danger', onclick: async () => {
        try { await api('/attachments/' + a.id, { method: 'DELETE' }); await reloadAttachments(); refresh(); }
        catch (e) { setErr('#dlg-err', e.message); }
      } }, 'Remove'))));
  }
  async function reloadAttachments() { renderAttachments((await api('/tasks/' + state.editing)).attachments); }
  async function download(a) {
    try {
      const r = await api('/attachments/' + a.id + '/download', { raw: true });
      const url = URL.createObjectURL(await r.blob());
      const link = h('a', { href: url, download: a.filename }); document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setErr('#dlg-err', e.message); }
  }
  $('#att-file').addEventListener('change', async (e) => {
    const file = e.target.files[0]; if (!file) return;
    setErr('#dlg-err', '');
    if (file.size > 5 * 1024 * 1024) { setErr('#dlg-err', 'File is larger than 5 MB'); e.target.value = ''; return; }
    const form = new FormData(); form.append('file', file);
    try { await api('/tasks/' + state.editing + '/attachments', { method: 'POST', form }); await reloadAttachments(); refresh(); toast('File uploaded'); }
    catch (err) { setErr('#dlg-err', err.message); }
    e.target.value = '';
  });
  $('#new-task').addEventListener('click', () => openDialog(null));
  $('#dlg-cancel').addEventListener('click', () => dlg.close());
  $('#task-form').addEventListener('submit', async (e) => {
    e.preventDefault(); setErr('#dlg-err', '');
    const body = { title: $('#t-title').value, description: $('#t-desc').value, priority: Number($('#t-pri').value),
                   status: $('#t-status').value, due_date: $('#t-due').value || null };
    try {
      if (state.editing) await api('/tasks/' + state.editing, { method: 'PUT', body });
      else await api('/tasks', { method: 'POST', body });
      dlg.close(); toast('Saved'); refresh();
    } catch (err) { setErr('#dlg-err', err.message); }
  });
  $('#dlg-delete').addEventListener('click', async () => {
    if (!confirm('Delete this task and its files?')) return;
    try { await api('/tasks/' + state.editing, { method: 'DELETE' }); dlg.close(); toast('Deleted'); refresh(); }
    catch (err) { setErr('#dlg-err', err.message); }
  });

  // ---------- footer status (shows which container served you; useful for load-balancer demos)
  async function status() {
    try { $('#st-host').textContent = (await (await fetch('/api/info')).json()).hostname; }
    catch (e) { $('#st-host').textContent = 'unreachable'; }
    try {
      const r = await fetch('/api/ready'); const j = await r.json();
      $('#st-db').textContent = j.database; $('#dot-db').className = 'dot ' + (j.database === 'up' ? 'ok' : 'bad');
      $('#st-s3').textContent = j.storage; $('#dot-s3').className = 'dot ' + (j.storage === 'up' ? 'ok' : j.storage === 'down' ? 'bad' : '');
    } catch (e) { $('#st-db').textContent = 'unreachable'; $('#dot-db').className = 'dot bad'; }
  }
  status(); setInterval(status, 10000);

  if (state.token) enter(); else showAuth();
})();
