import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "../api";
import { guessAtoms, verificationRows, type GuessCard, type GuessRound, type GuessState } from "../guessModel";
import type { ScenarioHistoryItem } from "../scenarioModel";
import { XIcon } from "./icons";
import { useFloatingBall } from "../useFloatingBall";
import GuessAnswers from "./GuessAnswers";
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
  const [verification, setVerification] = useState<{ id: string; afterRound: number; legacy: boolean }>();
  const floating = useFloatingBall();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const submitLock = useRef(false);
  const inputId = useId();
  const dragHintId = useId();
  const pendingRound = [...rounds].reverse().find(round =>
    (round.status === "splitting" || round.status === "matching") &&
    !history.some(item => item.id === round.challenge_id && (item.status === "failed" || item.is_trial)),
  );
  const [boundChallenge, setBoundChallenge] = useState<string>();
  const candidate = pendingRound?.challenge_id ?? history.find(item => item.status !== "failed" && !item.is_trial)?.id;
  const challengeId = boundChallenge && !history.some(item => item.id === boundChallenge && item.status === "failed") ? boundChallenge : candidate;
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

  const guess = useMutation({
    mutationFn: (text: string) => request<{ round_id: string }>(`${path}/guess`, { method: "POST", body: JSON.stringify({ text }) }),
    onSuccess: async (result, text) => {
      setSelectedRound(result.round_id);
      setSubmittedText(text);
      setDraft("");

      await state.refetch();
    },
    // POST 不自动重试：先回读服务端状态，避免网络中断导致重复扣次数。
    onError: async () => { await state.refetch(); },
  });
  const verify = useMutation({
    mutationFn: () => request<{ verification_id?: string }>(`${path}/guess/verify`, { method: "POST" }),
    onSuccess: async result => {
      setVerification({ id: result.verification_id ?? `local:${Date.now()}`, afterRound: knownRounds.length, legacy: !result.verification_id });
      await state.refetch();
    },
    onError: async () => { await state.refetch(); },
  });

  const available = state.data?.guess_credits ?? credits;
  const knownCards = state.data?.guess_cards ?? cards;
  const allCracked = knownCards.length > 0 && knownCards.every(card => card.cracked);
  const knownRounds = state.data?.guess_rounds ?? rounds;
  // 刚提交、后端尚未回传的轮次：用提交原文兜底，避免结果区一闪而空
  const justSubmitted = selectedRound && !knownRounds.some(item => item.id === selectedRound)
    ? { id: selectedRound, text: submittedText, status: "matching" }
    : null;
  // 全部历史轮次，最新在上；justSubmitted 若存在则置于最顶
  const shownRounds = [
    ...(justSubmitted ? [justSubmitted] : []),
    ...[...knownRounds].reverse(),
  ];
  const busy = guess.isPending || verify.isPending || Boolean(state.data?.guess_in_flight || state.data?.verify_in_flight);
  const unavailable = !challengeId ? "尚无可用对局" : state.data?.status === "failed" ? "对局已失败" : allCracked ? "已看破全部奇术" : available <= 0 ? "当前没有可用的提问次数" : "";
  const blocked = !state.data || state.isError || state.data.status === "failed";
  const latestStatus = shownRounds[0]?.status;
  const status = state.data?.verify_in_flight || verify.isPending ? "检定中" : busy ? "判定中" : latestStatus === "failed" ? "本次猜测失败" : "";

  const verifications = verificationRows(knownCards, verification ? { ...verification, complete: !busy && !state.isError } : undefined, Boolean(state.data?.verify_in_flight));
  const timeline: ({ kind: "guess"; key: string; round: GuessRound; latest: boolean } | { kind: "verify"; key: string; result: typeof verifications[number] })[] = [];
  // 旧轮次在上、新轮次在下：shownRounds 是「最新在上」，倒过来遍历即得正序时间线
  [...shownRounds].reverse().forEach((round, index) => {
    timeline.push({ kind: "guess", key: `guess:${round.id ?? index}`, round, latest: round === shownRounds[0] });
    verifications.filter(item => item.afterRound === index + 1).forEach(result => timeline.push({ kind: "verify", key: result.id, result }));
  });
  verifications.filter(item => item.afterRound <= 0 || item.afterRound > shownRounds.length).forEach(result => timeline.push({ kind: "verify", key: result.id, result }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy || blocked || unavailable || submitLock.current) return;
    submitLock.current = true;
    setBoundChallenge(challengeId);
    verify.reset();
    try { await guess.mutateAsync(text); } catch { /* 错误在窗口内显示，草稿保留 */ }
    finally { submitLock.current = false; }
  }

  return <Dialog.Root open={open} onOpenChange={setOpen} modal={false}>
    <Dialog.Trigger className="guess-fab" style={floating.style} {...floating.handlers} data-dragging={floating.dragging} data-covered={floating.covered} aria-label="道出猜测" aria-describedby={dragHintId} aria-busy={busy}>
      猜测{busy && <span className="guess-fab__pending" aria-hidden="true" />}
    </Dialog.Trigger>
    <span id={dragHintId} className="guess-drag-hint">可拖动；方向键调整位置，按 Enter 展开。</span>
    <Dialog.Portal>
      <Dialog.Content className="guess-window" style={floating.style} aria-describedby={undefined}
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
          {timeline.map(entry => entry.kind === "guess" ? <section key={entry.key} className="guess-window__round" aria-label={entry.latest ? "本次猜词结果" : "往次猜词结果"}>
            {guessAtoms(entry.round, knownCards).map(atom => <article className="guess-atom" key={atom.index}>
              <p className="guess-window__question">{atom.text}</p>
              <GuessAnswers answers={atom.answers} />
            </article>)}
          </section> : <section key={entry.key} className="guess-window__round" aria-label="看破检定结果">
            <p className="guess-window__question">进行了看破检定</p>
            <GuessAnswers answers={entry.result.answers} />
          </section>)}
          {unavailable && <p className="muted">{unavailable}</p>}
          {(guess.error || verify.error) && <p className="err" role="alert">{(guess.error || verify.error)?.message}</p>}
        </div>
        <form className="guess-window__form" onSubmit={event => void submit(event)}>
          <label htmlFor={inputId}>猜测内容</label>
          <textarea id={inputId} ref={inputRef} className="textarea" rows={3} value={draft} onChange={event => setDraft(event.target.value)} disabled={!challengeId || allCracked} />
          <div className="guess-window__actions">
            <button className="btn btn-ghost" type="button" disabled={busy || blocked || allCracked || !knownRounds.some(item => item.status === "complete")} onClick={() => { if (busy || blocked || submitLock.current) return; setBoundChallenge(challengeId); guess.reset(); verify.mutate(); }}>检定看破</button>
            <button className="btn btn-primary" disabled={busy || blocked || Boolean(unavailable) || !draft.trim()}>道出猜测</button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
