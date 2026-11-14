import { test, expect, type Page } from "@playwright/test";
import { mockGame, ability, character } from "./fixtures";

async function populatedCodex(page: Page) {
  await mockGame(page);
  const abilities = Array.from({ length: 45 }, (_, i) => ({
    ...ability, id: `art-${i + 1}`, name: `奇术${i + 1}`,
    detail: "发动时必须屏息三息，力量只能作用于十步内的轻物。".repeat(20).slice(0, 500),
  }));
  const characters = Array.from({ length: 16 }, (_, i) => ({
    ...character, id: `person-${i + 1}`, name: `奇人${i + 1}`,
    bio: "在江边长大的送信人。\n".repeat(40).slice(0, 500),
    ability_ids: abilities.slice(0, 4).map(a => a.id),
  }));
  await page.route("**/api/creator/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/abilities")) return route.fulfill({ json: abilities });
    if (path.endsWith("/characters")) return route.fulfill({ json: characters });
    const selected = characters.find(c => path.endsWith(`/${c.id}`));
    return route.fulfill({ json: { ...selected, abilities: abilities.slice(0, 4) } });
  });
}

for (const [width, height] of [[1440, 900], [1280, 720], [1024, 600], [1920, 1080], [2560, 1440]]) {
  test(`异闻录 ${width}×${height}：长名册与详情均在视口内滚动`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height });
    await populatedCodex(page);
    await page.goto("/yiwenlu");
    await expect(page.locator(".codex__item")).toHaveCount(16);
    const before = await page.locator(".codex__body").boundingBox();
    expect(before!.y).toBeLessThan(220);
    expect(before!.y + before!.height).toBeLessThanOrEqual(height - 15);
    const create = page.getByRole("button", { name: "新建奇人", exact: true });
    const list = page.locator(".codex__list");
    const createBox = await create.boundingBox();
    const listBox = await list.boundingBox();
    expect(createBox!.y + createBox!.height).toBeLessThanOrEqual(listBox!.y);
    await page.locator(".codex__item").last().click();
    await expect(page.getByRole("heading", { name: "奇人16", exact: true })).toBeVisible();
    expect(await list.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
    const sheet = page.locator(".codex__sheet");
    await sheet.locator(".codex__hint").last().scrollIntoViewIfNeeded();
    expect(await sheet.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight)).toBe(true);
    await page.getByRole("button", { name: "编辑 奇人16" }).click();
    await expect(page.getByRole("button", { name: "保存", exact: true })).toBeInViewport({ ratio: 1 });
    await expect(create).toBeInViewport({ ratio: 1 });
    await page.screenshot({ path: testInfo.outputPath(`codex-${width}.png`) });
  });
}

test("奇人与奇术互跳不再生成来处返回控件", async ({ page }) => {
  await populatedCodex(page);
  await page.goto("/yiwenlu");
  await page.locator(".codex__slot").first().click();
  await expect(page).toHaveURL(/\/yiwenlu\/abilities\/art-1$/);
  await expect(page.getByRole("button", { name: "新建奇术", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /^回到 / })).toHaveCount(0);
  await page.locator(".codex__carrier").first().click();
  await expect(page).toHaveURL(/\/yiwenlu\/characters\/person-1$/);
  await expect(page.getByRole("button", { name: /^回到 / })).toHaveCount(0);
});

test("手机名册上方可新建，详情可随页面滚到底部", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await populatedCodex(page);
  await page.goto("/yiwenlu");
  await expect(page.locator(".codex__item")).toHaveCount(16);
  const create = page.getByRole("button", { name: "新建奇人", exact: true });
  const list = await page.locator(".codex__list").boundingBox();
  const button = await create.boundingBox();
  expect(button!.y + button!.height).toBeLessThanOrEqual(list!.y);
  await page.locator(".codex__hint").last().scrollIntoViewIfNeeded();
  await expect(page.locator(".codex__hint").last()).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
