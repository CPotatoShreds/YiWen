import { test, expect } from "@playwright/test";
import { guessAtoms, cardClues, verificationRows, type GuessRound } from "../src/guessModel";

const cards = Array.from({ length: 4 }, (_, i) => ({ index: i + 1, cracked: false }));
const round: GuessRound = {
  id: "r1", text: "体型很大。需要触碰。", status: "matching",
  atoms: [{ index: 1, text: "体型很大", status: "ready" }, { index: 2, text: "需要触碰", status: "ready" }],
  matches: [
    { atom_index: 2, card_index: 3, text: "需要触碰", verdict: "是" },
    { atom_index: 1, card_index: 4, text: "体型很大", verdict: "否" },
    { atom_index: 1, card_index: 1, text: "体型很大", verdict: "是" },
    { atom_index: 1, card_index: 3, text: "体型很大", verdict: "不能确定" },
    { atom_index: 1, card_index: 2, text: "体型很大", verdict: "部分是" },
  ],
};

test("按分词索引和奇术索引排列，异步完成顺序不影响气泡位置", () => {
  const rows = guessAtoms(round, cards);
  expect(rows.map(row => row.text)).toEqual(["体型很大", "需要触碰"]);
  expect(rows[0].answers.map(answer => answer.label)).toEqual(["是", "部分是", "不确定", "否"]);
  expect(rows[1].answers.map(answer => answer.label)).toEqual(["待判定", "待判定", "是", "待判定"]);
});

test("缺失配对与已看破、失败有明确区别，不虚构不确定答案", () => {
  const rows = guessAtoms({ ...round, status: "failed", matches: [] }, cards);
  expect(rows[0].answers.map(a => a.label)).toEqual(Array(4).fill("失败"));
  expect(guessAtoms({ ...round, matches: [] }, [{ index: 1, cracked: true }])[0].answers[0].label).toBe("已看破");
});

test("详情页线索优先采用有序轮次，不重复叠加同源 feedback/comments", () => {
  const rows = cardClues([round], { ...cards[0], feedback: [{ text: "需要触碰", round: "r1" }, { text: "体型很大", round: "r1" }] });
  expect(rows.map(row => row.text)).toEqual(["体型很大", "需要触碰"]);
});

test("旧 comments 按原文位置恢复，只有 feedback 的旧记录按轮分组去重", () => {
  const legacy = { text: round.text, comments: [{ index: 1, items: [{ text: "需要触碰", verdict: "否" }, { text: "体型很大", verdict: "是" }] }] };
  expect(guessAtoms(legacy, cards).map(a => a.text)).toEqual(["体型很大", "需要触碰"]);
  expect(cardClues([], { ...cards[0], feedback: [{ round: 1, text: "甲" }, { round: 1, text: "乙" }, { round: 1, text: "甲" }, { round: 2, text: "丙" }] }).map(c => c.text)).toEqual(["丙", "甲", "乙"]);
});

test("同一猜测轮次的多次检定分开显示，已看破卡不在后续倒退", () => {
  const rows = verificationRows([
    { index: 1, cracked: true, verifies: [{ id: "v1", round: 1, cracked: true, created_at: "2026-11-16T01:00:00" }] },
    { index: 2, cracked: false, verifies: [{ id: "v1", round: 1, cracked: false, created_at: "2026-11-16T01:00:00" }, { id: "v2", round: 1, cracked: false, created_at: "2026-11-16T01:01:00" }] },
  ]);
  expect(rows.map(r => r.id)).toEqual(["v1", "v2"]);
  expect(rows[1].answers.map(a => a.label)).toEqual(["看破", "未看破"]);
});

test("分词文本相同但索引不同，仍然是两条独立命题", () => {
  const repeated = { ...round, atoms: [{ index: 1, text: "大", status: "ready" }, { index: 2, text: "大", status: "ready" }], matches: [{ atom_index: 2, card_index: 1, text: "大", verdict: "否" }] };
  const rows = guessAtoms(repeated, cards);
  expect(rows).toHaveLength(2);
  expect(rows.map(row => row.answers[0].label)).toEqual(["待判定", "否"]);
});

test("检定没有返回结果时不把未检查的卡片伪装成未看破", () => {
  const [row] = verificationRows(cards, { id: "v-new", afterRound: 1, complete: true });
  expect(row.answers.map(answer => answer.label)).toEqual(Array(4).fill("无结果"));
});
