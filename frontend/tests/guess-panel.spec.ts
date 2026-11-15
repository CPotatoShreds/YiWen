import { test, expect, type Page } from "@playwright/test";
import { mockGame, scenario, roster, history, context, challenge } from "./fixtures";
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
  const cards = () => [{ index: 1, cracked, ...(cracked ? { name: "借风", effect: "借一阵风" } : {}), verifies: verifies && !verifying ? [{ id: "verify-1", round: rounds.length, cracked }] : [], feedback: rounds[0]?.status !== "complete" ? [] : [{ text: question, verdict: "是", round: "round-1" }] }];
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
      return route.fulfill({ status: 202, json: { status: "accepted", verification_id: "verify-1", verify_in_flight: true } });
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
      return route.fulfill({ json: { ...challenge, ...state } });
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
  await expect(panel.getByRole("region", { name: "看破检定结果" }).getByRole("listitem", { name: "第 1 门奇术：看破", exact: true })).toBeVisible({ timeout: 8000 });
  await expect(page.locator(".roster-card.is-active")).toContainText("借风");
  expect(server.verifies()).toBe(1);
  expect(server.posts()).toBe(1);
  await page.reload();
  await page.getByRole("button", { name: "道出猜测", exact: true }).click();
  await expect(page.getByRole("region", { name: "看破检定结果" }).getByRole("listitem", { name: "第 1 门奇术：看破", exact: true })).toBeVisible();
});

test("重新进入详情可恢复正在判定的猜测", async ({ page }) => {
  await guessingGame(page, { resume: true, credits: 0 });
  await page.goto(detailUrl);
  await page.getByRole("button", { name: "道出猜测", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "道出猜测" });
  await expect(panel.getByRole("region", { name: "本次猜词结果" })).toContainText(question);
  await expect(panel.getByRole("listitem", { name: "第 1 门奇术：是", exact: true })).toBeVisible({ timeout: 10000 });
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

test("悬浮球可拖动贴边，拖动不误展开，方向键可替代拖动", async ({ page }) => {
  await guessingGame(page);
  await page.goto(detailUrl);
  const ball = page.getByRole("button", { name: "道出猜测", exact: true });
  const initial = await ball.boundingBox();
  await page.mouse.move(initial!.x + 28, initial!.y + 28);
  await page.mouse.down();
  await page.mouse.move(70, 260, { steps: 12 });
  await page.mouse.up();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect((await ball.boundingBox())!.x).toBe(16);
  await ball.focus();
  await page.keyboard.press("ArrowRight");
  expect((await ball.boundingBox())!.x).toBeGreaterThan(1000);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "道出猜测" })).toBeVisible();
});

test.describe("触摸悬浮球", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  test("手机拖动贴边不滚动页面，松手后仍可轻触展开", async ({ page }) => {
    await guessingGame(page);
    await page.goto(detailUrl);
    const ball = page.locator(".guess-fab");
    const initial = await ball.boundingBox();
    const scroll = await page.evaluate(() => scrollY);
    const touch = await page.context().newCDPSession(page);
    await touch.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: initial!.x + 28, y: initial!.y + 28, id: 1 }] });
    for (let step = 1; step <= 8; step++) {
      await touch.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: initial!.x + 28 + (50 - initial!.x - 28) * step / 8, y: initial!.y + 28 + (310 - initial!.y - 28) * step / 8, id: 1 }] });
    }
    await touch.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    await expect(ball).toHaveCSS("left", "16px");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(await page.evaluate(() => scrollY)).toBe(scroll);
    await ball.tap();
    await expect(page.getByRole("dialog", { name: "道出猜测" })).toBeVisible();
    await ball.tap();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await ball.tap();
    await expect(page.getByRole("dialog", { name: "道出猜测" })).toBeVisible();
    await touch.detach();
  });
});

test("详情、对战和记录共享悬浮球位置、展开状态与草稿", async ({ page }) => {
  await guessingGame(page);
  await page.goto(detailUrl);
  const ball = page.locator(".guess-fab");
  await ball.focus();
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("Enter");
  const panel = page.getByRole("dialog", { name: "道出猜测" });
  await panel.getByRole("textbox").fill("跨页保留的猜测");
  await page.getByRole("link", { name: "起笔", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${detailUrl}/battle$`));
  await expect(panel.getByRole("textbox")).toHaveValue("跨页保留的猜测");
  expect((await ball.boundingBox())!.x).toBe(16);
  await page.getByRole("link", { name: "翻阅往期", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${detailUrl}/records$`));
  await expect(panel.getByRole("textbox")).toHaveValue("跨页保留的猜测");
  await panel.getByRole("button", { name: "收起猜词" }).click();
  await ball.click();
  await expect(panel.getByRole("textbox")).toHaveValue("跨页保留的猜测");
});

for (const child of ["battle", "records"]) {
  test(`直接进入 ${child} 也能打开猜词`, async ({ page }) => {
    await guessingGame(page);
    await page.goto(`${detailUrl}/${child}`);
    await page.getByRole("button", { name: "道出猜测", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "道出猜测" }).getByRole("textbox")).toBeVisible();
  });
}

test("乱序返回的配对固定落入对应气泡，线索与分词顺序一致", async ({ page }) => {
  await guessingGame(page);
  let complete = false;
  const atoms = [{ index: 1, text: "体型很大", status: "ready" }, { index: 2, text: "需要触碰", status: "ready" }];
  const cards = Array.from({ length: 4 }, (_, i) => ({ index: i + 1, cracked: false }));
  const round = () => ({ id: "ordered-round", challenge_id: history.id, status: complete ? "complete" : "matching", text: "体型很大，需要触碰", atoms, matches: complete ? [
    { atom_index: 2, card_index: 3, text: "需要触碰", verdict: "是" },
    { atom_index: 1, card_index: 3, text: "体型很大", verdict: "否" },
    { atom_index: 1, card_index: 1, text: "体型很大", verdict: "是" },
    { atom_index: 1, card_index: 4, text: "体型很大", verdict: "不确定" },
    { atom_index: 1, card_index: 2, text: "体型很大", verdict: "部分是" },
  ] : [{ atom_index: 2, card_index: 3, text: "需要触碰", verdict: "是" }] });
  await page.route(`**/api${detailUrl}`, route => route.fulfill({ json: { ...context, roster: { ...roster, ability_count: 4 }, my_progress: { ...context.my_progress, cracked_cards: cards, guess_rounds: [round()] } } }));
  await page.route(`**/api/scenario-challenges/${history.id}`, route => route.fulfill({ json: { id: history.id, status: "won", guess_rounds: [round()], guess_cards: cards, guess_in_flight: !complete, guess_credits: 1 } }));
  await page.goto(detailUrl);
  await page.getByRole("button", { name: "道出猜测", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "道出猜测" });
  await expect(panel.locator(".guess-atom > p")).toHaveText(["体型很大", "需要触碰"]);
  await expect(panel.locator(".guess-answers").first().locator("li")).toHaveCount(4);
  await expect(panel.locator(".guess-answers").first()).toContainText("待判定");
  complete = true;
  const first = panel.locator(".guess-answers").first();
  await expect(first.getByRole("listitem", { name: "第 1 门奇术：是", exact: true })).toBeVisible({ timeout: 8000 });
  expect(await first.locator("li").evaluateAll(items => items.map(item => item.getAttribute("aria-label")))).toEqual(["第 1 门奇术：是", "第 2 门奇术：部分是", "第 3 门奇术：否", "第 4 门奇术：不确定"]);
  await expect(page.locator(".roster-book__page--clues .roster-clue__text")).toHaveText(["体型很大", "需要触碰"]);
});
