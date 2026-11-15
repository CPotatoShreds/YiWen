import { useMatch } from "react-router-dom";
import { useAuth } from "../auth";
import { useApiQuery } from "../useApiQuery";
import type { GuessCard, GuessRound } from "../guessModel";
import type { ScenarioHistoryItem } from "../scenarioModel";
import GuessFloatingPanel from "./GuessFloatingPanel";

type Context = {
  viewer_role: string;
  roster: { character_name: string; ability_count: number };
  my_challenges: ScenarioHistoryItem[];
  my_progress?: { cracked_cards: GuessCard[]; guess_rounds?: GuessRound[]; guess_credits: number } | null;
};

/** 位于路由页面之外，同一刻印的详情、对战、记录共享窗口与草稿。 */
export default function RosterGuessLayer() {
  const { user } = useAuth();
  const match = useMatch({ path: "/scenarios/:scenarioSlug/rosters/:rosterId", end: false });
  const { scenarioSlug, rosterId } = match?.params ?? {};
  const enabled = Boolean(user && rosterId && rosterId !== "new");
  const path = `/scenarios/${scenarioSlug}/rosters/${rosterId}`;
  const context = useApiQuery<Context>(path, enabled);
  if (!enabled || context.data?.viewer_role !== "challenger") return null;
  const { roster, my_challenges, my_progress } = context.data;
  const cards = Array.from({ length: roster.ability_count }, (_, index) =>
    my_progress?.cracked_cards.find(card => card.index === index + 1) ?? { index: index + 1, cracked: false });
  return <GuessFloatingPanel key={`${scenarioSlug}/${rosterId}`} rosterPath={path}
    characterName={roster.character_name} history={my_challenges}
    rounds={my_progress?.guess_rounds ?? []} cards={cards}
    credits={my_progress?.guess_credits ?? 0} />;
}
