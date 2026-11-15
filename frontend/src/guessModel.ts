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
  if (verdict === "否") return "verdict-no";
  if (verdict === "部分是" || verdict === "半对") return "verdict-partial";
  return "verdict-neutral";
}

export function roundMatches(round?: GuessRound): GuessMatch[] {
  if (round?.matches?.length) return round.matches;
  return (round?.comments ?? []).flatMap(group =>
    (group.items ?? []).map(item => ({ ...item, card_index: group.index })),
  );
}
