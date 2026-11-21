/* DRHP Contact Screener · FinDeependence
   Reads data/index.json, data/companies/<key>.json and data/outreach.json (written by the GitHub Actions pipeline).
   Follow-up stage / next date / notes for each outreach contact are kept in this browser (localStorage) with backup/restore. */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const STAGES = ['Not contacted', 'Mailed', 'Replied', 'Call scheduled', 'Meeting done', 'Pre-IPO discussion', 'Anchor discussion', 'Invested', 'Not interested'];
  const NOTES_KEY = 'fd-drhp-followups-v1';
  const state = { index: [], cache: {}, sel: null, outreach: [], view: 'drhp', cview: 'brlm' };

  const toast = (m, err) => { const t = $('#toast'); t.textContent = m; t.className = 'show' + (err ? ' err' : ''); clearTimeout(t._h); t._h = setTimeout(() => (t.className = ''), 2600); };
  const getJSON = async (u) => { const r = await fetch(u + (u.includes('?') ? '&' : '?') + 't=' + Date.now()); if (!r.ok) throw new Error(u + ' ' + r.status); return r.json(); };
  const loadNotes = () => { try { return JSON.parse(localStorage.getItem(NOTES_KEY) || '{}'); } catch { return {}; } };
  const saveNotes = (n) => { try { localStorage.setItem(NOTES_KEY, JSON.stringify(n)); } catch { toast('Browser storage is blocked: notes not saved', true); } };
  let notes = loadNotes();

  const cr = (v) => v == null ? '–' : Math.abs(v) >= 1000 ? v.toLocaleString('en-IN', { maximumFractionDigits: 0 }) : v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtRatio = (v, f) => v == null ? '–' : f === 'pct' ? (v * 100).toFixed(1) + '%' : f === 'x' ? v.toFixed(2) + 'x' : f === 'days' ? Math.round(v) + ' d' : cr(v);
  const dot = (s, tip) => s ? `<span class="dot ${s}" title="${esc(tip || s)}"></span>` : '';
  const fmtDate = (d) => d ? new Date(d.length === 10 ? d + 'T00:00:00' : d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '–';
  const telLink = (p) => `<a href="tel:${esc(p.replace(/[^\d+]/g, ''))}">${esc(p)}</a>`;
  const waLink = (p) => { const d = p.replace(/\D/g, ''); return d.length >= 10 ? ` · <a href="https://wa.me/${d.length === 10 ? '91' + d : d}" target="_blank" rel="noopener">WhatsApp</a>` : ''; };
  const mail = (e) => `<a href="mailto:${esc(e)}">${esc(e)}</a>`;

  // ---------------------------------------------------------------- tabs
  $('#tabs').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-v]'); if (!b) return;
    state.view = b.dataset.v;
    document.querySelectorAll('#tabs button').forEach((x) => x.classList.toggle('on', x === b));
    document.querySelectorAll('section.view').forEach((s) => (s.hidden = s.id !== 'v-' + state.view));
    if (state.view === 'outreach') renderOutreach();
    if (state.view === 'contacts') renderContacts();
  });

  // ---------------------------------------------------------------- DRHP list + detail
  function renderList() {
    const q = $('#q').value.trim().toLowerCase(), board = $('#boardFilter').value;
    const rows = state.index.filter((c) => (!board || c.board === board) &&
      (!q || [c.company, ...(c.promoters || []), ...(c.brlms || [])].join(' ').toLowerCase().includes(q)));
    $('#list').innerHTML = rows.length ? rows.map((c) => {
      const l = c.latest || {}, rev = l.revenue && l.revenue.v != null ? `Rev ₹${cr(l.revenue.v)} cr (${l.fy})` : '';
      const sent = state.outreach.some((o) => o.company_key === c.key && o.status === 'sent');
      return `<button class="ipo-btn${state.sel === c.key ? ' sel' : ''}" data-k="${esc(c.key)}">
        <span class="nm">${esc(c.company)} <span class="pill ${c.board === 'SME' ? 'SME' : 'MB'}">${esc(c.board || '')}</span>${sent ? '<span class="pill ok">Mailed</span>' : ''}</span>
        <span class="sub">${esc(c.source)} · ${fmtDate(c.filed_on)}${rev ? ' · ' + rev : ''}</span></button>`;
    }).join('') : '<p class="muted">No DRHPs match.</p>';
  }
  $('#list').addEventListener('click', (e) => { const b = e.target.closest('button[data-k]'); if (b) select(b.dataset.k); });
  $('#q').addEventListener('input', renderList);
  $('#boardFilter').addEventListener('change', renderList);

  async function select(key) {
    state.sel = key; renderList();
    const d = $('#detail'); d.innerHTML = '<p class="muted">Loading…</p>';
    try {
      const c = state.cache[key] || (state.cache[key] = await getJSON(`data/companies/${encodeURIComponent(key)}.json`));
      renderDetail(c);
    } catch (e) { d.innerHTML = `<p class="muted">Could not load this company (${esc(e.message)}).</p>`; }
  }

  function contactCard(lbl, who, lines, src) {
    return `<div class="card"><span class="lbl">${esc(lbl)}</span><span class="who">${who}</span>${lines.filter(Boolean).map((l) => `<span class="line">${l}</span>`).join('')}${src ? `<span class="src">${esc(src)}</span>` : ''}</div>`;
  }

  function renderDetail(c) {
    const f = c.financials || {};
    const sentRows = state.outreach.filter((o) => o.company_key === c.key);
    const facts = [];
    if (f.ok) {
      const j = f.periods.findIndex((p) => !p.stub), fy = f.periods[j] ? f.periods[j].label : '';
      const it = (k) => f.items[k] && f.items[k].values[j], ra = (k) => f.ratios[k] && f.ratios[k].values[j];
      facts.push(['Revenue ' + fy, it('revenue') != null ? '₹' + cr(it('revenue')) + ' cr' : '–'],
        ['PAT ' + fy, it('pat') != null ? '₹' + cr(it('pat')) + ' cr' : '–'],
        ['EBITDA margin', fmtRatio(ra('EBITDA margin'), 'pct')], ['RoNW', fmtRatio(ra('RoNW (closing)'), 'pct')],
        ['Debt / Equity', fmtRatio(ra('Debt / Equity'), 'x')], ['Revenue growth', fmtRatio(ra('Revenue growth'), 'pct')]);
    }
    const docLink = c.doc_url || c.page_url;
    const cgLink = c.via && c.page_url ? `<a class="btn" href="${esc(c.page_url)}" target="_blank" rel="noopener">Chittorgarh ↗</a>` : '';
    let h = `<div class="panel-head"><div><h2>${esc(c.company)} <span class="pill ${c.board === 'SME' ? 'SME' : 'MB'}">${esc(c.board)}</span>
      ${f.core_verified ? '<span class="pill ok">Figures cross-checked</span>' : '<span class="pill warn">Check figures</span>'}
      ${c.pre_ipo_placement ? `<span class="pill teal">Pre-IPO placement${c.pre_ipo_limit_pct ? ' ≤' + c.pre_ipo_limit_pct + '%' : ''}</span>` : ''}</h2>
      <p class="muted">${esc(c.document_type || 'DRHP')}${c.document_date ? ' dated ' + esc(c.document_date) : ''} · filed with ${esc(c.source)}${c.also_on && c.also_on.length ? ' (also on ' + esc(c.also_on.join(', ')) + ')' : ''} on ${fmtDate(c.filed_on)} · ${c.pages || '?'} pages
      ${c.exchange ? ' · listing: ' + esc(c.exchange) : ''}</p></div>
      <div class="row">${docLink ? `<a class="btn" href="${esc(docLink)}" target="_blank" rel="noopener">Open DRHP ↗</a>` : ''}${cgLink}${c.website ? `<a class="btn" href="${esc(/^https?:/.test(c.website) ? c.website : 'https://' + c.website)}" target="_blank" rel="noopener">Website ↗</a>` : ''}</div></div>`;
    if (c.warnings && c.warnings.length) h += `<div class="warnbox">${c.warnings.map(esc).join('<br>')}</div>`;
    if (facts.length) h += `<div class="facts">${facts.map(([k, v]) => `<div class="fact"><small>${esc(k)}</small><b>${v}</b></div>`).join('')}</div>`;

    h += `<h3 class="sec">Business</h3>`;
    h += c.business_summary ? `<p class="biz">${esc(c.business_summary)}</p>` : '';
    if (c.business && c.business.text) h += `<p class="biz-raw">DRHP, page ${c.business.page}: “${esc(c.business.text)}”</p>`;

    // contacts
    h += `<h3 class="sec">Promoters &amp; contacts</h3><div class="cards">`;
    (c.promoters || []).forEach((p) => {
      h += contactCard('Promoter', esc(p.name), [p.designation ? esc(p.designation) : '', ...(p.emails || []).map(mail), !(p.emails || []).length ? '<span class="muted">Personal email not printed in DRHP</span>' : '']);
    });
    if (c.cs) h += contactCard(c.via ? 'Company contact (compliance)' : 'Company Secretary & Compliance Officer', esc(c.cs.name || c.company), [...(c.cs.emails || []).map(mail), ...(c.cs.phones || []).map((p) => telLink(p) + waLink(p))], `DRHP page ${c.cs.page}`);
    (c.brlms || []).forEach((b) => {
      h += contactCard('Book Running Lead Manager', esc(b.name || 'BRLM'), [
        b.contact_persons && b.contact_persons.length ? 'Contact: <b>' + b.contact_persons.map(esc).join(', ') + '</b>' : '',
        ...(b.emails || []).map(mail), ...(b.phones || []).map((p) => telLink(p) + waLink(p)),
        b.grievance_emails && b.grievance_emails.length ? '<span class="muted">Grievance: ' + b.grievance_emails.map(esc).join(', ') + '</span>' : '',
        b.website ? esc(b.website) : '', b.sebi_reg ? '<span class="mono small">' + esc(b.sebi_reg) + '</span>' : ''], `DRHP page ${b.page}`);
    });
    if (c.registrar) h += contactCard('Registrar to the Offer', esc(c.registrar.name || '–'), [
      c.registrar.contact_persons && c.registrar.contact_persons.length ? 'Contact: ' + c.registrar.contact_persons.map(esc).join(', ') : '',
      ...(c.registrar.emails || []).slice(0, 2).map(mail), ...(c.registrar.phones || []).map(telLink)], `DRHP page ${c.registrar.page}`);
    h += `</div>`;
    if (c.via) h += `<p class="small muted">Via ${esc(c.via)}${c.status ? ' · ' + esc(c.status) : ''}${c.industry ? ' · ' + esc(c.industry) : ''}${c.issue_size ? ' · Issue: ' + esc(c.issue_size) : ''}${c.address ? '<br>' + esc(c.address) : ''}</p>`;
    if (c.cin) h += `<p class="small muted">CIN ${esc(c.cin)}${c.icdr_regulation ? ' · ICDR Regulation ' + esc(c.icdr_regulation) : ''}${c.fresh_issue ? ' · Fresh issue' : ''}${c.ofs ? ' · Offer for sale' : ''}</p>`;

    // financials
    if (f.ok) {
      const per = f.periods;
      h += `<h3 class="sec">Restated financials (₹ crore)</h3>
        <div class="legend"><span><span class="dot verified"></span> cross-checked</span><span><span class="dot unverified"></span> read from DRHP, not independently confirmed</span><span><span class="dot mismatch"></span> check failed: verify in DRHP</span><span>Hover a figure for the check and DRHP page. In the DRHP: ₹ ${esc(f.unit_in_drhp || '?')}.</span></div>`;
      const order = ['revenue', 'other_income', 'total_income', 'total_expenses', 'finance_cost', 'depreciation', 'pbt', 'tax', 'pat', 'eps_basic', 'eps_diluted',
        'total_assets', 'share_capital', 'other_equity', 'total_equity', 'borrowings', 'current_assets', 'current_liabilities', 'trade_receivables', 'inventories', 'cash', 'cfo', 'cfi', 'cff'];
      h += `<div class="tbl"><table><thead><tr><th>Particulars</th>${per.map((p) => `<th class="num">${esc(p.label)}${p.stub ? '*' : ''}</th>`).join('')}<th>Page</th></tr></thead><tbody>`;
      order.forEach((k) => {
        const it = f.items[k]; if (!it) return;
        h += `<tr><td title="${esc(it.drhp_label)}">${esc(it.label)}</td>${it.values.map((v, j) => `<td class="num"><span class="v" title="${esc((it.notes[j] || []).join('; ') || it.status[j])}">${k.startsWith('eps') ? (v == null ? '–' : v.toFixed(2)) : cr(v)}</span>${dot(it.status[j])}</td>`).join('')}<td class="mono small">${it.page || ''}</td></tr>`;
      });
      h += `</tbody></table></div>`;
      if (per.some((p) => p.stub)) h += `<p class="small muted">* Interim period, not annualised.</p>`;
      h += `<h3 class="sec">Ratios (computed from the restated statements)</h3><div class="tbl"><table><thead><tr><th>Ratio</th>${per.map((p) => `<th class="num">${esc(p.label)}</th>`).join('')}<th>Formula</th></tr></thead><tbody>`;
      Object.entries(f.ratios).forEach(([k, r]) => {
        h += `<tr><td>${esc(k)}</td>${r.values.map((v, j) => `<td class="num"><span class="v" title="${esc(((r.notes || [])[j] || []).join('; ') || r.status[j] || '')}">${fmtRatio(v, r.fmt)}</span>${dot(r.status[j])}</td>`).join('')}<td class="wrap small muted">${esc(r.formula)}</td></tr>`;
      });
      h += `</tbody></table></div>`;
      if (f.kpi_stated && f.kpi_stated.length) {
        const kp = f.kpi_periods || [];
        h += `<details class="blk"><summary>KPIs as stated in the DRHP (“Basis for Offer Price”, page ${f.kpi_page})<span class="muted small">${f.kpi_stated.length} rows</span></summary><div class="tbl"><table><thead><tr><th>KPI</th>${kp.map((p) => `<th class="num">${esc(p.label)}</th>`).join('')}</tr></thead><tbody>${f.kpi_stated.map((r) => `<tr><td class="wrap">${esc(r.label)}</td>${(r.raw || []).map((x) => `<td class="num">${esc(x ?? '–')}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`;
      }
      if (f.checks && f.checks.length) {
        h += `<details class="blk"><summary>Accounting checks<span class="muted small">${f.checks.filter((x) => x.ok).length}/${f.checks.length} passed</span></summary><div class="tbl"><table><thead><tr><th>Period</th><th>Check</th><th class="num">Computed</th><th class="num">Printed</th><th>Result</th></tr></thead><tbody>${f.checks.map((x) => `<tr><td>${esc(x.period)}</td><td>${esc(x.check)}</td><td class="num">${cr(x.lhs)}</td><td class="num">${cr(x.rhs)}</td><td>${x.ok ? '<span class="pill ok">OK</span>' : x.soft ? '<span class="pill warn">Info</span>' : '<span class="pill bad">Fail</span>'}</td></tr>`).join('')}</tbody></table></div></details>`;
      }
    } else {
      h += `<h3 class="sec">Financials</h3><p class="muted">${esc(f.reason || 'Not available')}</p>`;
      const x = f.external;
      if (x && x.rows && x.rows.length) {
        h += `<div class="tbl"><table><thead><tr><th>${esc(x.source)} snapshot (${esc(x.unit)})</th>${x.periods.map((p) => `<th class="num">${esc(p)}</th>`).join('')}</tr></thead><tbody>` +
          x.rows.map((r) => `<tr><td>${esc(r.label)}</td>${x.periods.map((_, j) => `<td class="num">${r.values[j] == null ? '–' : cr(r.values[j])}<span class="dot unverified" title="As published by ${esc(x.source)}; not cross-checked"></span></td>`).join('')}</tr>`).join('') +
          `</tbody></table></div><p class="small muted">Shown for reference only and never quoted in emails. Open the DRHP for the restated statements.</p>`;
      }
    }

    // emails
    h += `<h3 class="sec">Introduction email${(c.emails || []).length > 1 ? 's' : ''}</h3>`;
    if (!(c.emails || []).length) h += `<p class="muted">No recipient found.</p>`;
    (c.emails || []).forEach((m, i) => {
      const st = sentRows.filter((o) => m.to.includes(o.email));
      const s = st.length ? st[0] : null;
      h += `<div class="mailbox"><div class="mhead"><span><b>To:</b> ${m.to.map(esc).join(', ')} <span class="pill ${s && s.status === 'sent' ? 'ok' : s && s.status === 'failed' ? 'bad' : 'warn'}">${esc(s ? s.status : 'draft')}</span>${s && s.sent_at ? ' <span class="muted small">' + fmtDate(s.sent_at) + '</span>' : ''}</span>
        <span><b>Recipient:</b> ${esc({ promoter: 'Promoters', brlm: 'BRLM – ' + (m.brlm || ''), company: 'Company Secretary / IR' }[m.variant])}${m.names && m.names.length ? ' · ' + m.names.map(esc).join(', ') : ''}</span>
        <span><b>Subject:</b> ${esc(m.subject)}</span></div><iframe title="Email preview ${i + 1}" sandbox="" data-i="${i}"></iframe></div>`;
    });
    $('#detail').innerHTML = h;
    document.querySelectorAll('#detail iframe[data-i]').forEach((fr) => { fr.srcdoc = c.emails[+fr.dataset.i].html.replace(/cid:pcvf-logo/g, 'pcvf_logo.png'); });
  }

  // ---------------------------------------------------------------- outreach report
  STAGES.forEach((s) => $('#oStage').insertAdjacentHTML('beforeend', `<option>${esc(s)}</option>`));
  const note = (id) => notes[id] || {};
  const stageOf = (o) => note(o.id).stage || (o.status === 'sent' ? 'Mailed' : 'Not contacted');
  const today = () => new Date().toISOString().slice(0, 10);

  function outreachRows() {
    const q = $('#oQ').value.trim().toLowerCase(), st = $('#oSt').value, stage = $('#oStage').value, board = $('#oBoard').value, due = $('#oDue').checked;
    return state.outreach.filter((o) => (!st || o.status === st) && (!board || o.board === board) && (!stage || stageOf(o) === stage) &&
      (!due || (note(o.id).next && note(o.id).next <= today())) &&
      (!q || [o.company, o.organisation, o.email, ...(o.names || []), ...(o.promoters || [])].join(' ').toLowerCase().includes(q)))
      .sort((a, b) => (b.sent_at || b.created_at || '').localeCompare(a.sent_at || a.created_at || ''));
  }

  function renderOutreach() {
    const all = state.outreach, sent = all.filter((o) => o.status === 'sent');
    const cos = new Set(state.index.map((c) => c.key)).size;
    const replied = all.filter((o) => ['Replied', 'Call scheduled', 'Meeting done', 'Pre-IPO discussion', 'Anchor discussion', 'Invested'].includes(stageOf(o))).length;
    const dueN = all.filter((o) => note(o.id).next && note(o.id).next <= today()).length;
    $('#oTiles').innerHTML = [['DRHPs screened', cos], ['Mails sent', sent.length], ['Companies mailed', new Set(sent.map((o) => o.company_key)).size],
      ['Awaiting approval', all.filter((o) => o.status === 'awaiting approval').length], ['Replies / meetings', replied], ['Follow-ups due', dueN]]
      .map(([k, v]) => `<div class="fact"><small>${k}</small><b>${v}</b></div>`).join('');
    const rows = outreachRows();
    $('#oTable').innerHTML = `<thead><tr><th>Date</th><th>Company</th><th>Sent to</th><th>Role / firm</th><th>Email &amp; phone</th><th>Promoters</th><th>Mail</th><th>Stage</th><th>Next follow-up</th><th>Notes</th></tr></thead><tbody>` +
      (rows.length ? rows.map((o) => {
        const n = note(o.id), isDue = n.next && n.next <= today();
        return `<tr class="${isDue ? 'due' : ''}" data-id="${esc(o.id)}">
          <td>${fmtDate(o.sent_at || o.created_at)}</td>
          <td class="wrap"><a class="go" href="#" data-k="${esc(o.company_key)}">${esc(o.company)}</a><br><span class="pill ${o.board === 'SME' ? 'SME' : 'MB'}">${esc(o.board || '')}</span> <span class="muted small">DRHP ${fmtDate(o.filed_on)}</span></td>
          <td class="wrap"><b>${(o.names || []).map(esc).join(', ') || '–'}</b></td>
          <td class="wrap">${esc(o.role)}<br><span class="muted small">${esc(o.organisation || '')}</span></td>
          <td class="wrap">${mail(o.email)}${(o.phones || []).map((p) => '<br>' + telLink(p) + waLink(p)).join('')}</td>
          <td class="wrap small">${(o.promoters || []).map(esc).join(', ')}</td>
          <td><span class="pill ${o.status === 'sent' ? 'ok' : o.status === 'failed' ? 'bad' : 'warn'}" title="${esc(o.error || o.subject)}">${esc(o.status)}</span></td>
          <td><select class="stage" data-f="stage">${STAGES.map((s) => `<option${s === stageOf(o) ? ' selected' : ''}>${esc(s)}</option>`).join('')}</select></td>
          <td><input type="date" class="fu" data-f="next" value="${esc(n.next || '')}"></td>
          <td class="notes"><textarea data-f="text" placeholder="Call notes, ticket size, next step…">${esc(n.text || '')}</textarea></td></tr>`;
      }).join('') : '<tr><td colspan="10" class="muted">No outreach yet. Rows appear here as soon as the pipeline prepares or sends a mail.</td></tr>') + '</tbody>';
  }
  ['#oQ', '#oSt', '#oStage', '#oBoard', '#oDue'].forEach((s) => $(s).addEventListener('input', renderOutreach));
  $('#oTable').addEventListener('change', (e) => {
    const el = e.target.closest('[data-f]'); if (!el) return;
    const id = el.closest('tr').dataset.id;
    notes[id] = { ...note(id), [el.dataset.f]: el.value, updated: new Date().toISOString() };
    saveNotes(notes); toast('Saved');
    if (el.dataset.f !== 'text') renderOutreach();
  });
  $('#oTable').addEventListener('click', (e) => {
    const a = e.target.closest('a.go'); if (!a) return; e.preventDefault();
    $('#tabs button[data-v="drhp"]').click(); select(a.dataset.k);
  });
  $('#oBackup').addEventListener('click', () => download(new Blob([JSON.stringify({ app: 'fd-drhp', saved: new Date().toISOString(), notes }, null, 1)], { type: 'application/json' }), `DRHP-outreach-notes-${today()}.json`));
  $('#oRestoreBtn').addEventListener('click', () => $('#oRestore').click());
  $('#oRestore').addEventListener('change', async (e) => {
    const file = e.target.files[0]; if (!file) return;
    try { const d = JSON.parse(await file.text()); notes = { ...notes, ...(d.notes || {}) }; saveNotes(notes); renderOutreach(); toast('Notes restored'); }
    catch { toast('That file is not a notes backup', true); }
    e.target.value = '';
  });

  function download(blob, name) { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); }

  async function xlsx(name, sheets) {
    if (!window.ExcelJS) { toast('Excel library did not load', true); return; }
    const wb = new ExcelJS.Workbook(); wb.creator = 'FinDeependence';
    sheets.forEach(({ title, cols, rows }) => {
      const ws = wb.addWorksheet(title, { views: [{ state: 'frozen', ySplit: 1 }] });
      ws.columns = cols.map((c) => ({ header: c[0], key: c[1], width: c[2] || 18 }));
      rows.forEach((r) => ws.addRow(r));
      ws.getRow(1).eachCell((cell) => { cell.font = { bold: true, color: { argb: 'FFFFFFFF' } }; cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF0E2740' } }; });
      ws.autoFilter = { from: { row: 1, column: 1 }, to: { row: 1, column: cols.length } };
      ws.eachRow((row, i) => { if (i > 1) row.alignment = { vertical: 'top', wrapText: true }; });
    });
    download(new Blob([await wb.xlsx.writeBuffer()], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), name);
  }

  $('#oXlsx').addEventListener('click', () => xlsx(`DRHP-outreach-${today()}.xlsx`, [{
    title: 'Outreach', cols: [['Date', 'date', 12], ['Company', 'company', 30], ['Board', 'board', 10], ['DRHP filed', 'filed', 12], ['Sent to', 'names', 26], ['Role', 'role', 22], ['Firm', 'org', 32],
      ['Email', 'email', 32], ['Phone', 'phones', 22], ['Promoters', 'promoters', 40], ['CS email', 'cs', 28], ['Mail status', 'status', 16], ['Subject', 'subject', 50], ['Stage', 'stage', 18], ['Next follow-up', 'next', 14], ['Notes', 'notes', 50], ['DRHP link', 'doc', 40]],
    rows: outreachRows().map((o) => ({ date: (o.sent_at || o.created_at || '').slice(0, 10), company: o.company, board: o.board, filed: o.filed_on, names: (o.names || []).join(', '), role: o.role, org: o.organisation,
      email: o.email, phones: (o.phones || []).join(', '), promoters: (o.promoters || []).join(', '), cs: o.cs ? `${o.cs.name || ''} ${(o.cs.emails || []).join(', ')} ${(o.cs.phones || []).join(', ')}`.trim() : '',
      status: o.status, subject: o.subject, stage: stageOf(o), next: note(o.id).next || '', notes: note(o.id).text || '', doc: o.doc_url || '' })),
  }]));

  // ---------------------------------------------------------------- contacts directory
  async function allCompanies() {
    await Promise.all(state.index.map(async (c) => { if (!state.cache[c.key]) { try { state.cache[c.key] = await getJSON(`data/companies/${encodeURIComponent(c.key)}.json`); } catch { /* skip */ } } }));
    return state.index.map((c) => state.cache[c.key]).filter(Boolean);
  }
  function brlmDirectory(cos) {
    const firms = {};
    cos.forEach((c) => (c.brlms || []).forEach((b) => {
      const k = (b.sebi_reg || b.name || '').toLowerCase(); if (!k) return;
      const f = firms[k] || (firms[k] = { name: b.name, sebi: b.sebi_reg, website: b.website, people: new Set(), emails: new Set(), phones: new Set(), deals: [] });
      (b.contact_persons || []).forEach((p) => f.people.add(p)); (b.emails || []).forEach((e) => f.emails.add(e)); (b.phones || []).forEach((p) => f.phones.add(p));
      f.deals.push({ company: c.company, key: c.key, board: c.board, filed: c.filed_on });
    }));
    return Object.values(firms).sort((a, b) => b.deals.length - a.deals.length);
  }
  async function renderContacts() {
    $('#cTable').innerHTML = '<tbody><tr><td class="muted">Loading…</td></tr></tbody>';
    const cos = await allCompanies(), q = $('#cQ').value.trim().toLowerCase();
    if (state.cview === 'brlm') {
      const rows = brlmDirectory(cos).filter((f) => !q || [f.name, ...f.people, ...f.emails, ...f.deals.map((d) => d.company)].join(' ').toLowerCase().includes(q));
      $('#cTable').innerHTML = `<thead><tr><th>BRLM</th><th>Contact persons</th><th>Emails</th><th>Phones</th><th class="num">Deals</th><th>Companies</th></tr></thead><tbody>` +
        rows.map((f) => `<tr><td class="wrap"><b>${esc(f.name)}</b><br><span class="mono small muted">${esc(f.sebi || '')}</span>${f.website ? '<br><span class="small">' + esc(f.website) + '</span>' : ''}</td>
          <td class="wrap">${[...f.people].map(esc).join('<br>')}</td><td class="wrap">${[...f.emails].map(mail).join('<br>')}</td>
          <td class="wrap">${[...f.phones].map((p) => telLink(p) + waLink(p)).join('<br>')}</td><td class="num">${f.deals.length}</td>
          <td class="wrap small">${f.deals.map((d) => `<a class="go" href="#" data-k="${esc(d.key)}">${esc(d.company)}</a>`).join(', ')}</td></tr>`).join('') + '</tbody>';
    } else {
      const rows = cos.filter((c) => !q || [c.company, ...(c.promoters || []).map((p) => p.name), c.cs && c.cs.name].join(' ').toLowerCase().includes(q));
      $('#cTable').innerHTML = `<thead><tr><th>Company</th><th>Promoters</th><th>Company Secretary</th><th>Email</th><th>Phone</th><th>BRLMs</th><th>Website</th></tr></thead><tbody>` +
        rows.map((c) => `<tr><td class="wrap"><a class="go" href="#" data-k="${esc(c.key)}">${esc(c.company)}</a><br><span class="pill ${c.board === 'SME' ? 'SME' : 'MB'}">${esc(c.board)}</span></td>
          <td class="wrap small">${(c.promoters || []).map((p) => esc(p.name) + (p.designation ? ' <span class="muted">(' + esc(p.designation) + ')</span>' : '')).join('<br>')}</td>
          <td class="wrap">${esc(c.cs && c.cs.name || '–')}</td><td class="wrap">${((c.cs && c.cs.emails) || []).map(mail).join('<br>')}</td>
          <td class="wrap">${((c.cs && c.cs.phones) || []).map((p) => telLink(p) + waLink(p)).join('<br>')}</td>
          <td class="wrap small">${(c.brlms || []).map((b) => esc(b.name)).join('<br>')}</td><td class="small">${esc(c.website || '')}</td></tr>`).join('') + '</tbody>';
    }
  }
  $('#cViews').addEventListener('click', (e) => { const b = e.target.closest('button[data-cv]'); if (!b) return; state.cview = b.dataset.cv; document.querySelectorAll('#cViews button').forEach((x) => x.classList.toggle('on', x === b)); renderContacts(); });
  $('#cQ').addEventListener('input', renderContacts);
  $('#cTable').addEventListener('click', (e) => { const a = e.target.closest('a.go'); if (!a) return; e.preventDefault(); $('#tabs button[data-v="drhp"]').click(); select(a.dataset.k); });
  $('#cXlsx').addEventListener('click', async () => {
    const cos = await allCompanies();
    await xlsx(`DRHP-contacts-${today()}.xlsx`, [
      { title: 'BRLMs', cols: [['BRLM', 'name', 36], ['SEBI reg.', 'sebi', 16], ['Contact persons', 'people', 34], ['Emails', 'emails', 40], ['Phones', 'phones', 26], ['Website', 'web', 26], ['Deals', 'n', 8], ['Companies', 'cos', 60]],
        rows: brlmDirectory(cos).map((f) => ({ name: f.name, sebi: f.sebi, people: [...f.people].join(', '), emails: [...f.emails].join(', '), phones: [...f.phones].join(', '), web: f.website, n: f.deals.length, cos: f.deals.map((d) => d.company).join(', ') })) },
      { title: 'Companies', cols: [['Company', 'company', 32], ['Board', 'board', 10], ['DRHP filed', 'filed', 12], ['Promoters', 'promoters', 50], ['Promoter emails', 'pe', 30], ['Company Secretary', 'cs', 24], ['CS email', 'cse', 30], ['CS phone', 'csp', 18], ['BRLMs', 'brlms', 40], ['BRLM contacts', 'bc', 60], ['Registrar', 'reg', 30], ['Website', 'web', 26], ['CIN', 'cin', 24], ['DRHP link', 'doc', 40]],
        rows: cos.map((c) => ({ company: c.company, board: c.board, filed: c.filed_on, promoters: (c.promoters || []).map((p) => p.name + (p.designation ? ` (${p.designation})` : '')).join(', '),
          pe: (c.promoters || []).flatMap((p) => p.emails || []).join(', '), cs: c.cs && c.cs.name, cse: ((c.cs && c.cs.emails) || []).join(', '), csp: ((c.cs && c.cs.phones) || []).join(', '),
          brlms: (c.brlms || []).map((b) => b.name).join(', '), bc: (c.brlms || []).map((b) => `${b.name}: ${(b.contact_persons || []).join('/')} ${(b.emails || []).join(', ')} ${(b.phones || []).join(', ')}`).join(' | '),
          reg: c.registrar && c.registrar.name, web: c.website, cin: c.cin, doc: c.doc_url || c.page_url })) },
    ]);
  });

  // ---------------------------------------------------------------- about
  function renderAbout(meta) {
    $('#about').innerHTML = `<div class="panel-head"><div><h2>How it works</h2><p class="muted">Data last updated ${meta.updated_at ? new Date(meta.updated_at).toLocaleString('en-IN') : '–'}.</p></div></div>
      <div class="cards">
        <div class="card"><span class="lbl">1 · New filings</span><span class="line">Every few hours a GitHub Actions job reads SEBI's “Draft Offer Documents”, NSE's offer-document feeds (Mainboard and Emerge SME) and BSE SME, and picks up DRHPs and UDRHPs it hasn't processed yet.</span></div>
        <div class="card"><span class="lbl">2 · Extraction</span><span class="line">Each DRHP PDF is read in full. The pipeline picks up the cover page, General Information (Company Secretary, BRLMs, Registrar), promoters, the business overview, the restated financial statements and the KPI table.</span></div>
        <div class="card"><span class="lbl">3 · Cross-checks</span><span class="line">A figure is marked <span class="dot verified"></span> only when it passes an accounting identity (assets = equity + liabilities, PBT − tax = PAT, revenue + other income = total income), appears again elsewhere in the DRHP, or matches the DRHP's own KPI table. Emails quote only cross-checked figures.</span></div>
        <div class="card"><span class="lbl">4 · Introduction email</span><span class="line">Recipients: the promoters' own email if the DRHP prints one; otherwise a personalised mail to each BRLM's deal contact; otherwise the Company Secretary / IR. Each address is mailed once only. Sent from fundmanager.pcvf@gmail.com.</span></div>
        <div class="card"><span class="lbl">5 · Outreach report</span><span class="line">Every mail is logged with the company, person, role, email, phone and BRLM details. Track the stage, next follow-up and notes in the Outreach tab, and export them to Excel.</span></div>
      </div>`;
  }

  // ---------------------------------------------------------------- boot
  (async () => {
    try {
      const [idx, out] = await Promise.all([getJSON('data/index.json'), getJSON('data/outreach.json').catch(() => ({ entries: [] }))]);
      state.index = idx.companies || []; state.outreach = out.entries || [];
      renderAbout(idx); renderList();
      if (state.index.length) select(state.index[0].key); else $('#detail').innerHTML = '<div class="empty">No DRHPs yet. They appear here after the first pipeline run.</div>';
      const pend = state.outreach.filter((o) => o.status === 'awaiting approval').length;
      if (pend) { const s = $('#status'); s.hidden = false; s.textContent = `${pend} introduction mail${pend > 1 ? 's are' : ' is'} prepared and waiting. Automatic sending is off until the email wording is approved.`; }
    } catch (e) { $('#detail').innerHTML = `<p class="muted">Could not load data (${esc(e.message)}).</p>`; renderList(); }
  })();
})();
