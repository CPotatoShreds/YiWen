import type { CSSProperties } from "react";
import { verdictClass, type GuessAnswer } from "../guessModel";

/** 第 n 个气泡固定对应第 n 门奇术，输出结果不伪装成可选按钮。 */
export default function GuessAnswers({ answers }: { answers: GuessAnswer[] }) {
  return <ol className="guess-answers" style={{ "--guess-card-count": Math.max(1, answers.length) } as CSSProperties}>
    {answers.map(answer => <li key={answer.cardIndex} className={`guess-answer ${verdictClass(answer.label)}`}
      aria-label={`第 ${answer.cardIndex} 门奇术：${answer.label}`} title={`第 ${answer.cardIndex} 门奇术：${answer.label}`}>
      <span className="guess-answer__index" aria-hidden="true">{answer.cardIndex}</span><span>{answer.label}</span>
    </li>)}
  </ol>;
}
