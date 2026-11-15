import { useEffect, useId, useRef, useState, type CSSProperties, type FormEvent } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "../api";
import { roundMatches, verdictClass, type GuessCard, type GuessRound, type GuessState } from "../guessModel";
import type { ScenarioHistoryItem } from "../scenarioModel";
import { XIcon } from "./icons";
import "./GuessFloatingPanel.css";

type Props = {
  rosterPath: string;
  characterName: string;
  history: ScenarioHistoryItem[];
  rounds: GuessRound[];
  cards: GuessCard[];
  credits: number;
};

/** 只使用后端公开结果。收起窗口不会中断后台任务或丢弃本页草稿。 */
export default function GuessFloatingPanel({ rosterPath, characterName, history, rounds, cards, credits }: Props) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [selectedRound, setSelectedRound] = useState<string>();
  const [submittedText, setSubmittedText] = useState("");
  const [verifyRequested, setVerifyRequested] = useState(false);
  const [viewport, setViewport] = useState<CSSProperties>({});
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const submitLock = useRef(false);
  const inputId = useId();
  const pendingRound = [...rounds].reverse().find(round =>
    (round.status === "splitting" || round.status === "matching") &&
    !history.some(item => item.id === round.challenge_id && (item.status === "failed" || item.is_trial)),
  );
  // 固定在本次访问的对局，避免详情刷新时把仍在判定的请求切到另一场。
  const [challengeId] = useState(() => pendingRound?.challenge_id ?? history.find(item => item.status !== "failed" && !item.is_trial)?.id);
  const path = `/scenario-challenges/${challengeId}`;
  const state = useQuery<GuessState>({
    queryKey: ["api", path],
    queryFn: ({ signal }) => request<GuessState>(path, { signal }),
    enabled: query => Boolean(challengeId && (open || pendingRound || query.state.data?.guess_in_flight || query.state.data?.verify_in_flight)),
    staleTime: 0,
    refetchInterval: query => query.state.data?.guess_in_flight || query.state.data?.verify_in_flight ? 1500 : false,
    retry: false,
  });

  useEffect(() => {
    if (state.data) void client.invalidateQueries({ queryKey: ["api", rosterPath], exact: true });
  }, [state.data, client, rosterPath]);

  useEffect(() => {
    if (!open || !window.visualViewport) return;
    const visual = window.visualViewport;
    const update = () => setViewport({
      "--guess-viewport-height": `${visual.height}px`,
      "--guess-keyboard-offset": `${Math.max(0, window.innerHeight - visual.height - visual.offsetTop)}px`,
    } as CSSProperties);
    update();
    visual.addEventListener("resize", update);
    visual.addEventListener("scroll", update);
    return () => {
      visual.removeEventListener("resize", update);
      visual.removeEventListener("scroll", update);
    };
  }, [open]);

  const guess = useMutation({
    mutationFn: (text: string) => request<{ round_id: string }>(`${path}/guess`, { method: "POST", body: JSON.stringify({ text }) }),
    onSuccess: async (result, text) => {
      setSelectedRound(result.round_id);
      setSubmittedText(text);
      setDraft("");
      setVerifyRequested(false);
      await state.refetch();
    },
    // POST 不自动重试：先回读服务端状态，避免网络中断导致重复扣次数。
    onError: async () => { await state.refetch(); },
  });
  const verify = useMutation({
    mutationFn: () => request(`${path}/guess/verify`, { method: "POST" }),
    onSuccess: async () => {
      setVerifyRequested(true);
      await state.refetch();
    },
    onError: async () => { await state.refetch(); },
  });

  const available = state.data?.guess_credits ?? credits;
  const knownCards = state.data?.guess_cards ?? cards;
  const allCracked = knownCards.length > 0 && knownCards.every(card => card.cracked);
  const knownRounds = state.data?.guess_rounds ?? rounds;
  const round = selectedRound
    ? knownRounds.find(item => item.id === selectedRound) ?? { text: submittedText, status: "matching" }
    : knownRounds.at(-1);
  const matches = roundMatches(round);
  const busy = guess.isPending || verify.isPending || Boolean(state.data?.guess_in_flight || state.data?.verify_in_flight);
  const unavailable = !challengeId ? "尚无可用对局" : state.data?.status === "failed" ? "对局已失败" : allCracked ? "已看破全部奇术" : available <= 0 ? "当前没有可用的提问次数" : "";
  const blocked = !state.data || state.isError || state.data.status === "failed";
  const status = state.data?.verify_in_flight || verify.isPending ? "检定中" : busy ? "判定中" : round?.status === "failed" ? "本次猜测失败" : round ? "本次结果" : "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy || blocked || unavailable || submitLock.current) return;
    submitLock.current = true;
    verify.reset();
    try { await guess.mutateAsync(text); } catch { /* 错误在窗口内显示，草稿保留 */ }
    finally { submitLock.current = false; }
  }

  return <Dialog.Root open={open} onOpenChange={setOpen} modal={false}>
    <Dialog.Trigger className="guess-fab" style={viewport} aria-label="道出猜测" aria-busy={busy}>
      猜测{busy && <span className="guess-fab__pending" aria-hidden="true" />}
    </Dialog.Trigger>
    <Dialog.Portal>
      <Dialog.Content className="guess-window" style={viewport} aria-describedby={undefined}
        onOpenAutoFocus={event => {
          event.preventDefault();
          if (window.matchMedia("(max-width: 600px)").matches || inputRef.current?.disabled) titleRef.current?.focus();
          else inputRef.current?.focus();
        }}
        onInteractOutside={event => event.preventDefault()}>
        <header className="guess-window__header">
          <div><Dialog.Title ref={titleRef} tabIndex={-1}>道出猜测</Dialog.Title><p>{characterName}</p></div>
          <span className="muted">可提问 {available}</span>
          <Dialog.Close className="btn btn-ghost btn-icon" aria-label="收起猜词"><XIcon size={18} /></Dialog.Close>
        </header>
        <div className="guess-window__results">
          {challengeId && state.isPending && <p role="status">载入中</p>}
          {state.isError && <div role="alert"><p className="err">{state.error.message}</p><button className="btn" onClick={() => void state.refetch()}>重试</button></div>}
          {status && <p role="status" className="guess-window__status">{status}</p>}
          {round && <section aria-label="本次猜词结果">
            <p className="guess-window__question">{round.text}</p>
            <div className="roster-clues">{matches.map((match, index) => <article className="roster-clue" key={`${match.card_index}-${match.atom_index}-${index}`}>
              <div><span className="muted">第 {match.card_index ?? "?"} 门奇术</span><p className="roster-clue__text">{match.text}</p></div>
              <span className={`roster-clue__verdict ${verdictClass(match.verdict)}`}>{match.status === "failed" ? "判定失败" : match.verdict === "不能确定" ? "不确定" : match.verdict === "半对" ? "部分是" : match.verdict}</span>
            </article>)}</div>
          </section>}
          {verifyRequested && !busy && !state.isError && <p role="status">已看破 {knownCards.filter(card => card.cracked).length} / {knownCards.length} 门</p>}
          {unavailable && <p className="muted">{unavailable}</p>}
          {(guess.error || verify.error) && <p className="err" role="alert">{(guess.error || verify.error)?.message}</p>}
        </div>
        <form className="guess-window__form" onSubmit={event => void submit(event)}>
          <label htmlFor={inputId}>猜测内容</label>
          <textarea id={inputId} ref={inputRef} className="textarea" rows={3} value={draft} onChange={event => setDraft(event.target.value)} disabled={!challengeId || allCracked} />
          <div className="guess-window__actions">
            <button className="btn btn-ghost" type="button" disabled={busy || blocked || allCracked || !knownRounds.some(item => item.status === "complete")} onClick={() => { guess.reset(); verify.mutate(); }}>检定看破</button>
            <button className="btn btn-primary" disabled={busy || blocked || Boolean(unavailable) || !draft.trim()}>道出猜测</button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
