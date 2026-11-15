import { test, expect, type Page } from "@playwright/test";
import { mockGame, scenario, roster, history, context } from "./fixtures";
import type { GuessState, GuessRound } from "../src/guessModel";

const detailUrl = `/scenarios/${scenario.slug}/rosters/${roster.id}`;
const question = "对手只能在雨天发动奇术";

async function guessingGame(page: Page, options: { credits?: number; noHistory?: boolean; owner?: boolean; reject?: boolean; resume?: boolean; failRound?: boolean } = {}) {
  await mockGame(page);
  let posts = 0;
  let verifies = 0;
  let polls = 0;
  let busy = Boolean(options.resume);
  let verifying = false;
  let credits = options.credits ?? 1;
  let cracked = false;
  let rounds: GuessRound[] = options.resume ? [{ id: "round-1", challenge_id: history.id, text: question, status: "matching", matches: [] }] : [];
  const cards = () => [{ index: 1, cracked, ...(cracked ? { name: "借风", effect: "借一阵风" } : {}), feedback: rounds[0]?.status !== "complete" ? [] : [{ text: question, verdict: "是", round: "round-1" }] }];
  await page.route(`**/api${detailUrl}`, route => route.fulfill({ json: {
    ...context, viewer_role: options.owner ? "owner" : "challenger",
    my_challenges: options.noHistory ? [] : [history],
    roster: { ...roster, ability_count: 1 },
    my_progress: { ...context.my_progress, guess_credits: credits, cracked_cards: cards(), guess_rounds: rounds },
  } }));
  await page.route("**/api/scenario-challenges/**", async route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (req.method() === "POST" && path.endsWith("/guess")) {
      posts++;
      expect(req.postDataJSON()).toEqual({ text: question });
      if (options.reject) return route.fulfill({ status: 409, json: { detail: "上一轮猜测仍在判定中" } });
      credits--;
      busy = true;
      polls = 0;
      rounds = [{ id: "round-1", challenge_id: history.id, text: question, status: "matching", atoms: [{ index: 1, text: question, status: "ready" }], matches: [] }];
      return route.fulfill({ status: 202, json: { status: "accepted", round_id: "round-1", guess_credits: credits } });
    }
    if (req.method() === "POST" && path.endsWith("/guess/verify")) {
      verifies++;
      verifying = true;
      polls = 0;
      return route.fulfill({ status: 202, json: { status: "accepted", verify_in_flight: true } });
    }
    if (req.method() === "GET" && path.endsWith(`/${history.id}`)) {
      if (busy && ++polls >= 3) {
        busy = false;
        if (options.failRound) {
          credits++;
          rounds = [{ ...rounds[0], status: "failed", matches: [] }];
        } else {
          rounds = [{ ...rounds[0], status: "complete", matches: [{ atom_index: 1, card_index: 1, text: question, verdict: "是", status: "complete" }] }];
        }
      }
      if (verifying && ++polls >= 2) { verifying = false; cracked = true; }
      const state: GuessState = { id: history.id, roster_id: roster.id, status: "won", guess_credits: credits, guess_rounds: rounds, guess_cards: cards(), guess_in_flight: busy, verify_in_flight: verifying };
      return route.fulfill({ json: state });
    }
    return route.fulfill({ status: 404, json: { detail: "Unknown request" } });
  });
  return { posts: () => posts, verifies: () => verifies, finished: () => !busy && rounds.length > 0 };
}

test("悬浮窗可用键盘收起、保留草稿，页面仍可浏览", async ({ page }) => {
  await guessingGame(page);
  await page.goto(detailUrl);
  const trigger = page.getByRole("button", { name: "道出猜测", exact: true });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const panel = page.getByRole("dialog", { name: "道出猜测" });
  const input = panel.getByRole("textbox", { name: "猜测内容" });
  await expect(input).toBeFocused();
  await input.fill(question);
  await page.getByRole("heading", { name: "撑伞客", exact: true }).click();
  await expect(panel).toBeVisible();
  await input.focus();
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await trigger.click();
  await expect(input).toHaveValue(question);
});

test("提交一次猜测，收起后继续轮询，结果和线索同步；检定不再扣次数", async ({ page }) => {
  const server = await guessingGame(page);
  await page.goto(detailUrl);
  await page.getByRole("button", { name: "道出猜测", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "道出猜测" });
  await panel.getByRole("textbox").fill(question);
  await expect(panel.getByRole("button", { name: "道出猜测" })).toBeEnabled();
  await panel.locator("form").evaluate((form: HTMLFormElement) => { form.requestSubmit(); form.requestSubmit(); });
  await expect(panel.getByText("判定中", { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: "收起猜词" }).click();
  await expect.poll(server.finished, { timeout: 10000 }).toBe(true);
  expect(server.posts()).toBe(1);
  await expect(page.locator(".roster-book__page--clues")).toContainText(question);
  await page.getByRole("button", { name: "道出猜测", exact: true }).click();
  await expect(panel.getByRole("region", { name: "本次猜词结果" })).toContainText("是");
  await expect(panel).toContainText("可提问 0");
  await expect(panel.getByRole("button", { name: "道出猜测" })).toBeDisabled();
  await panel.getByRole("button", { name: "检定看破" }).click();
  await expect(panel.getByText("已看破 1 / 1 门", { exact: true })).toBeVisible({ timeout: 8000 });
  await expect(page.locator(".roster-card.is-active")).toContainText("借风");
  expect(server.verifies()).toBe(1);
  expect(server.posts()).toBe(1);
});

test("重新进入详情可恢复正在判定的猜测", async ({ page }) => {
  await guessingGame(page, { resume: true, credits: 0 });
  await page.goto(detailUrl);
  await page.getByRole("button", { name: "道出猜测", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "道出猜测" });
  await expect(panel.getByRole("region", { name: "本次猜词结果" })).toContainText(question);
  await expect(panel.locator(".roster-clue__verdict")).toHaveText("是", { timeout: 10000 });
});

test("无对局、无次数和作者视角不会发送不可用请求", async ({ page }) => {
  const server = await guessingGame(page, { noHistory: true, credits: 0 });
  await page.goto(detailUrl);
  await page.getByRole("button", { name: "道出猜测", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "道出猜测" });
  await expect(panel).toContainText("尚无可用对局");
  await expect(panel.getByRole("textbox")).toBeDisabled();
  await expect(panel.getByRole("button", { name: "道出猜测" })).toBeDisabled();
  expect(server.posts()).toBe(0);
  await page.unrouteAll();
  await guessingGame(page, { owner: true });
  await page.reload();
  await expect(page.getByRole("heading", { name: "撑伞客", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "道出猜测", exact: true })).toHaveCount(0);
});

test("失败保留输入，不自动重试扣次请求", async ({ page }) => {
  const server = await guessingGame(page, { reject: true });
  await page.goto(detailUrl);
  await page.getByRole("button", { name: "道出猜测", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "道出猜测" });
  await panel.getByRole("textbox").fill(question);
  await panel.getByRole("button", { name: "道出猜测" }).click();
  await expect(panel.getByRole("alert")).toHaveText("上一轮猜测仍在判定中");
  await expect(panel.getByRole("textbox")).toHaveValue(question);
  expect(server.posts()).toBe(1);
});

test("后台判定失败时显示失败，次数以服务器退回结果为准", async ({ page }) => {
  const server = await guessingGame(page, { failRound: true });
  await page.goto(detailUrl);
  await page.getByRole("button", { name: "道出猜测", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "道出猜测" });
  await panel.getByRole("textbox").fill(question);
  await panel.getByRole("button", { name: "道出猜测" }).click();
  await expect(panel.getByText("本次猜测失败", { exact: true })).toBeVisible({ timeout: 10000 });
  await expect(panel).toContainText("可提问 1");
  await expect(panel.getByRole("button", { name: "检定看破" })).toBeDisabled();
  expect(server.posts()).toBe(1);
});

test("手机小窗与较小可视区域不溢出，输入不被遮挡", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await guessingGame(page);
  await page.goto(detailUrl);
  await page.getByRole("button", { name: "道出猜测", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "道出猜测" });
  await expect(panel.getByRole("heading", { name: "道出猜测" })).toBeFocused();
  await panel.getByRole("textbox").fill(question);
  await page.setViewportSize({ width: 390, height: 360 });
  await expect(panel.getByRole("textbox")).toBeInViewport({ ratio: 1 });
  await expect(panel.getByRole("button", { name: "道出猜测" })).toBeInViewport({ ratio: 1 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await panel.getByRole("button", { name: "收起猜词" }).click();
  await expect(page.getByRole("button", { name: "道出猜测", exact: true })).toBeFocused();
});
