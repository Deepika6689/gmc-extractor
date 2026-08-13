const state = { current: null };

const el = (sel) => document.querySelector(sel);
const dropzone = el('#dropzone');
const fileInput = el('#file-input');
const processing = el('#processing');
const processingLabel = el('#processing-label');
const intakeError = el('#intake-error');
const fileList = el('#file-list');
const detailPlaceholder = el('#detail-placeholder');
const detailContent = el('#detail-content');
const geminiKeyInput = el('#gemini-key-input');
const anthropicKeyInput = el('#anthropic-key-input');
const keyStatus = el('#key-status');

/* ---------------- Section definitions ---------------- */
const SECTIONS = [
  {
    key: 'room_rent_hospitalization', title: 'Room Rent & Hospitalization', index: '01',
    fields: {
      room_rent: 'Room Rent',
      icu_charges: 'ICU Charges',
      pre_hospitalization_days: 'Pre-Hospitalization (days)',
      post_hospitalization_days: 'Post-Hospitalization (days)',
    }
  },
  {
    key: 'maternity_details', title: 'Maternity Details', index: '02',
    fields: {
      nine_month_waiting_period: '9-Month Waiting Period',
      baby_day_one_cover: 'Baby Day One Cover',
      vaccination_coverage: 'Vaccination Coverage',
      normal_delivery_metro: 'Normal Delivery (Metro)',
      normal_delivery_non_metro: 'Normal Delivery (Non-Metro)',
      c_section_metro: 'C-Section (Metro)',
      c_section_non_metro: 'C-Section (Non-Metro)',
    }
  },
  {
    key: 'waiting_periods', title: 'Waiting Periods', index: '03',
    fields: {
      thirty_day_waiting_period: '30-Day Waiting Period',
      first_year_waiting_period: '1st Year Waiting Period',
      second_year_waiting_period: '2nd Year Waiting Period',
      pre_existing_diseases: 'Pre-Existing Diseases',
    }
  },
  {
    key: 'specific_benefits', title: 'Specific Benefits', index: '04',
    fields: {
      day_care_expenses: 'Day Care Expenses',
      opd_benefit: 'OPD Benefit',
      teleconsultation: 'Teleconsultation',
      pharmacy_discount: 'Pharmacy Discount',
      domiciliary_hospitalization: 'Domiciliary Hospitalization',
      annual_health_checkup: 'Annual Health Check-Up',
      modern_treatment: 'Modern Treatment',
      bariatric_treatment: 'Bariatric Treatment',
      psychiatric_treatment: 'Psychiatric Treatment',
      ayush_treatment: 'AYUSH Treatment',
      lgbtq_coverage: 'LGBTQ Coverage',
      live_in_partners: 'Live-in Partners',
      organ_donor_expenses: 'Organ Donor Expenses',
    }
  },
  {
    key: 'infertility_and_ambulance', title: 'Infertility & Ambulance', index: '05',
    fields: {
      infertility_treatment_surrogacy: 'Infertility Treatment & Surrogacy',
      ambulance_charges: 'Ambulance Charges',
      air_ambulance_charges: 'Air Ambulance Charges',
    }
  },
  {
    key: 'buffer_and_waiver', title: 'Buffer & Waiver', index: '06',
    fields: {
      corporate_buffer_disease_wise_capping: 'Corporate Buffer (Disease-wise Capping)',
    }
  },
];

function statusClass(status) {
  if (!status) return 'none';
  const s = status.toLowerCase();
  if (s === 'covered') return 'covered';
  if (s === 'not covered') return 'not-covered';
  if (s === 'waived off') return 'waived';
  if (s === 'applied') return 'applied';
  return 'none';
}

function stubBorderClass(status) {
  const c = statusClass(status);
  if (c === 'covered') return 'status-covered';
  if (c === 'not-covered') return 'status-not-covered';
  if (c === 'waived') return 'status-waived';
  if (c === 'applied') return 'status-applied';
  return '';
}

function renderStub(label, field) {
  field = field || {};
  const status = field.status || null;
  const limit = field.limit || null;
  const rawText = field.raw_text || null;
  const page = field.source_page;

  const stub = document.createElement('div');
  stub.className = `stub ${stubBorderClass(status)}`;

  const top = document.createElement('div');
  top.className = 'stub-top';
  const labelEl = document.createElement('div');
  labelEl.className = 'stub-label';
  labelEl.textContent = label;
  top.appendChild(labelEl);
  if (page) {
    const tag = document.createElement('span');
    tag.className = 'stub-page-tag';
    tag.textContent = `p.${page}`;
    top.appendChild(tag);
  }
  stub.appendChild(top);

  const statusEl = document.createElement('span');
  statusEl.className = `stub-status ${statusClass(status)}`;
  statusEl.textContent = status || 'Not found';
  stub.appendChild(statusEl);

  const limitEl = document.createElement('div');
  limitEl.className = limit ? 'stub-limit' : 'stub-limit empty';
  limitEl.textContent = limit || 'no limit stated';
  stub.appendChild(limitEl);

  if (rawText) {
    const toggle = document.createElement('button');
    toggle.className = 'stub-quote-toggle';
    toggle.textContent = 'view source clause';
    const quote = document.createElement('div');
    quote.className = 'stub-quote hidden';
    quote.textContent = `"${rawText}"`;
    toggle.addEventListener('click', () => {
      quote.classList.toggle('hidden');
      toggle.textContent = quote.classList.contains('hidden') ? 'view source clause' : 'hide source clause';
    });
    stub.appendChild(toggle);
    stub.appendChild(quote);
  }

  return stub;
}

function metaCell(label, value) {
  const cell = document.createElement('div');
  cell.className = 'meta-cell';
  const l = document.createElement('div');
  l.className = 'mc-label';
  l.textContent = label;
  const v = document.createElement('div');
  v.className = value ? 'mc-value' : 'mc-value empty';
  v.textContent = value || '—';
  cell.appendChild(l);
  cell.appendChild(v);
  return cell;
}

function renderDetail(data) {
  detailContent.innerHTML = '';
  detailPlaceholder.classList.add('hidden');
  detailContent.classList.remove('hidden');

  const meta = data.policy_metadata || {};
  const demo = data.demographics || {};
  const em = data.extraction_meta || {};

  const header = document.createElement('div');
  header.className = 'doc-header';
  const title = document.createElement('div');
  title.className = 'doc-title';
  title.textContent = data.source_file || 'Untitled document';
  header.appendChild(title);

  const metaRow = document.createElement('div');
  metaRow.className = 'doc-meta-row';
  const engineLabel = em.engine_used || em.engine || 'unknown';
  metaRow.innerHTML = `
    <span>Engine: <b>${engineLabel}</b></span>
    <span>Pages: <b>${em.page_count ?? '—'}</b></span>
    <span>OCR pages: <b>${em.ocr_pages ?? 0}</b></span>
    <span>Processed in: <b>${em.elapsed_seconds ?? '—'}s</b></span>
  `;
  header.appendChild(metaRow);
  detailContent.appendChild(header);

  if (em.llm_error) {
    const warn = document.createElement('div');
    warn.className = 'intake-error';
    warn.style.marginBottom = '20px';
    warn.textContent = `LLM extraction failed, fell back to rules engine: ${em.llm_error}`;
    detailContent.appendChild(warn);
  }

  const metaGrid = document.createElement('div');
  metaGrid.className = 'metadata-grid';
  metaGrid.appendChild(metaCell('Insurer', meta.insurer_name));
  metaGrid.appendChild(metaCell('Existing TPA', meta.existing_tpa));
  metaGrid.appendChild(metaCell('Policy Number', meta.policy_number));
  metaGrid.appendChild(metaCell('Inception / Renewal Date', meta.inception_or_renewal_date));
  metaGrid.appendChild(metaCell('Policy End Date', meta.policy_end_date));
  metaGrid.appendChild(metaCell('Policy Tenure', meta.policy_tenure));
  metaGrid.appendChild(metaCell('Inception Premium', meta.inception_premium));
  metaGrid.appendChild(metaCell('Family Structure', meta.family_structure));
  metaGrid.appendChild(metaCell('Total Employees', demo.total_employees));
  metaGrid.appendChild(metaCell('Total Spouses', demo.total_spouses));
  metaGrid.appendChild(metaCell('Total Children', demo.total_children));
  metaGrid.appendChild(metaCell('Parents / Parents-in-law', demo.total_parents_or_parents_in_law));
  metaGrid.appendChild(metaCell('Total Lives Covered', demo.total_lives_covered));
  detailContent.appendChild(metaGrid);

  if (meta.sum_insured_tiers && meta.sum_insured_tiers.length) {
    const sec = document.createElement('div');
    sec.className = 'section-block';
    const t = document.createElement('div');
    t.className = 'section-title';
    t.innerHTML = `<span class="st-index">SI</span><span>Sum Insured Tiers</span>`;
    sec.appendChild(t);
    const grid = document.createElement('div');
    grid.className = 'stub-grid';
    meta.sum_insured_tiers.forEach(tier => {
      const stub = document.createElement('div');
      stub.className = 'stub';
      stub.innerHTML = `<div class="stub-limit">${tier.sum_insured || '—'}</div>
                         <div class="stub-label">${tier.applicable_to || 'applies to: unspecified'}</div>`;
      grid.appendChild(stub);
    });
    sec.appendChild(grid);
    detailContent.appendChild(sec);
  }

  SECTIONS.forEach(section => {
    const sectionData = data[section.key] || {};
    const block = document.createElement('div');
    block.className = 'section-block';

    const t = document.createElement('div');
    t.className = 'section-title';
    t.innerHTML = `<span class="st-index">${section.index}</span><span>${section.title}</span>`;
    block.appendChild(t);

    const grid = document.createElement('div');
    grid.className = 'stub-grid';
    Object.entries(section.fields).forEach(([fieldKey, label]) => {
      grid.appendChild(renderStub(label, sectionData[fieldKey]));
    });
    block.appendChild(grid);
    detailContent.appendChild(block);
  });
}

function renderFileList(items) {
  fileList.innerHTML = '';
  if (!items.length) {
    fileList.innerHTML = '<li class="file-list-empty">No files processed yet.</li>';
    return;
  }
  items.forEach(item => {
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.className = 'file-item' + (state.current === item.file ? ' active' : '');
    const pillClass = (item.engine === 'gemini' || item.engine === 'anthropic') ? 'pill-llm' : 'pill-rules';
    btn.innerHTML = `
      <span class="fi-name">${item.file}</span>
      <span class="fi-meta">
        <span>${item.insurer || 'insurer unknown'}</span>
        <span class="pill ${pillClass}">${item.engine || '—'}</span>
      </span>`;
    btn.addEventListener('click', () => openFile(item.file));
    li.appendChild(btn);
    fileList.appendChild(li);
  });
}

async function refreshList() {
  const res = await fetch('/api/results');
  const items = await res.json();
  renderFileList(items);
}

async function openFile(name) {
  state.current = name;
  const res = await fetch(`/api/results/${encodeURIComponent(name)}`);
  const data = await res.json();
  renderDetail(data);
  refreshList();
}

async function uploadFile(file) {
  intakeError.classList.add('hidden');
  processing.classList.remove('hidden');
  dropzone.classList.add('hidden');
  processingLabel.textContent = `Reading ${file.name}…`;

  const form = new FormData();
  form.append('file', file);

  try {
    const res = await fetch('/api/upload', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Upload failed');
    state.current = data.source_file ? data.source_file.replace(/\.pdf$/i, '') : null;
    renderDetail(data);
    await refreshList();
  } catch (e) {
    intakeError.textContent = e.message;
    intakeError.classList.remove('hidden');
  } finally {
    processing.classList.add('hidden');
    dropzone.classList.remove('hidden');
  }
}

/* ---------------- Wiring ---------------- */
dropzone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => {
  if (e.target.files.length) uploadFile(e.target.files[0]);
});
['dragover', 'dragenter'].forEach(evt =>
  dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.add('drag-over'); })
);
['dragleave', 'drop'].forEach(evt =>
  dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.remove('drag-over'); })
);
dropzone.addEventListener('drop', (e) => {
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file);
});

el('#refresh-btn').addEventListener('click', refreshList);

el('#gemini-key-btn').addEventListener('click', async () => {
  const key = geminiKeyInput.value.trim();
  await fetch('/api/set-key', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: 'gemini', api_key: key }),
  });
  geminiKeyInput.value = '';
  checkKeyStatus();
});

el('#anthropic-key-btn').addEventListener('click', async () => {
  const key = anthropicKeyInput.value.trim();
  await fetch('/api/set-key', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: 'anthropic', api_key: key }),
  });
  anthropicKeyInput.value = '';
  checkKeyStatus();
});

async function checkKeyStatus() {
  const res = await fetch('/api/key-status');
  const data = await res.json();
  if (data.gemini) {
    keyStatus.textContent = 'Gemini key active — uploads use free-tier LLM extraction.';
    keyStatus.className = 'key-status ok';
  } else if (data.anthropic) {
    keyStatus.textContent = 'Anthropic key active — uploads use paid LLM extraction.';
    keyStatus.className = 'key-status ok';
  } else {
    keyStatus.textContent = 'No key set — uploads will use rules-only extraction.';
    keyStatus.className = 'key-status warn';
  }
}

checkKeyStatus();
refreshList();