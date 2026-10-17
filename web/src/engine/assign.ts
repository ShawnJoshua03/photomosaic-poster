// Which photo goes in which tile (mirrors src/mosaic_poster/assign.py).

const SPREAD_PENALTY = 15;     // squared-Lab units per previous use
const VARIETY_TOLERANCE = 60;  // near-best window, widened by the tint

/** Small fast seeded RNG, so a given seed always gives the same layout. */
export function rng(seed: number) {
  let a = seed >>> 0 || 1;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export interface AssignOptions {
  maxRepeats?: number; // 0 = automatic
  spacing?: number;    // no repeat (or look-alike) within this many tiles
  variety?: number;    // random pick among this many near-best photos
  tint?: number;
  seed?: number;
  useAll?: boolean;    // every distinct photo appears at least once
}

export interface AssignResult {
  grid: Int32Array;    // rows*cols photo indices
  uses: Int32Array;
  maxRepeats: number;
}

/**
 * cellLab: Lab per cell (3 per cell, row-major). tileLab: Lab per photo.
 * groups: look-alike group id per photo.
 */
export function assignTiles(cellLab: Float32Array, rows: number, cols: number,
  tileLab: Float32Array, groups: Int32Array, o: AssignOptions = {}): AssignResult {
  const n = tileLab.length / 3, total = rows * cols;
  const spacing = o.spacing ?? 5, variety = o.variety ?? 16, tint = o.tint ?? 0;
  const need = Math.ceil(total / n);
  let maxRepeats = o.maxRepeats ?? 0;
  if (maxRepeats <= 0) maxRepeats = Math.max(need + 1, Math.ceil((1.5 * total) / n));
  else maxRepeats = Math.max(maxRepeats, need);
  const nGroups = groups.reduce((m, g) => Math.max(m, g), 0) + 1;
  const groupCap = Math.ceil(1.5 * maxRepeats);
  const tolerance = VARIETY_TOLERANCE / Math.max(1 - Math.min(tint, 0.9), 0.1) ** 2;
  const rand = rng(o.seed ?? 1);

  const grid = new Int32Array(total).fill(-1);
  const uses = new Int32Array(n), groupUses = new Int32Array(nGroups);
  const cost = new Float64Array(n);
  const banned = new Uint8Array(n);
  const nearGroups = new Uint8Array(nGroups);

  // Visit cells in random order so no direction gets the best photos first.
  const order = new Int32Array(total);
  for (let i = 0; i < total; i++) order[i] = i;
  for (let i = total - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }

  const markNear = (r: number, c: number, radius: number) => {
    nearGroups.fill(0);
    for (let y = Math.max(0, r - radius); y <= Math.min(rows - 1, r + radius); y++) {
      for (let x = Math.max(0, c - radius); x <= Math.min(cols - 1, c + radius); x++) {
        const t = grid[y * cols + x];
        if (t >= 0) nearGroups[groups[t]] = 1;
      }
    }
  };

  for (const cell of order) {
    const r = Math.floor(cell / cols), c = cell % cols;
    const L = cellLab[cell * 3], A = cellLab[cell * 3 + 1], B = cellLab[cell * 3 + 2];
    for (let t = 0; t < n; t++) {
      const dl = tileLab[t * 3] - L, da = tileLab[t * 3 + 1] - A, db = tileLab[t * 3 + 2] - B;
      cost[t] = dl * dl + da * da + db * db + SPREAD_PENALTY * uses[t];
    }
    // Strictest rules first; relax only when nothing is left (very few photos).
    let free = 0;
    for (const [radius, useCap] of [[spacing, true], [1, true], [1, false], [0, false]] as const) {
      if (radius) markNear(r, c, radius);
      free = 0;
      for (let t = 0; t < n; t++) {
        const capped = useCap && (uses[t] >= maxRepeats || groupUses[groups[t]] >= groupCap);
        banned[t] = capped || (radius > 0 && nearGroups[groups[t]] === 1) ? 1 : 0;
        if (!banned[t]) free++;
      }
      if (free) break;
    }
    // Random pick among the k cheapest allowed photos within the tolerance window.
    const k = Math.min(variety, free);
    const best: number[] = [];
    for (let t = 0; t < n; t++) {
      if (banned[t]) continue;
      if (best.length < k) {
        best.push(t);
        best.sort((a, b) => cost[a] - cost[b]);
      } else if (cost[t] < cost[best[k - 1]]) {
        best[k - 1] = t;
        best.sort((a, b) => cost[a] - cost[b]);
      }
    }
    const pool = best.filter((t) => cost[t] <= cost[best[0]] + tolerance);
    const pick = pool[Math.floor(rand() * pool.length)];
    grid[cell] = pick;
    uses[pick]++;
    groupUses[groups[pick]]++;
  }

  if (o.useAll ?? true) {
    // Everyone looks for their own photo: give every distinct photo a spot where it
    // costs the least color accuracy, replacing only photos used more than once.
    const current = new Float64Array(total);
    for (let i = 0; i < total; i++) current[i] = dist(cellLab, i, tileLab, grid[i]);
    const membersOf: number[][] = Array.from({ length: nGroups }, () => []);
    for (let t = 0; t < n; t++) membersOf[groups[t]].push(t);
    for (let g = 0; g < nGroups; g++) {
      if (groupUses[g] > 0) continue;
      let bestD = Infinity, bestT = -1, bestCell = -1;
      for (const t of membersOf[g]) {
        for (let i = 0; i < total; i++) {
          if (uses[grid[i]] <= 1) continue;
          const d = dist(cellLab, i, tileLab, t) - current[i];
          if (d < bestD) { bestD = d; bestT = t; bestCell = i; }
        }
      }
      if (bestT < 0) break; // more distinct photos than tiles
      uses[grid[bestCell]]--;
      grid[bestCell] = bestT;
      uses[bestT]++;
      groupUses[g]++;
      current[bestCell] = dist(cellLab, bestCell, tileLab, bestT);
    }
  }
  return { grid, uses, maxRepeats };
}

function dist(cellLab: Float32Array, i: number, tileLab: Float32Array, t: number) {
  const dl = tileLab[t * 3] - cellLab[i * 3], da = tileLab[t * 3 + 1] - cellLab[i * 3 + 1],
    db = tileLab[t * 3 + 2] - cellLab[i * 3 + 2];
  return dl * dl + da * da + db * db;
}

/** Group look-alike photos by 64-bit difference hash (8 bytes each). */
export function lookAlikeGroups(hashes: Uint8Array[], maxDist = 6): Int32Array {
  const n = hashes.length, group = new Int32Array(n).fill(-1);
  let k = 0;
  for (let i = 0; i < n; i++) {
    if (group[i] >= 0) continue;
    for (let j = i; j < n; j++) {
      if (group[j] < 0 && hamming(hashes[i], hashes[j]) <= maxDist) group[j] = k;
    }
    k++;
  }
  return group;
}

function hamming(a: Uint8Array, b: Uint8Array) {
  let d = 0;
  for (let i = 0; i < a.length; i++) {
    let x = a[i] ^ b[i];
    while (x) { d += x & 1; x >>= 1; }
  }
  return d;
}
