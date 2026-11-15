export type GuessMatch = {
  card_index?: number;
  atom_index?: number;
  text?: string;
  verdict?: string;
  status?: string;
};

export type GuessRound = {
  id?: string;
  challenge_id?: string;
  text?: string;
  attempt?: number;
  status?: string;
  created_at?: string;
  atoms?: { index: number; text: string; status: string }[];
  matches?: GuessMatch[];
  comments?: { index?: number; items?: { text?: string; verdict?: string }[] }[];
};

export type GuessCard = {
  index: number;
  cracked: boolean;
  name?: string;
  effect?: string;
  feedback?: { text?: string; verdict?: string; round?: number | string }[];
  verifies?: { id?: string; round: number; cracked: boolean; created_at?: string }[];
};

export type GuessState = {
  id: string;
  roster_id: string;
  status: string;
  guess_rounds?: GuessRound[];
  guess_cards?: GuessCard[];
  guess_credits?: number;
  guess_in_flight?: boolean;
  verify_in_flight?: boolean;
};

export function verdictClass(verdict?: string) {
  if (verdict === "是") return "verdict-yes";
  if (verdict === "否" || verdict === "失败") return "verdict-no";
  if (verdict === "部分是" || verdict === "半对") return "verdict-partial";
  return "verdict-neutral";
}

export function roundMatches(round?: GuessRound): GuessMatch[] {
  if (round?.matches?.length) return round.matches;
  return (round?.comments ?? []).flatMap(group =>
    (group.items ?? []).map(item => ({ ...item, card_index: group.index })),
  );
}

export type GuessAnswer = { cardIndex: number; label: string };
export type GuessAtom = { index: number; text: string; answers: GuessAnswer[] };
const positiveIndex = (value?: number): value is number => Number.isInteger(value) && value! > 0;

/** 分词编号是顺序真源；异步配对完成顺序不能改变行或列的位置。 */
export function guessAtoms(round: GuessRound, cards: GuessCard[]): GuessAtom[] {
  const matches = roundMatches(round);
  const atoms = new Map<number, string>();
  for (const atom of round.atoms ?? []) if (positiveIndex(atom.index)) atoms.set(atom.index, atom.text);
  if (!atoms.size) {
    for (const match of matches) {
      if (positiveIndex(match.atom_index) && match.text && !atoms.has(match.atom_index)) atoms.set(match.atom_index, match.text);
    }
  }
  if (!atoms.size) {
    // 旧 comments 没有原子编号，按猜测原文中的位置恢复，不合并重复数据视图。
    const texts = [...new Set(matches.map(m => m.text).filter((t): t is string => Boolean(t)))];
    texts.sort((a, b) => {
      const first = round.text?.indexOf(a) ?? -1;
      const second = round.text?.indexOf(b) ?? -1;
      return (first < 0 ? Infinity : first) - (second < 0 ? Infinity : second);
    });
    texts.forEach((text, index) => atoms.set(index + 1, text));
  }
  if (!atoms.size && round.text) atoms.set(1, round.text);
  const indexed = new Map<string, GuessMatch>();
  const legacy = new Map<string, GuessMatch>();
  for (const match of matches) {
    if (positiveIndex(match.atom_index)) indexed.set(`${match.atom_index}/${match.card_index}`, match);
    else legacy.set(`${match.text}/${match.card_index}`, match);
  }
  return [...atoms].sort(([a], [b]) => a - b).map(([index, text]) => ({
    index, text,
    answers: [...cards].sort((a, b) => a.index - b.index).map(card => {
      const match = indexed.get(`${index}/${card.index}`) ?? legacy.get(`${text}/${card.index}`);
      let label: string;
      if (match?.status === "failed" || (!match && round.status === "failed")) label = "失败";
      else if (match) {
        const value = match.verdict === "不能确定" ? "不确定" : match.verdict === "半对" ? "部分是" : match.verdict;
        label = ["是", "否", "部分是", "不确定"].includes(value ?? "") ? value! : "无结果";
      } else if (card.cracked) label = "已看破";
      else label = !round.status || round.status === "complete" ? "无结果" : "待判定";
      return { cardIndex: card.index, label };
    }),
  }));
}

export function cardClues(rounds: GuessRound[], card: GuessCard) {
  const clues = [...rounds].reverse().flatMap((round, index) => guessAtoms(round, [card]).map(atom => ({
    text: atom.text, verdict: atom.answers[0]?.label, round: `${round.id ?? rounds.length - index}/${atom.index}`,
  })));
  if (clues.length) return clues;
  // 只有 feedback 的旧记录，按轮次倒序，轮内保留原始顺序。
  const groups = new Map<string | number | undefined, Map<string, NonNullable<GuessCard["feedback"]>[number]>>();
  for (const item of card.feedback ?? []) {
    if (!item.text) continue;
    const group = groups.get(item.round) ?? new Map();
    group.set(item.text, item);
    groups.set(item.round, group);
  }
  return [...groups.values()].reverse().flatMap(group => [...group.values()].map(item => ({ ...item, text: item.text! })));
}

export type VerificationRow = {
  id: string; afterRound: number; createdAt?: string; answers: GuessAnswer[];
};
export type LocalVerification = { id: string; afterRound: number; complete: boolean; legacy?: boolean };

/** 检定只展示公开的布尔结果；已看破卡在后续检定中沿用已知状态。 */
export function verificationRows(cards: GuessCard[], local?: LocalVerification, inFlight = false): VerificationRow[] {
  const events = new Map<string, { afterRound: number; createdAt?: string; order: number; values: Map<number, boolean> }>();
  for (const card of cards) {
    const occurrences = new Map<number, number>();
    for (const result of card.verifies ?? []) {
      const occurrence = occurrences.get(result.round) ?? 0;
      occurrences.set(result.round, occurrence + 1);
      const id = result.id ?? `legacy:${result.round}:${occurrence}`;
      const event = events.get(id) ?? { afterRound: result.round, createdAt: result.created_at, order: occurrence, values: new Map() };
      event.values.set(card.index, result.cracked);
      events.set(id, event);
    }
  }
  if (local && !events.has(local.id)) events.set(local.id, {
    afterRound: local.afterRound, order: Infinity,
    values: new Map(local.complete && local.legacy ? cards.map(card => [card.index, card.cracked]) : []),
  });
  const known = new Set<number>();
  const ordered = [...events].sort(([, a], [, b]) => a.afterRound - b.afterRound ||
    (a.createdAt && b.createdAt ? a.createdAt.localeCompare(b.createdAt) : a.order - b.order));
  return ordered.map(([id, event], index) => ({
    id, afterRound: event.afterRound, createdAt: event.createdAt,
    answers: [...cards].sort((a, b) => a.index - b.index).map(card => {
      const result = event.values.get(card.index);
      if (result) known.add(card.index);
      const pending = (local?.id === id && !local.complete) || (inFlight && index === ordered.length - 1);
      return { cardIndex: card.index, label: known.has(card.index) ? "看破" : result === false ? "未看破" : pending ? "检定中" : "无结果" };
    }),
  }));
}
