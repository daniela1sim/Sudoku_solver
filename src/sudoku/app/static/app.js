"use strict";
const $ = id => document.getElementById(id);
// Bundled practice puzzles. Descriptions are guides, not difficulty ratings.
const examples = [
  {name: 'Classic warm-up', description: 'Our original example: a starting point for practicing singles.',
    puzzle: '530070000600195000098000060800060003400803001700020006060000280000419005000080079'},
  {name: 'Box by box', description: 'A different layout for exploring rows, columns, and boxes.',
    puzzle: '003020600900305001001806400008102900700000008006708200002609500800203009005010300'},
  {name: 'Fresh perspective', description: 'Another practice grid. Take your time and reveal hints gradually.',
    puzzle: '200080300060070084030500209000105408000000000402706000301007040720040060004010003'},
  {name: 'Sparse singles practice', description: 'Only 17 starting clues, but solvable with singles. Clue count alone does not determine difficulty.',
    puzzle: '000000010400000000020000000000050407008000300001090000300400200050100000000806000'},
  {name: 'Advanced · Skyscrapers', description: 'Verified full solve using Skyscrapers, naked and hidden pairs, and locked candidates. From Peter Norvig’s top95 collection (puzzle 13).',
    puzzle: '005000987040050001007000000200048000090100000600200000300600200000009070000000500'},
  {name: 'Advanced · Empty rectangles', description: 'Verified full solve using Empty Rectangles, a naked triple, pairs, and locked candidates. From Peter Norvig’s top95 collection (puzzle 19).',
    puzzle: '023700006800060590900000700000040970307096002000000000500470000000002000080000000'},
];
let draft = Array(81).fill('0'), selected = 0, session = null, view = null;
let busy = false, playing = false, timer = null;
let catalogReady = false;
let imageReview = null;
function clearImageReview() {
  imageReview = null;
  $('image-review').hidden = true;
  $('image-confirm').checked = false;
}
const techniqueOptions = [];
function selectedTechniques() {
  return techniqueOptions.filter(item => item.input.checked && (!item.unique || $('unique').checked)).map(item => item.name);
}
function updateTechniqueOptions() {
  for (const item of techniqueOptions) item.input.disabled = busy || (item.unique && !$('unique').checked);
  $('technique-count').textContent = `· ${selectedTechniques().length} selected`;
}
async function loadTechniques() {
  try {
    const response = await fetch('/api/techniques');
    if (!response.ok) throw new Error('Could not load the technique list. Refresh to retry.');
    const entries = await response.json();
    for (const entry of entries) {
      const label = document.createElement('label'), input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = true;
      input.onchange = updateTechniqueOptions;
      label.append(input, document.createTextNode(entry.name + (entry.requires_uniqueness ? ' (requires uniqueness)' : '')));
      $('technique-options').append(label);
      techniqueOptions.push({input, name: entry.name, unique: entry.requires_uniqueness});
    }
    catalogReady = true;
    updateTechniqueOptions();
  } catch (error) { notice(error.message); }
  controls();
}
// Each new hint starts without locations, effect highlights, or an answer.
let hintLevel = 0;
const cells = [];
const label = cell => `R${cell[0] + 1}C${cell[1] + 1}`;
const index = cell => cell[0] * 9 + cell[1];

function stop() {
  playing = false;
  clearTimeout(timer);
  $('play').textContent = '▶ Play';
}
function notice(text = '', loading = false) {
  $('message').textContent = text;
  $('message').classList.toggle('busy', loading);
}
function controls() {
  for (const id of ['start', 'import', 'example', 'examples', 'clear', 'hint', 'deeper', 'apply', 'edit', 'next', 'back', 'first', 'timeline']) {
    $(id).disabled = busy;
  }
  $('start').disabled = busy || !catalogReady || (imageReview && !$('image-confirm').checked);
  $('read-image').disabled = $('puzzle-image').disabled = busy;
  $('image-confirm').disabled = busy;
  $('unique').disabled = busy;
  for (const id of ['techniques-all', 'techniques-singles', 'techniques-none']) $(id).disabled = busy || !catalogReady;
  updateTechniqueOptions();
  if (session && view && !busy) {
    $('first').disabled = $('back').disabled = view.cursor === 0;
    $('hint').disabled = view.status !== 'ready';
    const recordedNext = view.cursor < view.total;
    $('next').disabled = !recordedNext && (view.status !== 'ready' || hintLevel >= 3);
    $('next').textContent = recordedNext ? 'Next step →' : hintLevel >= 3 ? 'Apply below ↓' : 'Next hint →';
    $('next').title = recordedNext ? 'Replay the next recorded move' : 'Reveal the next hint level without changing the board';
    $('play').disabled = view.total === 0;
    $('play').title = view.total ? 'Replay your applied deductions from the beginning or current position' : 'Apply a deduction first to enable replay';
  } else $('play').disabled = busy;
}
async function request(path, body) {
  busy = true;
  controls();
  notice(path === '/api/image' ? 'Reading the puzzle image…' : 'Checking the logic…', true);
  try {
    const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed');
    notice();
    return data;
  } catch (error) {
    stop();
    notice(error.message);
    return null;
  } finally {
    busy = false;
    controls();
  }
}
function renderBoard() {
  const grid = session ? view.grid : draft.join('');
  const givens = new Set(session ? view.givens.map(index) : []);
  // A nudge must not leak the move through colors or crossed-out notes.
  const deduction = session ? (view.hint ? (hintLevel >= 2 ? view.hint : null) : view.last) : null;
  const showEffects = !view?.hint || hintLevel >= 3;
  const reasons = new Set(deduction ? deduction.premises.flatMap(p => p.cells.map(index)) : []);
  const placed = new Set(deduction && showEffects ? deduction.placements.map(m => index(m.cell)) : []);
  const removed = new Map();
  if (deduction && showEffects) for (const m of deduction.eliminations) {
    const i = index(m.cell);
    if (!removed.has(i)) removed.set(i, new Set());
    removed.get(i).add(m.digit);
  }
  cells.forEach((cell, i) => {
    cell.replaceChildren();
    cell.className = 'cell';
    cell.classList.toggle('given', givens.has(i));
    cell.classList.toggle('selected', selected === i);
    cell.classList.toggle('reason', reasons.has(i));
    cell.classList.toggle('placed', placed.has(i));
    cell.classList.toggle('eliminated', removed.has(i));
    cell.classList.toggle('image-uncertain', !session && !!imageReview?.cells[i].review);
    const digit = grid[i];
    const candidates = session ? view.candidates[i] : [];
    cell.setAttribute('aria-label', `Row ${Math.floor(i / 9) + 1}, column ${i % 9 + 1}, ${digit !== '0' ? digit : 'empty' + (candidates.length ? ', candidates ' + candidates.join(', ') : '')}`);
    if (digit !== '0') cell.textContent = digit;
    else if (session && $('notes').checked) {
      const notes = document.createElement('span');
      notes.className = 'notes';
      for (let n = 1; n <= 9; n++) {
        const item = document.createElement('span');
        if (candidates.includes(n) || removed.get(i)?.has(n)) item.textContent = n;
        if (removed.get(i)?.has(n)) item.className = 'removed';
        notes.append(item);
      }
      cell.append(notes);
    }
  });
}
function nudge(technique) {
  if (technique === 'Naked Single') return 'Look through the empty cells and compare their candidate counts. Is there a cell with no choice left to make?';
  if (technique === 'Hidden Single') return 'Pick a row, column, or box. For each missing digit, count the cells that can still contain it. Can you find a digit with only one possible home?';
  if (/Naked (Pair|Triple|Quad)/.test(technique)) return 'Compare small groups of cells in one row, column, or box. Do they share exactly enough candidates to fill those cells? What would that mean for the other cells?';
  if (/Hidden (Pair|Triple|Quad)/.test(technique)) return 'Look for a few digits whose possible positions are confined to the same small group of cells in one unit. What else could those cells contain?';
  if (/Pointing|Claiming|Locked/.test(technique)) return 'Compare a box with the rows and columns passing through it. Are all possible positions for a digit confined to their intersection?';
  if (/Wing|Swordfish|Jellyfish/.test(technique) && !/XY|XYZ|W-Wing/.test(technique)) return 'Follow one candidate across rows and columns. Look for a small set of lines whose possible positions are confined to the same crossing lines.';
  if (/Wing/.test(technique)) return 'Compare cells with only a few candidates. Consider how choosing one candidate can force a choice in another cell that shares a unit with it.';
  if (/Unique|BUG/.test(technique)) return 'Look for an almost repeating candidate pattern. Under your uniqueness assumption, consider what must prevent an interchangeable arrangement.';
  if (/ALS|Sue de Coq/.test(technique)) return 'Look for groups of cells with just one more candidate than cells. Consider how linked groups restrict one another.';
  return 'Follow the relationships between candidates. If one possibility is false, what must become true elsewhere? Look for consequences shared by the alternatives.';
}
function explain() {
  const d = view.hint || view.last;
  const preview = !!view.hint;
  const revealed = !preview || hintLevel >= 3;
  $('explanation').replaceChildren();
  $('deduction-label').textContent = preview ? `HINT ${hintLevel} OF 3 / YOUR MOVE` : (d ? 'MOST RECENT DEDUCTION' : 'A HELPING HAND');
  $('technique').textContent = preview && !revealed ? (hintLevel === 1 ? 'Something to consider' : 'Here’s where to look') : d?.technique || 'A little guidance?';
  if (preview && !revealed) {
    const p = document.createElement('p');
    p.textContent = nudge(d.technique);
    $('explanation').append(p);
    if (hintLevel === 2) {
      const focus = document.createElement('p');
      focus.textContent = `Try looking for a ${d.technique} using the highlighted cells. Work out what the pattern allows before revealing the move.`;
      $('explanation').append(focus);
    }
  } else if (d) {
    const list = document.createElement('ul');
    for (const p of d.premises) {
      const item = document.createElement('li');
      item.textContent = p.description;
      list.append(item);
    }
    $('explanation').append(list);
    for (const [key, verb] of [['placements', 'Place'], ['eliminations', 'Remove']]) {
      if (!d[key].length) continue;
      const p = document.createElement('p');
      p.className = 'effect-line';
      p.textContent = d[key].map(m => `${verb} ${m.digit} ${key === 'placements' ? 'at' : 'from'} ${label(m.cell)}`).join('; ');
      $('explanation').append(p);
    }
  } else {
    const p = document.createElement('p');
    p.textContent = 'Try the puzzle at your own pace. Ask for a gentle nudge whenever you need one; you choose how much help to reveal.';
    $('explanation').append(p);
  }
  if (view.status !== 'ready') {
    const p = document.createElement('p');
    p.textContent = view.status === 'solved' ? 'Puzzle complete. Replay any step to revisit its reasoning.'
      : view.status === 'contradiction' ? `${view.contradiction}. This final deduction exposes the contradiction. No further moves were calculated. Use Back or the timeline to inspect the deductions, or edit the clues.`
      : 'No deduction found within the available techniques and search limits. This does not establish that the puzzle is unsolvable.';
    $('explanation').append(p);
  }
  $('apply').hidden = !preview || !revealed;
  $('hint').hidden = !!view.hint;
  $('deeper').hidden = !preview || revealed;
  $('deeper').textContent = hintLevel === 1 ? 'Show where to look' : 'Reveal the deduction';
}
function render() {
  $('setup').hidden = !!session;
  for (const id of ['replay', 'deduction', 'history-card']) $(id).hidden = !session;
  $('board-help').hidden = !!session;
  $('board-label').textContent = session ? 'YOUR SOLVING SPACE' : 'YOUR PUZZLE';
  $('board-title').textContent = session ? (view.status === 'solved' ? 'Puzzle complete' : view.status === 'contradiction' ? 'Contradiction reached' : view.status === 'stuck' ? 'End of the available path' : 'Find your next move') : 'Set the starting grid';
  renderBoard();
  if (session) {
    $('position').textContent = `Step ${view.cursor} of ${view.total}`;
    $('timeline').max = view.total;
    $('timeline').value = view.cursor;
    $('count').textContent = view.cursor;
    $('history').replaceChildren();
    $('empty-history').hidden = view.cursor > 0;
    $('empty-history').textContent = view.total > 0
      ? 'No deductions applied at this position yet. Advance a step or apply a revealed hint to begin your history.'
      : 'No verified deductions were found for this position with the available techniques.';
    $('replay-help').textContent = view.total === 0
      ? 'No deductions are available from this position with the current techniques and search limits.'
      : `${view.total} deductions ready. Use Play or Next step to replay, or Give me a nudge for gradual hints. Play restarts from the beginning when you are at the latest move.`;
    view.history.forEach((name, i) => {
      const li = document.createElement('li'), button = document.createElement('button'), number = document.createElement('span');
      number.textContent = String(i + 1).padStart(2, '0');
      button.append(number, document.createTextNode(name));
      button.classList.toggle('active', i + 1 === view.cursor);
      button.onclick = () => seek(i + 1);
      li.append(button);
      $('history').append(li);
    });
    $('history').scrollTop = $('history').scrollHeight;
    explain();
    $('active-techniques').textContent = `${view.techniques.length} techniques enabled. Use Edit puzzle / start over to change your selection and rebuild the replay.`;
  }
  controls();
}
async function action(name, extra = {}) {
  if (busy || !session) return false;
  const data = await request('/api/action', {session, action: name, ...extra});
  if (!data) return false;
  view = data;
  hintLevel = name === 'hint' && view.hint ? 1 : 0;
  if (view.status !== 'ready' || (name === 'next' && view.cursor >= view.total)) stop();
  render();
  return true;
}
function seek(cursor) { stop(); return action('seek', {cursor}); }
async function tick() {
  if (!playing) return;
  if (await action('next') && playing) timer = setTimeout(tick, 850);
}
for (let i = 0; i < 81; i++) {
  const cell = document.createElement('button');
  cell.className = 'cell';
  cell.onclick = () => { selected = i; renderBoard(); };
  cell.onkeydown = event => {
    if (busy) return;
    let target = i;
    if (event.key === 'ArrowLeft') target = Math.max(0, i - 1);
    else if (event.key === 'ArrowRight') target = Math.min(80, i + 1);
    else if (event.key === 'ArrowUp') target = Math.max(0, i - 9);
    else if (event.key === 'ArrowDown') target = Math.min(80, i + 9);
    else if (!session && /^[1-9]$/.test(event.key)) {
      draft[i] = event.key;
      $('puzzle').value = draft.join('');
    } else if (!session && ['Backspace', 'Delete', '0', '.'].includes(event.key)) {
      draft[i] = '0';
      $('puzzle').value = draft.join('');
    } else return;
    if (!session && imageReview && /^[1-9]$|^Backspace$|^Delete$|^0$|^\.$/.test(event.key)) {
      imageReview.cells[i].review = false;
      $('image-confirm').checked = false;
      controls();
    }
    event.preventDefault();
    selected = target;
    renderBoard();
    cells[target].focus();
  };
  cells.push(cell);
  $('board').append(cell);
}
$('notes').onchange = renderBoard;
function loadExample() {
  clearImageReview();
  const example = examples[Number($('examples').value)];
  draft = example.puzzle.split('');
  selected = 0;
  $('puzzle').value = example.puzzle;
  notice();
  render();
}
examples.forEach((example, i) => {
  const option = document.createElement('option');
  option.value = i;
  option.textContent = `${example.name} · ${example.puzzle.replace(/0/g, '').length} clues`;
  $('examples').append(option);
});
$('examples').onchange = () => {
  $('example-description').textContent = examples[Number($('examples').value)].description;
};
$('examples').onchange();
$('example').onclick = loadExample;
$('clear').onclick = () => { clearImageReview(); draft.fill('0'); $('puzzle').value = ''; notice(); render(); };
$('import').onclick = () => {
  const text = $('puzzle').value.replace(/\s/g, '');
  if (!/^[0-9.]{81}$/.test(text)) { notice('Enter exactly 81 digits or dots. Spaces and line breaks are accepted.'); return; }
  clearImageReview();
  draft = text.replace(/\./g, '0').split('');
  notice(); render();
};
$('start').onclick = async () => {
  if (busy || (imageReview && !$('image-confirm').checked)) return;
  const data = await request('/api/start', {puzzle: draft.join(''), allow_uniqueness: $('unique').checked, techniques: selectedTechniques()});
  if (data) { session = data.session; view = data; render(); }
};
$('image-confirm').onchange = controls;
$('read-image').onclick = async () => {
  if (busy || session) return;
  const file = $('puzzle-image').files[0];
  if (!file) { notice('Choose a puzzle image first.'); return; }
  if (file.size > 8 * 1024 * 1024) { notice('Choose an image smaller than 8 MiB.'); return; }
  busy = true; controls();
  try {
    const encoded = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onerror = () => reject(new Error('Could not read the selected file.'));
      reader.readAsDataURL(file);
    });
    const data = await request('/api/image', {image: encoded});
    if (!data) return;
    imageReview = data;
    draft = data.puzzle.split('');
    $('puzzle').value = data.puzzle;
    $('image-preview').src = data.preview;
    $('image-status').textContent = `${data.warning} ${data.cells.filter(c => c.review).length} cells flagged; ${data.conflicts.length} conflicting cells.`;
    $('image-confirm').checked = false;
    $('image-review').hidden = false;
    selected = 0;
    render();
  } catch (error) { notice(error.message); }
  finally { busy = false; controls(); }
};
$('hint').onclick = () => { stop(); action('hint'); };
$('deeper').onclick = () => {
  if (busy || !view?.hint || hintLevel >= 3) return;
  hintLevel += 1;
  render();
};
$('apply').onclick = () => {
  if (!view?.hint || hintLevel < 3) return;
  stop(); action('next');
};
$('next').onclick = () => {
  if (busy) return;
  stop();
  if (view.cursor < view.total) action('next');
  else if (!view.hint) action('hint');
  else if (hintLevel < 3) { hintLevel += 1; render(); }
};
$('back').onclick = () => seek(view.cursor - 1);
$('first').onclick = () => seek(0);
$('timeline').oninput = () => seek(Number($('timeline').value));
$('play').onclick = async () => {
  if (playing) stop();
  else if (!busy && view.total > 0) {
    if (view.cursor >= view.total && !await action('seek', {cursor: 0})) return;
    playing = true;
    $('play').textContent = 'Ⅱ Pause';
    tick();
  }
};
$('edit').onclick = () => { stop(); session = null; view = null; notice(); render(); };
// Start with a playable example; custom entry remains available via Clear grid.
loadExample();
$('unique').onchange = updateTechniqueOptions;
for (const [id, predicate] of [
  ['techniques-all', () => true],
  ['techniques-singles', item => ['Naked Single', 'Hidden Single'].includes(item.name)],
  ['techniques-none', () => false],
]) $(id).onclick = () => {
  for (const item of techniqueOptions) item.input.checked = predicate(item);
  updateTechniqueOptions();
};
loadTechniques();
