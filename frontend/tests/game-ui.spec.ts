import { test, expect } from "@playwright/test";
import { mockGame, scenario, roster } from "./fixtures";

for (const width of [1440, 768, 390]) {
  test(`纸墨游戏主流程在 ${width}px 下可读`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await mockGame(page);
    const errors: string[] = [];
    page.on("pageerror", e => errors.push(e.message));
    const base = `/scenarios/${scenario.slug}`;
    const pages = [["home", "/home"], ["volumes", "/scenarios"], ["volume", base], ["codex", "/yiwenlu"], ["roster", `${base}/rosters/${roster.id}`], ["battle", `${base}/rosters/${roster.id}/battle`], ["records", `${base}/rosters/${roster.id}/records`], ["composer", `${base}/rosters/new`], ["settings", "/settings"]];
    for (const [name, url] of pages) {
      await page.goto(url);
      await expect(page.locator("main")).toContainText(/书院|小天下集|夜渡听潮|异闻录|撑伞客|刻印奇人|设置/);
      await expect(page.locator(".skeleton")).toHaveCount(0);
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`${name}-${width}.png`), fullPage: true });
    }
    expect(errors).toEqual([]);
  });
}

test("空册可创建奇人，经首页返回后仍能读取", async ({ page }) => {
  await mockGame(page, { empty: true });
  await page.goto("/yiwenlu");
  await page.getByRole("button", { name: "写一位奇人" }).click();
  await page.getByRole("textbox", { name: "名字" }).fill("听雨客");
  await page.getByRole("button", { name: "收录", exact: true }).click();
  await expect(page.getByRole("heading", { name: "听雨客" })).toBeVisible();
  await page.getByRole("navigation", { name: "主导航", exact: true }).getByRole("link", { name: "书院", exact: true }).click();
  await page.locator("main").getByRole("link", { name: /异闻录/ }).click();
  await expect(page.getByRole("heading", { name: "听雨客" })).toBeVisible();
});

test("放弃修改与删除都可取消，确认框管理焦点", async ({ page }) => {
  await mockGame(page);
  await page.goto("/yiwenlu");
  await page.getByRole("button", { name: "编辑 沈听澜" }).click();
  await page.getByRole("textbox", { name: "名字" }).fill("尚未保存");
  const cancel = page.getByRole("button", { name: "取消", exact: true });
  await cancel.click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog.getByRole("button", { name: "取消" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("textbox", { name: "名字" })).toHaveValue("尚未保存");
  await expect(cancel).toBeFocused();
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await dialog.getByRole("button", { name: "取消" }).click();
  await expect(page.getByRole("textbox", { name: "名字" })).toBeVisible();
});

test("设置页签支持方向键，手机目录可关可导航", async ({ page }) => {
  await mockGame(page);
  await page.goto("/settings");
  await page.getByRole("tab", { name: "模型方案" }).focus();
  await page.keyboard.press("End");
  await expect(page.getByRole("tab", { name: "数据与账号" })).toHaveAttribute("aria-selected", "true");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "打开导航" })).toBeFocused();
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("navigation", { name: "移动端导航" }).getByRole("link", { name: "小天下集" }).click();
  await expect(page).toHaveURL(/\/scenarios$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("编修时切换篇章，取消保留草稿，确认后清除旧表单", async ({ page }) => {
  await mockGame(page);
  await page.goto("/yiwenlu");
  await page.getByRole("button", { name: "编辑 沈听澜" }).click();
  await page.getByRole("textbox", { name: "名字" }).fill("未落定的名字");
  await page.getByRole("tab", { name: /奇术篇/ }).click();
  const dialog = page.getByRole("alertdialog");
  await dialog.getByRole("button", { name: "取消" }).click();
  await expect(page.getByRole("textbox", { name: "名字" })).toHaveValue("未落定的名字");
  await page.getByRole("tab", { name: /奇术篇/ }).click();
  await dialog.getByRole("button", { name: "确认继续" }).click();
  await expect(page.getByRole("heading", { name: "借风", exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "名字" })).toHaveCount(0);
});

test("推演书页用键盘切换视角，未解锁记录不显示推演全文", async ({ page }) => {
  await mockGame(page, { reading: true });
  await page.goto(`/scenarios/${scenario.slug}/rosters/${roster.id}/battle`);
  await page.getByRole("tab", { name: "推演", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "挑战者视角" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tabpanel")).toContainText("我踏过湿漉漉的石阶");
  await page.unrouteAll();
  await mockGame(page);
  await page.goto(`/scenarios/${scenario.slug}/rosters/${roster.id}/records`);
  await expect(page.locator("main")).toContainText("我踏过湿漉漉的石阶");
  await expect(page.locator("main")).not.toContainText("送信人在钟响之前借风渡江，将信交付。");
});

test("卷架失败给出重试", async ({ page }) => {
  await mockGame(page, { failedVolumes: true });
  await page.goto("/scenarios");
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("button", { name: /重新|重试/ })).toBeVisible();
});

test("寻卷无结果可清除，往期记录可以收起", async ({ page }) => {
  await mockGame(page);
  await page.goto("/scenarios");
  await page.getByRole("searchbox", { name: "寻卷" }).fill("不存在的卷");
  await expect(page.getByRole("heading", { name: "未找到相应的卷" })).toBeVisible();
  await page.getByRole("button", { name: "清除搜索" }).click();
  await expect(page.getByRole("heading", { name: scenario.name })).toBeVisible();
  await page.goto(`/scenarios/${scenario.slug}/rosters/${roster.id}/records`);
  const row = page.locator(".records-row__hit");
  await expect(row).toHaveAttribute("aria-expanded", "true");
  await row.click();
  await expect(row).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator(".records-row__folio")).toHaveCount(0);
});

test("减少动态效果时仍能导航，账号菜单支持 Escape", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockGame(page);
  await page.goto("/home");
  const account = page.getByRole("button", { name: "打开账号菜单" });
  await account.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menu")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(account).toBeFocused();
  await page.locator("main").getByRole("link", { name: /小天下集/ }).click();
  await expect(page).toHaveURL(/\/scenarios$/);
  await expect(page.getByRole("heading", { name: /小天下集/, level: 1 })).toBeVisible();
  expect(await page.locator("main").evaluate(el => el.getAnimations().length)).toBe(0);
});
